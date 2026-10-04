"""Memory inventory plus usage; bank counts are firmware devices, not upgrade slots."""
import glob
import re
import psutil
from .base import Collector, read_file
from ..inventory import get_dmi, meaningful, clean_fields

def _parse_meminfo():
    out={}
    for line in (read_file('/proc/meminfo') or '').splitlines():
        key,_,rest=line.partition(':');parts=rest.split()
        if parts and parts[0].isdigit(): out[key.strip()]=int(parts[0])
    return out

def memory_inventory(sections):
    array_sections=[s for s in sections if s['type']==16 and s['fields'].get('Use','System Memory')=='System Memory']
    arrays=[s['fields'] for s in array_sections]
    handles={s.get('handle','').lower() for s in array_sections if s.get('handle')}
    devices=[s['fields'] for s in sections if s['type']==17 and (not handles or s['fields'].get('Array Handle','').lower() in handles)]
    modules=[]
    for d in devices:
        size=d.get('Size','Unknown');lower=size.lower()
        populated=False if lower in ('no module installed','not installed','0 mb','0 gb') else None if lower in ('unknown','not specified','') else True
        modules.append({'kind':'memory_module','name':meaningful(d.get('Locator')) or 'Memory device',
            'populated':populated,'size':size,'bank':meaningful(d.get('Bank Locator')),
            'manufacturer':meaningful(d.get('Manufacturer')),'part_number':meaningful(d.get('Part Number')),
            'serial':meaningful(d.get('Serial Number')),'memory_type':meaningful(d.get('Type')),
            'form_factor':meaningful(d.get('Form Factor')),'rated_speed':meaningful(d.get('Speed')),
            'configured_speed':meaningful(d.get('Configured Memory Speed') or d.get('Configured Clock Speed')),
            'rank':meaningful(d.get('Rank')),'data_width':meaningful(d.get('Data Width')),
            'total_width':meaningful(d.get('Total Width')),'voltage':meaningful(d.get('Configured Voltage'))})
    count=sum(int(a['Number Of Devices']) for a in arrays if a.get('Number Of Devices','').isdigit())
    count=count or len(modules) or None
    populated=sum(m['populated'] is True for m in modules) if modules and all(m['populated'] is not None for m in modules) else None
    empty=sum(m['populated'] is False for m in modules) if modules and all(m['populated'] is not None for m in modules) else None
    if count is not None and len(modules)!=count: populated=empty=None
    onboard=any((m.get('form_factor') or '').lower() in ('row of chips','die') for m in modules)
    return count,populated,empty,onboard,modules

class MemoryCollector(Collector):
    name='memory';title='Memory'
    def _dimm_slots(self):
        modules=[]
        for f in glob.glob('/sys/devices/system/edac/mc/mc*/dimm*/dimm_label'):
            path=f.rsplit('/',1)[0];label=read_file(f)
            if label: modules.append({'kind':'memory_module','name':label,'size':read_file(path+'/dimm_size'),'location':read_file(path+'/dimm_location'),'source':'EDAC (size in MiB)'})
        return modules
    def collect(self):
        r=self.new_result();vm=psutil.virtual_memory();sw=psutil.swap_memory()
        r.add('Usable RAM',round(vm.total/1024**3,2),'GiB')
        r.add('RAM in use',round((vm.total-vm.available)/1024**3,2),'GiB')
        r.add('RAM available',round(vm.available/1024**3,2),'GiB')
        r.add('RAM usage',vm.percent,'%')
        count,used,empty,onboard,modules=memory_inventory(get_dmi(self.context))
        kernel_modules=self._dimm_slots() if not modules else []
        status=self.context.get('dmi_status','authorization_required')
        if count is not None:
            inventory_status='Firmware inventory read successfully'
        elif kernel_modules:inventory_status='Limited kernel inventory; total/empty bank count is not reported'
        elif status=='authorization_required':inventory_status='Authorization needed — click Read memory / BIOS details'
        elif status=='interface_absent':inventory_status='Firmware interface absent on this machine; an installed dmidecode may provide a fallback'
        elif status=='not_reported' or get_dmi(self.context):inventory_status='Firmware read, but it does not report RAM banks'
        else:inventory_status='Firmware inventory could not be read — try Read memory / BIOS details'
        r.add('Memory inventory status',inventory_status)
        if count is not None:r.add('Memory banks reported',count)
        if count is not None:
            capacity=0;known_capacity=True
            for mod in modules:
                if mod.get('populated') is False:continue
                match=re.fullmatch(r'(\d+)\s+(kB|MB|GB|TB)',mod.get('size',''),re.I)
                if not match:known_capacity=False;break
                capacity+=int(match[1])*{'kb':1024,'mb':1024**2,'gb':1024**3,'tb':1024**4}[match[2].lower()]
            if known_capacity and capacity:r.add('Installed RAM (firmware)',round(capacity/1024**3,2),'GiB')
            r.add('Banks populated',used if used is not None else 'Firmware inventory incomplete')
            r.add('Banks empty',empty if empty is not None else 'Firmware inventory incomplete')
            r.add('Memory layout','Onboard / soldered chips' if onboard else 'See reported form factors below; firmware banks do not prove upgradeable slots')
            for label,key in [('Memory type','memory_type'),('Memory manufacturer','manufacturer'),('Configured speed','configured_speed')]:
                values=sorted({m[key] for m in modules if m.get(key) and m.get('populated') is True})
                if values:r.add(label,values)
        r.add('Memory timings (CL / tRCD / tRP / tRAS)','Live timing values are not supported by this app yet; firmware authorization does not unlock them')
        for mod in modules or kernel_modules:r.add_record(clean_fields(mod))
        r.add('Swap total',round(sw.total/1024**3,2),'GiB');r.add('Swap used',round(sw.used/1024**3,2),'GiB');r.add('Swap usage',sw.percent,'%')
        for attr in ['free','active','inactive','buffers','cached']:
            value=getattr(vm,attr,None)
            if value is not None:r.add(attr.capitalize(),round(value/1024**3,2),'GiB',advanced=True)
        mi=_parse_meminfo()
        for key in ['Shmem','Dirty','Writeback','Slab','SReclaimable','SUnreclaim','KernelStack','PageTables','CommitLimit','Committed_AS','HugePages_Total','Hugepagesize']:
            if key in mi:r.add(key,mi[key],'pages' if key=='HugePages_Total' else 'kB',advanced=True)
        r.note='Bank counts describe firmware memory devices, which may be soldered chips. They are not a count of user-replaceable slots.'
        return r
