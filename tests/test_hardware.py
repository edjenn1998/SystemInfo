import json
import struct
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from system_info.smbios import parse_smbios
from system_info.collectors.memory import memory_inventory
from system_info.collectors.power import battery_record
from system_info.collectors.cpu import boost_status
from system_info.collectors.storage import StorageCollector, health_fields
from system_info.collectors.gpu import GpuCollector
from system_info.collectors.network import NetworkCollector, wifi_link, nm_fields
from system_info.core import CategoryResult, SystemSnapshot
from system_info.overview import overview
from system_info.protected import read_protected


def smbios_fixture():
    def record(typ,handle,length,strings=(),values=()):
        data=bytearray(length);data[0]=typ;data[1]=length;struct.pack_into('<H',data,2,handle)
        for offset,width,value in values:data[offset:offset+width]=value.to_bytes(width,'little')
        return bytes(data)+b'\0'.join(s.encode() for s in strings)+b'\0\0'
    table=record(16,0x1000,15,values=[(5,1,3),(13,2,4)])
    for i in range(4):
        table+=record(17,0x1100+i,0x28,['BANK'+str(i),'CHANNEL '+str(i),'Samsung','SERIAL'+str(i),'PART123'],
            [(4,2,0x1000),(8,2,64),(10,2,64),(12,2,4096),(14,1,11),(16,1,1),(17,1,2),(18,1,0x1e),
             (21,2,4267),(23,1,3),(24,1,4),(26,1,5),(27,1,1),(32,2,4267),(38,2,1200)])
    return table+record(127,0x7fff,4)

