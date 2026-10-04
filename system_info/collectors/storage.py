"""Installed drives first; virtual disks and partitions are technical details."""
import glob
import json
import re
from pathlib import Path
import psutil
from .base import Collector, run_cmd, read_file, which
from ..inventory import capacity_label, meaningful, numeric
from ..filesystems import parse_fstab, match_fstab, device_aliases

def smart_report(path, context):
    data=context.get('smart_reports',{}).get(path)
    if data is None and which('smartctl'):
        # smartctl uses a bitmask status: a nonzero code may still contain a valid health report.
        import subprocess, os
        try:
            proc=subprocess.run(['smartctl','-j','-a',path],capture_output=True,text=True,timeout=6,env={**os.environ,'LC_ALL':'C'})
            data=json.loads(proc.stdout)
        except (OSError,ValueError,subprocess.TimeoutExpired):return {}
    if not isinstance(data,dict):return {}
    return data

def health_fields(data):
    if not data:return {}
    rec={};status=data.get('smart_status',{}).get('passed')
    if status is not None:rec['SMART health']='Passed' if status else 'FAILED'
    for key,value in [('Temperature (°C)',data.get('temperature',{}).get('current')),('Power-on hours',data.get('power_on_time',{}).get('hours'))]:
        if value is not None:rec[key]=value
    nvme=data.get('nvme_smart_health_information_log',{})
    for source,key in [('percentage_used','Rated endurance consumed (%)'),('media_errors','Media / data errors'),('critical_warning','NVMe critical warning flags'),('available_spare','Available spare (%)')]:
        if source in nvme:rec[key]=nvme[source]
    attrs={a.get('id'):a for a in data.get('ata_smart_attributes',{}).get('table',[])}
    for ident,label in [(5,'Reallocated sectors'),(197,'Pending sectors'),(198,'Uncorrectable sectors')]:
        value=attrs.get(ident,{}).get('raw',{}).get('value')
        if value is not None:rec[label]=value
    return rec

class StorageCollector(Collector):
    name='storage';title='Storage'
    def _lsblk(self):
        out=run_cmd(['lsblk','-J','-b','-o','NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,PARTUUID,SERIAL,MODEL,VENDOR,ROTA,RO,LOG-SEC,PHY-SEC,TRAN,MOUNTPOINT'])
        try:return json.loads(out or '{}').get('blockdevices',[])
        except ValueError:return []
    def _flatten_devices(self,devices,parent=None):
        flat=[]
        for dev in devices:
            dev=dict(dev);kids=dev.pop('children',[]);dev['parent']=parent;flat.append(dev)
            flat.extend(self._flatten_devices(kids,dev.get('path')))
        return flat
    def _sys_disks(self):
        devices=[]
        for p in sorted(glob.glob('/sys/class/block/*')):
            name=p.rsplit('/',1)[-1]
            if name.startswith(('loop','ram','zram','dm-','md')):continue
            is_partition=Path(p+'/partition').exists()
            size=numeric(p+'/size')
            devices.append({'name':name,'path':'/dev/'+name,'type':'part' if is_partition else 'disk',
                'parent':'/dev/'+Path(p).resolve().parent.name if is_partition else None,
                'size':int(size*512) if size is not None else None,'model':read_file(p+'/device/model'),
                'vendor':read_file(p+'/device/vendor'),'rota':read_file(p+'/queue/rotational')=='1',
                'tran':'nvme' if name.startswith('nvme') else 'usb' if '/usb' in str(Path(p).resolve()) else None})
        return devices
    def collect(self):
        r=self.new_result();all_devices=self._flatten_devices(self._lsblk())
        if not all_devices:
            all_devices=self._sys_disks();r.note='lsblk is unavailable; using the kernel drive inventory.'
        aliases=device_aliases();fstab=parse_fstab(read_file('/etc/fstab'))
        for dev in all_devices:
            for key,value in aliases.get(dev.get('path'),{}).items():
                if not dev.get(key):dev[key]=value
        physical=[d for d in all_devices if d.get('type') in ('disk','rom') and not d.get('name','').startswith(('loop','ram','zram','nbd'))]
        r.add('Installed drives detected',len(physical))
        r.add('Software loop devices',sum(d.get('type')=='loop' for d in all_devices),advanced=True)
        for d in physical:
            name=d.get('name','');transport=d.get('tran') or ('nvme' if name.startswith('nvme') else None)
            drive_type='NVMe SSD' if transport=='nvme' else ('SATA ' if transport=='sata' else 'USB ' if transport=='usb' else '')+('HDD' if d.get('rota') else 'SSD / flash storage')
            if d.get('type')=='rom':drive_type='Optical drive'
            rec={'kind':'disk','name':d.get('model','').strip() if isinstance(d.get('model'),str) and d.get('model').strip() else name,
                'model':meaningful(d.get('model')),'device':d.get('path'),'drive_type':drive_type,'connection':transport.upper() if transport else 'Not reported',
                'capacity':capacity_label(d.get('size')),'size_bytes':d.get('size'),'uuid':d.get('uuid'),'partuuid':d.get('partuuid'),
                'filesystem':d.get('fstype'),'filesystem_label':d.get('label'),'fstab_entries':match_fstab(d,fstab),'serial':meaningful(d.get('serial')),'read_only':d.get('ro')}
            controller=next((p for p in glob.glob('/sys/class/nvme/nvme*') if name.startswith(p.rsplit('/',1)[-1]+'n')),None)
            if controller:
                rec.update({'firmware':read_file(controller+'/firmware_rev'),'controller_state':read_file(controller+'/state')})
            health=health_fields(smart_report(d.get('path'),self.context)) if d.get('path') else {}
            rec.update(health)
            if health and d.get('path') in self.context.get('smart_reports',{}):
                rec['health_read_note']='From the last protected health read this session; use Read drive health again to refresh these values'
            if not health:rec['health_note']='SMART details need smartctl and drive read permission; use “Read drive health” if available.'
            r.add_record({k:v for k,v in rec.items() if v is not None})
        for d in all_devices:
            if d in physical:continue
            primary=d.get('type') in ('part','crypt','lvm','raid0','raid1','raid5','raid6','raid10','md','mpath')
            rec={'kind':'partition' if d.get('type')=='part' else 'volume' if primary else 'virtual_disk',
                'name':d.get('name'),'device':d.get('path'),'parent':d.get('parent'),
                'capacity':capacity_label(d.get('size')),'filesystem':d.get('fstype'),'mountpoint':d.get('mountpoint'),
                'uuid':d.get('uuid'),'partuuid':d.get('partuuid'),'filesystem_label':d.get('label'),
                'fstab_entries':match_fstab(d,fstab),'advanced':not primary}
            if primary and not rec['uuid']:
                rec['uuid_note']='No UUID reported in the system inventory; this partition may have no filesystem or need read permission'
            r.add_record(rec)
        for part in psutil.disk_partitions(all=False):
            if part.device.startswith('/dev/loop') or part.fstype in ('squashfs','tmpfs','overlay'):continue
            try:usage=psutil.disk_usage(part.mountpoint)
            except OSError:continue
            r.add_record({'kind':'filesystem','name':part.mountpoint,'device':part.device,'mountpoint':part.mountpoint,
                'filesystem':part.fstype,'capacity':capacity_label(usage.total),'used':capacity_label(usage.used),'free':capacity_label(usage.free),'used_percent':usage.percent,'advanced':True})
        if not physical:r.note='No physical drives are visible to this process. Virtual machines and restricted containers may expose a limited inventory.'
        return r
