"""Memory inventory plus usage; bank counts are firmware devices, not upgrade slots."""
import glob
import re
import psutil
from .base import Collector, read_file
from ..inventory import get_dmi, meaningful, clean_fields

UNAVAILABLE_HELP = (
    'Installed physical RAM minus Linux MemTotal. This can include firmware allocations, '
    'integrated GPU reservations, memory mapping exclusions, and other system-level '
    'reservations; it is not a measurement of hardware reservations alone. '
    'The result depends on the accuracy and completeness of SMBIOS.'
)
TIMING_HELP = (
    'No validated portable read-only Linux interface for active AMD/Intel memory '
    'controller timings is implemented. SMBIOS does not provide these timings, and '
    'SPD/XMP/EXPO profiles describe advertised settings, not necessarily active settings. '
    'Firmware authorization does not unlock active timings. Controller registers and '
    'memory buses are not probed.'
)


def smbios_capacity_bytes(value):
    """SMBIOS size units are binary, even when dmidecode spells them MB/GB.

    This parser is deliberately specific to SMBIOS, not decimal disk capacities.
    """
    match = re.fullmatch(r'(\d+)\s*(kB|KiB|MB|MiB|GB|GiB|TB|TiB)', str(value), re.I)
    if not match:
        return None
    power = {'k': 1, 'm': 2, 'g': 3, 't': 4}[match[2][0].lower()]
    return int(match[1]) * 1024**power


def installed_capacity(count, modules):
    """Return (complete installed bytes or None, known partial bytes)."""
    complete = bool(count and len(modules) == count)
    capacity = 0
    for mod in modules:
        if mod.get('populated') is False:
            continue
        size = smbios_capacity_bytes(mod.get('size'))
        if mod.get('populated') is not True or not size:
            complete = False
        else:
            capacity += size
    return (capacity if complete and capacity else None), capacity


def memory_usage(meminfo, vm):
    """Byte quantities; Linux /proc/meminfo kB means 1024 bytes.

    psutil supplies the kernel-compatible available-memory estimate on older
    kernels without MemAvailable. Never use installed capacity as the denominator.
    """
    total = meminfo.get('MemTotal', 0) * 1024
    total = total if total > 0 else None
    available = meminfo.get('MemAvailable')
    available = available * 1024 if available is not None else vm.available
    if total is None:
        return None, None, None, None
    available = min(total, max(0, available))
    used = total - available
    return total, used, available, round(used / total * 100, 1)


def unavailable_memory(installed, usable):
    """Withhold inconsistent firmware values rather than inventing zero."""
    if installed is None or usable is None or installed < usable:
        return None
    return max(0, installed - usable)

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
    has_arrays = any(s['type'] == 16 for s in sections)
    devices=[s['fields'] for s in sections if s['type']==17 and
             (not has_arrays or s['fields'].get('Array Handle','').lower() in handles)]
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
    # An absent array count cannot establish that the module list is complete.
    count=count or None
    populated=sum(m['populated'] is True for m in modules) if modules and all(m['populated'] is not None for m in modules) else None
    empty=sum(m['populated'] is False for m in modules) if modules and all(m['populated'] is not None for m in modules) else None
    if count is not None and len(modules)!=count: populated=empty=None
    onboard=any((m.get('form_factor') or '').lower() in ('chip','row of chips','die') for m in modules)
    for module, device in zip(modules, devices):
        array = next((s['fields'] for s in array_sections
                      if s.get('handle', '').lower() == device.get('Array Handle', '').lower()), {})
        correction = meaningful(array.get('Error Correction Type'))
        # Array-level ECC reporting alone is not proof of a module's ECC wiring.
        widths = [re.fullmatch(r'(\d+) bits', device.get(key, ''))
                  for key in ('Total Width', 'Data Width')]
        if correction in ('Single-bit ECC', 'Multi-bit ECC') and all(widths):
            total, data = (int(w[1]) for w in widths)
            if total > data > 0:
                module['ecc_capability'] = f'ECC-capable (firmware: {correction}; not proof ECC is enabled)'
        if 'ecc_capability' not in module:
            module['ecc_capability'] = 'Not available'
        if correction:
            module['array_error_correction'] = correction
        module['source'] = 'SMBIOS firmware inventory'
    return count,populated,empty,onboard,modules

