"""Physical GPU adapters and displays; display connectors are not extra GPUs."""
import glob
import os
import re
from pathlib import Path
from .base import Collector, read_file, run_cmd
from ..inventory import numeric

def _parse_lspci_gpus(text):
    result=[];current=None
    for line in text.splitlines():
        if line and not line[0].isspace():
            current=None
            if not re.search(r'\b(VGA(?: compatible)?|3D|Display) controller\b',line,re.I):continue
            match=re.match(r'(\S+)\s+.*?:\s+(.*?)\s*\[([0-9a-f]{4}):([0-9a-f]{4})\]',line,re.I)
            if not match:continue
            current={'kind':'gpu','slot':match[1],'name':match[2].strip(),'vendor_id':match[3],'device_id':match[4]};result.append(current)
        elif current is not None:
            key,sep,value=line.strip().partition(':')
            mapping={'Kernel driver in use':'driver','Kernel modules':'modules','Subsystem':'subsystem'}
            if sep and key in mapping:current[mapping[key]]=value.strip()
    return result

def edid_details(path):
    try:data=Path(path).read_bytes()
    except OSError:return {}
    if len(data)<128 or data[:8]!=b'\x00\xff\xff\xff\xff\xff\xff\x00':return {}
    code=int.from_bytes(data[8:10],'big');vendor=''.join(chr(64+((code>>shift)&31)) for shift in (10,5,0))
    rec={'monitor_manufacturer_code':vendor}
    for start in range(54,126,18):
        block=data[start:start+18]
        if len(block)==18 and block[:3]==b'\x00\x00\x00':
            if block[3] in (0xfc,0xff):
                value=block[5:].decode('ascii',errors='replace').strip('\x00\n ')
                rec['monitor_model' if block[3]==0xfc else 'monitor_serial']=value
    if data[21] and data[22]:rec['panel_size_cm']=f'{data[21]} × {data[22]}'
    return rec

def x11_modes():
    if os.environ.get('XDG_SESSION_TYPE')!='x11':return {}
    modes={};current=None
    for line in (run_cmd(['xrandr','--current']) or '').splitlines():
        match=re.match(r'(\S+) connected(?: primary)? (\d+x\d+)\+',line)
        if match:modes[match[1]]=match[2];current=match[1]
    return modes

class GpuCollector(Collector):
    name='gpu';title='Graphics / Displays'
    def collect(self):
        r=self.new_result();gpus=_parse_lspci_gpus(run_cmd(['lspci','-nnk']) or '')
        cards=[]
        for card in sorted(glob.glob('/sys/class/drm/card[0-9]*')):
            if '-' in card.rsplit('/',1)[-1]:continue
            device=Path(card+'/device');slot=device.resolve().name
            gpu=next((g for g in gpus if g['slot']==slot or g['slot']==slot.removeprefix('0000:')),None)
            if gpu is None and device.exists():
                gpu={'kind':'gpu','name':read_file(card+'/device/uevent') or 'Graphics adapter','slot':slot}
                driver=(device/'driver').resolve().name if (device/'driver').exists() else None
                gpu['name']='Graphics adapter ('+(driver or 'driver not reported')+')';gpu['driver']=driver;gpus.append(gpu)
            if gpu:
                cards.append((card,gpu));gpu['drm_device']=card.rsplit('/',1)[-1]
                for key,label,divisor in [('mem_info_vram_total','dedicated_memory_GiB',1024**3),('gpu_busy_percent','utilization_percent',1)]:
                    value=numeric(card+'/device/'+key)
                    if value is not None:gpu[label]=round(value/divisor,2)
                if re.search(r'\b(Iris|UHD|HD Graphics)\b',gpu['name'],re.I):gpu['memory_type']='Integrated graphics — shares system RAM'
                elif 'dedicated_memory_GiB' not in gpu:gpu['memory_note']='Dedicated memory capacity is not exposed by this driver'
        r.add('Installed GPU adapters',len(gpus))
        for gpu in gpus:r.add_record(gpu)
        current_modes=x11_modes();connected=0
        for connector in sorted(glob.glob('/sys/class/drm/card[0-9]*-*')):
            name=connector.rsplit('/',1)[-1]
            if 'Writeback' in name:continue
            status=read_file(connector+'/status')
            if status is None:continue
            card=name.split('-',1)[0];port=name[len(card)+1:];is_connected=status=='connected'
            if is_connected:connected+=1
            modes=list(dict.fromkeys((read_file(connector+'/modes') or '').splitlines()))
            rec={'kind':'display' if is_connected else 'display_connector','name':('Built-in display' if port.startswith(('eDP','LVDS','DSI')) else 'External display')+' • '+port,
                'connector':port,'GPU_device':card,'status':status,'enabled':read_file(connector+'/enabled'),
                'current_resolution':current_modes.get(port) if is_connected else None,'preferred_reported_mode':modes[0] if modes else None,
                'supported_modes':modes,'advanced_keys':['supported_modes'],'advanced':not is_connected}
            if is_connected:
                rec.update(edid_details(connector+'/edid'))
                if not rec['current_resolution']:rec['resolution_note']='Current desktop resolution is not exposed here; preferred/supported modes are listed separately'
            r.add_record({k:v for k,v in rec.items() if v is not None})
        r.add('Connected displays',connected)
        if not gpus:r.note='No GPU adapter is visible; the PCI inventory or driver data may be unavailable.'
        return r