class HardwareTests(unittest.TestCase):
    def test_smbios_onboard_memory(self):
        sections=parse_smbios(smbios_fixture());count,used,empty,onboard,modules=memory_inventory(sections)
        self.assertEqual((count,used,empty,onboard),(4,4,0,True))
        self.assertEqual(modules[0]['manufacturer'],'Samsung');self.assertEqual(modules[0]['configured_speed'],'4267 MT/s')
        self.assertEqual(modules[0]['memory_type'],'LPDDR4')
    def test_smbios_truncation(self):
        with self.assertRaises(ValueError):parse_smbios(smbios_fixture()[:-2])
    def test_memory_empty_and_unknown(self):
        sections=[{'type':16,'handle':'0x10','fields':{'Use':'System Memory','Number Of Devices':'2'}},
                  {'type':17,'fields':{'Array Handle':'0x10','Size':'8192 MB','Form Factor':'SODIMM'}},
                  {'type':17,'fields':{'Array Handle':'0x10','Size':'No Module Installed'}}]
        self.assertEqual(memory_inventory(sections)[:4],(2,1,1,False))
        sections[-1]['fields']['Size']='Unknown';self.assertEqual(memory_inventory(sections)[1:3],(None,None))
    def battery(self,values):
        def read(path):return values.get(path.rsplit('/',1)[-1])
        with patch('system_info.inventory.read_file',side_effect=read),patch('system_info.collectors.power.read_file',side_effect=read):
            return battery_record('/sys/class/power_supply/BAT0')
    def test_battery_charge_health(self):
        b=self.battery({'status':'Discharging','capacity':'73','voltage_now':'7843000','current_now':'1370000',
            'charge_full':'5372000','charge_full_design':'6000000','charge_now':'3935000'})
        self.assertEqual(b['health_percent'],89.5);self.assertEqual(b['charge_percent'],73);self.assertEqual(b['power_W'],10.74)
        self.assertIn('2h 52m',b['time_estimate']);self.assertEqual(b['design_capacity_mAh'],6000)
    def test_battery_energy_and_missing_design(self):
        b=self.battery({'status':'Charging','capacity':'50','energy_full':'40000000','energy_full_design':'50000000','energy_now':'20000000','power_now':'10000000'})
        self.assertEqual(b['health_percent'],80);self.assertEqual(b['time_estimate'],'2h 0m until full')
        b=self.battery({'charge_full':'1000','charge_full_design':'0'})
        self.assertNotIn('health_percent',b);self.assertIn('health_note',b)
    def test_boost_intel(self):
        with patch('system_info.collectors.cpu.read_file',side_effect=lambda p:'0' if p.endswith('no_turbo') else None):self.assertEqual(boost_status(),'Enabled')
    def test_storage_only_physical_primary(self):
        old=json.loads((Path(__file__).parent/'fixtures/laptop-storage.json').read_text())
        devices=[{'name':r['name'],'path':r['path'],'type':r['kind'],'size':r['size'],'model':r['model'],'tran':r['transport'],'rota':r['rotational']} for r in old['records'] if 'path' in r]
        with patch.object(StorageCollector,'_lsblk',return_value=devices),patch('system_info.collectors.storage.smart_report',return_value={}),patch('system_info.collectors.storage.psutil.disk_partitions',return_value=[]),patch('system_info.collectors.storage.glob.glob',return_value=[]):
            result=StorageCollector().collect()
        visible=[r for r in result.records if not r.get('advanced')]
        disks=[r for r in visible if r['kind']=='disk']
        self.assertEqual(len(disks),1);self.assertEqual(disks[0]['drive_type'],'NVMe SSD')
        self.assertFalse(any(r['kind']=='virtual_disk' for r in visible))
        self.assertIn('PM991a',visible[0]['name']);self.assertIn('1.02 TB',visible[0]['capacity'])
    def test_gpu_one_adapter_seven_connectors(self):
        out='0000:00:02.0 VGA compatible controller [0300]: Intel Iris Xe Graphics [8086:9a49]\n\tKernel driver in use: i915'
        connectors=['/sys/class/drm/card0-'+c for c in ['DP-1','DP-2','DP-3','HDMI-A-1','HDMI-A-2','HDMI-A-3','eDP-1']]
        def read(path):
            if path.endswith('/status'):return 'connected' if 'eDP' in path else 'disconnected'
            if path.endswith('/modes'):return '1920x1080\n1920x1080' if 'eDP' in path else None
            return None
        with patch('system_info.collectors.gpu.run_cmd',return_value=out),patch('system_info.collectors.gpu.read_file',side_effect=read),patch('system_info.collectors.gpu.glob.glob',side_effect=lambda pattern:connectors if pattern.endswith('-*') else []),patch('system_info.collectors.gpu.edid_details',return_value={}):
            result=GpuCollector().collect()
        self.assertEqual(sum(r['kind']=='gpu' for r in result.records),1)
        self.assertEqual(sum(r['kind']=='display' for r in result.records),1)
        self.assertEqual(sum(r.get('advanced',False) for r in result.records),6)
        self.assertEqual(next(r for r in result.records if r['kind']=='display')['supported_modes'],['1920x1080'])
    def test_wifi_rate_and_escaped_ssid(self):
        with patch('system_info.collectors.network.run_cmd',return_value='Connected to xx\n\tSSID: Home\n\tsignal: -50 dBm\n\ttx bitrate: 866.7 MBit/s\n\trx bitrate: 780.0 MBit/s'):
            self.assertEqual(wifi_link('wlan0')['transmit_link_rate'],'866.7 MBit/s')
        self.assertEqual(nm_fields(r'yes:Home\:WiFi:540 Mbit/s:67'),['yes','Home:WiFi','540 Mbit/s','67'])
    def test_advertised_rate_not_mislabelled(self):
        with patch('system_info.collectors.network.run_cmd',side_effect=['','yes:Home:540 Mbit/s:67']):
            result=wifi_link('wlan0');self.assertNotIn('transmit_link_rate',result);self.assertEqual(result['advertised_AP_rate'],'540 Mbit/s')
    def test_smart_metrics(self):
        health=health_fields({'smart_status':{'passed':False},'temperature':{'current':44},'nvme_smart_health_information_log':{'percentage_used':5,'media_errors':2}})
        self.assertEqual(health['SMART health'],'FAILED');self.assertEqual(health['Rated endurance consumed (%)'],5)
    def test_authorized_read_is_fixed_command(self):
        with patch('system_info.protected.trusted_tool',side_effect=['/usr/bin/pkexec','/usr/bin/cat']),patch('system_info.protected.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=smbios_fixture())) as run:
            result=read_protected('firmware')
            self.assertEqual(run.call_args.args[0],['/usr/bin/pkexec','/usr/bin/cat','/sys/firmware/dmi/tables/DMI'])
            self.assertNotIn('shell',run.call_args.kwargs);self.assertEqual(len(result),5)
    def test_smart_command_injection_rejected(self):
        with patch('system_info.protected.trusted_tool',return_value='/usr/bin/pkexec'):
            with self.assertRaises(RuntimeError):read_protected('smart','/dev/sda; echo bad')
    def test_overview_physical_counts(self):
        snap=SystemSnapshot();g=CategoryResult('gpu','Graphics');g.add_record({'kind':'gpu','name':'Intel Iris Xe','driver':'i915'});g.add_record({'kind':'display','name':'Built in'});snap.add(g)
        st=CategoryResult('storage','Storage');st.add_record({'kind':'disk','name':'Samsung','drive_type':'NVMe SSD','capacity':'1 TB'});st.add_record({'kind':'virtual_disk','name':'loop0','advanced':True});snap.add(st)
        fields={f.label:f.value for f in overview(snap).fields};self.assertEqual(fields['Graphics adapters'],1);self.assertEqual(fields['Installed storage'],1)

if __name__=='__main__':unittest.main()
