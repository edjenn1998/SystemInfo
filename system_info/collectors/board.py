"""Computer / board identity and firmware, with explicit protected-data access."""
import glob
import os
from .base import Collector, read_file
from ..inventory import meaningful, get_dmi
DMI='/sys/devices/virtual/dmi/id'
_FIELDS=[('sys_vendor','System manufacturer',1,'Manufacturer'),('product_name','Computer model',1,'Product Name'),
 ('product_family','Product family',1,'Family'),('product_serial','Service tag / system serial',1,'Serial Number'),
 ('product_uuid','System UUID',1,'UUID'),('board_vendor','Board manufacturer',2,'Manufacturer'),
 ('board_name','Motherboard model',2,'Product Name'),('board_version','Motherboard revision',2,'Version'),
 ('board_serial','Motherboard serial',2,'Serial Number'),('bios_vendor','BIOS manufacturer',0,'Vendor'),
 ('bios_version','BIOS version',0,'Version'),('bios_date','BIOS release date',0,'Release Date'),
 ('bios_release','BIOS revision',0,'BIOS Revision'),('chassis_vendor','Chassis manufacturer',3,'Manufacturer')]
_CHASSIS={'3':'Desktop','4':'Low-profile desktop','6':'Mini tower','7':'Tower','8':'Portable','9':'Laptop','10':'Notebook','13':'All-in-one','14':'Sub-notebook','23':'Rack server','30':'Tablet','31':'Convertible','32':'Detachable','35':'Mini PC'}
class BoardCollector(Collector):
    name='board';title='Motherboard / BIOS'
    def collect(self):
        r=self.new_result();sections=get_dmi(self.context);protected=[]
        by_type={s['type']:s['fields'] for s in sections}
        for fname,label,typ,key in _FIELDS:
            value=meaningful(read_file(DMI+'/'+fname)) or meaningful(by_type.get(typ,{}).get(key))
            if value:r.add(label,value,advanced=label=='System UUID')
            elif 'serial' in fname or 'uuid' in fname:protected.append(label)
        code=read_file(DMI+'/chassis_type')
        chassis=_CHASSIS.get(code) or meaningful(by_type.get(3,{}).get('Type'))
        if chassis:r.add('Computer form factor',chassis)
        uefi=os.path.isdir('/sys/firmware/efi')
        r.add('Boot mode','UEFI' if uefi else 'Legacy BIOS (or EFI information is not exposed)')
        if uefi:
            secure=None
            for f in glob.glob('/sys/firmware/efi/efivars/SecureBoot-*'):
                try:
                    raw=open(f,'rb').read()
                    if len(raw)>4:secure=bool(raw[4])
                except OSError:pass
            r.add('Secure Boot','Enabled' if secure is True else 'Disabled' if secure is False else 'Firmware variable is not readable')
        if protected:r.note='Protected identifiers can be read with “Read memory / BIOS details”. Blank or unspecified firmware strings are omitted.'
        if not any(f.label=='Computer model' for f in r.fields):r.note='Computer identity is not exposed. Read memory / BIOS details to try the firmware inventory.'
        return r
