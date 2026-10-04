"""Physical network adapters first, with virtual interfaces explicitly separated."""
import glob
import json
import re
from pathlib import Path
import socket
import psutil
from .base import Collector, read_file, run_cmd

def _ip_json(args):
    try:return json.loads(run_cmd(['ip','-j']+args) or '[]')
    except ValueError:return []

def nm_fields(line):
    values=[];current='';escape=False
    for char in line:
        if escape:current+=char;escape=False
        elif char=='\\':escape=True
        elif char==':':values.append(current);current=''
        else:current+=char
    values.append(current);return values

def wifi_link(iface):
    rec={};out=run_cmd(['iw','dev',iface,'link']) or ''
    if 'Connected to' in out:rec['connection_state']='Connected'
    for label,key in [('SSID','SSID'),('signal','signal'),('tx bitrate','transmit_link_rate'),('rx bitrate','receive_link_rate'),('freq','frequency_MHz')]:
        m=re.search(r'^\s*'+re.escape(label)+r':\s*(.+)',out,re.M)
        if m:rec[key]=m[1].strip()
    if 'Not connected' in out:rec['connection_state']='Disconnected'
    # NetworkManager supplies useful fallback even without iw installed.
    if not rec.get('transmit_link_rate'):
        out=run_cmd(['nmcli','-t','-f','ACTIVE,SSID,RATE,SIGNAL','device','wifi','list','ifname',iface,'--rescan','no']) or ''
        for line in out.splitlines():
            fields=nm_fields(line)
            if len(fields)==4 and fields[0]=='yes':
                rec.setdefault('SSID',fields[1]);rec['advertised_AP_rate']=fields[2];rec['signal_percent']=fields[3]
                break
    # AP advertised rate is not the negotiated link rate or measured throughput.
    if not rec.get('transmit_link_rate'):rec['link_rate_note']='Negotiated Wi-Fi speed is not reported; advertised AP rate is not a speed test'
    return rec

class NetworkCollector(Collector):
    name='network';title='Network / Bluetooth'
    def collect(self):
        r=self.new_result();physical=0;virtual=0
        try:addrs=psutil.net_if_addrs()
        except (OSError,psutil.Error):addrs={}
        try:stats=psutil.net_if_stats()
        except (OSError,psutil.Error):stats={}
        names=sorted(set(addrs)|{p.rsplit('/',1)[-1] for p in glob.glob('/sys/class/net/*')})
        io=psutil.net_io_counters(pernic=True)
        for iface in names:
            path=Path('/sys/class/net')/iface
            is_physical=(path/'device').exists()
            is_wifi=(path/'wireless').exists() or (path/'phy80211').exists()
            kind='Wi-Fi' if is_wifi else 'Ethernet / hardware interface' if is_physical else 'Loopback (local computer traffic)' if iface=='lo' else 'Tailscale VPN' if iface.startswith('tailscale') else 'Virtual network interface'
            st=stats.get(iface);state=read_file(str(path/'operstate'))
            rec={'kind':'network_adapter' if is_physical else 'virtual_interface','name':iface,'adapter_type':kind,
                'state':state or ('Up' if st and st.isup else 'Down'), 'MTU':st.mtu if st else None,'advanced':not is_physical}
            if is_physical:
                physical+=1;dev=path/'device';slot=dev.resolve().name
                pci=run_cmd(['lspci','-s',slot,'-nn']) if re.fullmatch(r'[0-9a-fA-F:]+\.[0-7]',slot) else None
                if pci and ': ' in pci:rec['model']=pci.split(': ',1)[1].strip();rec['name']=rec['model']
                if (dev/'driver').exists():rec['driver']=(dev/'driver').resolve().name
            else:virtual+=1
            if is_wifi:rec.update(wifi_link(iface))
            elif is_physical and st and st.speed>0:rec['link_speed_Mbit_s']=st.speed
            elif is_physical:rec['speed_note']='Link speed not exposed or interface disconnected'
            ipv4=[];ipv6=[]
            for a in addrs.get(iface,[]):
                if a.family==socket.AF_INET:ipv4.append(f'{a.address}/{a.netmask}' if a.netmask else a.address)
                elif a.family==socket.AF_INET6:ipv6.append(a.address)
                elif a.family==psutil.AF_LINK:rec['MAC_address']=a.address
            if ipv4:rec['IPv4_addresses']=ipv4
            if ipv6:rec['IPv6_addresses']=ipv6
            traffic=io.get(iface)
            if traffic:rec.update({'receive_errors':traffic.errin,'transmit_errors':traffic.errout,'dropped_in':traffic.dropin,'dropped_out':traffic.dropout})
            r.add_record({k:v for k,v in rec.items() if v is not None})
        r.add('Physical network adapters',physical);r.add('Virtual interfaces',virtual,advanced=True)
        bluetooth=[]
        for path in sorted(glob.glob('/sys/class/bluetooth/hci*')):
            dev=Path(path)/'device';rec={'kind':'bluetooth','name':'Bluetooth adapter '+Path(path).name,'driver':(dev/'driver').resolve().name if (dev/'driver').exists() else None}
            for child in [dev,*dev.resolve().parents]:
                model=read_file(str(child/'product'));vendor=read_file(str(child/'manufacturer'))
                if model:rec['model']=model
                if vendor:rec['manufacturer']=vendor
                if model:break
            bluetooth.append(rec)
        # Adapter can be present in USB inventory while rfkill disables hci registration.
        if not bluetooth:
            for line in (run_cmd(['lsusb']) or '').splitlines():
                if 'bluetooth' in line.lower():bluetooth.append({'kind':'bluetooth','name':line.split('ID ',1)[-1],'state':'USB device present; active controller is not exposed'})
        for rf in glob.glob('/sys/class/rfkill/rfkill*'):
            if read_file(rf+'/type')=='bluetooth':
                for b in bluetooth:
                    b['software_blocked']=read_file(rf+'/soft')=='1'
                    b['hardware_blocked']=read_file(rf+'/hard')=='1'
        for b in bluetooth:r.add_record({k:v for k,v in b.items() if v is not None})
        r.add('Bluetooth adapters detected',len(bluetooth))
        for route in _ip_json(['route','show','default']):r.add_record({'kind':'route','name':'Default route','gateway':route.get('gateway'),'interface':route.get('dev'),'metric':route.get('metric'),'advanced':True})
        resolv=read_file('/etc/resolv.conf')
        if resolv:r.add('DNS servers',[l.split()[1] for l in resolv.splitlines() if l.strip().startswith('nameserver ') and len(l.split())>1],advanced=True)
        r.note='Wi-Fi link rates describe the radio link, not download speed. Loopback and VPN interfaces appear only with technical details.'
        return r