class MemoryCollector(Collector):
    name='memory';title='Memory'
    def _dimm_slots(self):
        modules=[]
        for path in sorted(glob.glob('/sys/devices/system/edac/mc/mc*/dimm[0-9]*')):
            size = read_file(path+'/size') or read_file(path+'/dimm_size')
            if size is None or not size.isdigit() or int(size) <= 0:
                continue
            modules.append({'kind':'memory_module',
                'name':read_file(path+'/dimm_label') or path.rsplit('/',1)[-1],
                'size':size, 'location':read_file(path+'/dimm_location'),
                'memory_type':read_file(path+'/dimm_mem_type'),
                'edac_mode':read_file(path+'/dimm_edac_mode'),
                'source':'EDAC (size in MiB); labels may be assigned by userspace'})
        return modules
    def collect(self):
        r=self.new_result();vm=psutil.virtual_memory();sw=psutil.swap_memory()
        mi = _parse_meminfo()
        usable, ram_used, available, percent = memory_usage(mi, vm)
        count,used,empty,onboard,modules=memory_inventory(get_dmi(self.context))
        installed, partial = installed_capacity(count, modules)
        # Validate counts per array as well as the aggregate (two errors can cancel).
        sections = get_dmi(self.context)
        device_handles = [s['handle'].lower() for s in sections if s['type'] == 17 and s.get('handle')]
        if len(device_handles) != len(set(device_handles)):
            installed = None
        for array in (s for s in sections if s['type'] == 16 and s['fields'].get('Use', 'System Memory') == 'System Memory'):
            expected = array['fields'].get('Number Of Devices', '')
            actual = sum(s['type'] == 17 and s['fields'].get('Array Handle', '').lower() == array.get('handle', '').lower() for s in sections)
            if not expected.isdigit() or int(expected) != actual:
                installed = None
        difference = unavailable_memory(installed, usable)
        def gib(label, value, section='System Memory', tooltip=None):
            r.add(label, round(value / 1024**3, 2) if value is not None else 'Not available',
                  'GiB' if value is not None else None, section=section, tooltip=tooltip)
        gib('Installed RAM', installed, tooltip='Sum of populated system-memory SMBIOS devices, only when the firmware inventory is complete. Firmware can be inaccurate; this is not Linux usable RAM. SMBIOS MB/GB are binary units, displayed here as GiB.')
        gib('Usable RAM', usable, tooltip='Linux MemTotal from /proc/meminfo: RAM available to the kernel, excluding memory unavailable to Linux. Linux kB means KiB (1024 bytes).')
        gib('Unavailable to Linux', difference, tooltip=UNAVAILABLE_HELP)
        if installed is not None and usable is not None and installed < usable:
            r.add('Capacity validation', 'Firmware installed capacity is below Linux usable RAM; unavailable memory cannot be calculated', section='System Memory')
        elif installed is None:
            r.add('Capacity validation', 'Complete physical capacity not available from SMBIOS; unavailable memory cannot be calculated', section='System Memory')
        gib('RAM in use', ram_used, tooltip='Usable minus available RAM; reclaimable caches count as available, rather than in use.')
        gib('RAM available', available, tooltip='MemAvailable from /proc/meminfo, or the psutil estimate on older kernels. Includes reclaimable caches; not just completely free RAM.')
        r.add('RAM usage', percent if percent is not None else 'Not available', '%' if percent is not None else None, section='System Memory')
        kernel_modules=self._dimm_slots() if not modules else []
        status=self.context.get('dmi_status','authorization_required')
        if count is not None:
            inventory_status='Firmware inventory read successfully'
        elif modules:inventory_status='Partial firmware module inventory; complete bank count is not reported'
        elif kernel_modules:inventory_status='Limited kernel inventory; total/empty bank count is not reported'
        elif status=='authorization_required':inventory_status='Authorization needed — click Read memory / BIOS details'
        elif status=='interface_absent':inventory_status='Firmware interface absent on this machine; an installed dmidecode may provide a fallback'
        elif status=='not_reported' or get_dmi(self.context):inventory_status='Firmware read, but it does not report RAM banks'
        else:inventory_status='Firmware inventory could not be read — try Read memory / BIOS details'
        r.add('Memory inventory status',inventory_status,section='Memory Configuration')
        if count is not None:r.add('Memory banks reported',count,section='Memory Configuration',tooltip='Firmware memory devices, possibly soldered chips. Not a count of physically accessible or upgradeable slots.')
        if count is not None:
            r.add('Banks populated',used if used is not None else 'Firmware inventory incomplete',section='Memory Configuration')
            r.add('Banks empty',empty if empty is not None else 'Firmware inventory incomplete',section='Memory Configuration')
            r.add('Memory layout','Onboard / soldered chips' if onboard else 'See reported form factors below; firmware banks do not prove upgradeable slots',section='Memory Configuration')
        if installed is None and partial:
            gib('Reported module capacity (incomplete inventory)', partial)
        for label,key in [('Memory type','memory_type'),('Memory manufacturer','manufacturer'),('Configured speed','configured_speed'),('Rated speed (firmware maximum)','rated_speed')]:
            values=sorted({m[key] for m in modules if m.get(key) and m.get('populated') is True})
            tooltip = ('Configured speed is the firmware-reported operating transfer rate, not a live measurement. Rated speed is the firmware-reported module maximum, not the controller maximum or an active timing profile.'
                       if key in ('configured_speed', 'rated_speed') else 'Reported by populated SMBIOS system-memory devices; mixed module values are listed separately.')
            r.add(label,values or 'Not available',section='Memory Configuration',tooltip=tooltip)
        for label in ('CAS Latency (tCL)', 'RAS to CAS Delay (tRCD)', 'Row Precharge (tRP)', 'Active to Precharge Delay (tRAS)', 'Command Rate'):
            r.add(label,'Not available',section='Memory Configuration',tooltip=TIMING_HELP)
        r.add('Active timings status','Not available — no validated safe interface; SPD profiles are not active timings',section='Memory Configuration',tooltip=TIMING_HELP)
        # Bank names, ranks and firmware device counts are not channel topology.
        for mod in modules or kernel_modules:
            if mod.get('populated') is False:
                mod = {**mod, 'advanced': True}
            r.add_record(clean_fields(mod))
        gib('Swap total',sw.total,'Swap');gib('Swap used',sw.used,'Swap');gib('Swap available',sw.free,'Swap')
        r.add('Swap usage',sw.percent,'%',section='Swap')
        for attr in ['free','active','inactive','buffers','cached']:
            value=getattr(vm,attr,None)
            if value is not None:r.add(attr.capitalize(),round(value/1024**3,2),'GiB',advanced=True)
        for key in ['Shmem','Dirty','Writeback','Slab','SReclaimable','SUnreclaim','KernelStack','PageTables','CommitLimit','Committed_AS','HugePages_Total','Hugepagesize']:
            if key in mi:r.add(key,mi[key],'pages' if key=='HugePages_Total' else 'kB',advanced=True)
        r.note='Bank counts describe firmware memory devices, which may be soldered chips. They are not a count of user-replaceable slots.'
        return r
