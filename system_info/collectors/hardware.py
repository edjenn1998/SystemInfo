"""Sensor readings, with duplicate readings retained only in technical view."""
import glob
from .base import Collector, read_file
class HardwareCollector(Collector):
    name='hardware';title='Sensors'
    def collect(self):
        r=self.new_result();items=[]
        for hw in sorted(glob.glob('/sys/class/hwmon/hwmon*')):
            chip=read_file(hw+'/name') or 'Unknown sensor'
            for pattern,scale,unit in [('temp*_input',1000,'°C'),('fan*_input',1,'RPM'),('power*_average',10**6,'W')]:
                for f in sorted(glob.glob(hw+'/'+pattern)):
                    raw=read_file(f)
                    try:value=round(float(raw)/scale,2)
                    except (ValueError,TypeError):continue
                    base=f.rsplit('_',1)[0];label=read_file(base+'_label') or base.rsplit('/',1)[-1]
                    friendly='CPU' if chip in ('coretemp','k10temp','zenpower') else 'NVMe drive' if chip=='nvme' else 'Wi-Fi' if chip.startswith('iwlwifi') else chip
                    rec={'kind':'sensor','name':friendly+' • '+label,'chip':chip,'label':label,'value':value,'unit':unit}
                    limit=read_file(base+'_crit')
                    if limit and unit=='°C':
                        try:rec['critical_limit_C']=round(float(limit)/1000,1)
                        except ValueError:pass
                    items.append(rec)
        # Dell exposes some of the same readings through two drivers. Keep the
        # readable dell_ddv labels primary; retain dell_smm in technical view.
        has_ddv=any(i['chip']=='dell_ddv' for i in items)
        for rec in items:
            if has_ddv and rec['chip']=='dell_smm':rec['advanced']=True
            r.add_record(rec)
        r.add('Sensor readings available',sum(not i.get('advanced') for i in items))
        r.note='Values are reported by hardware drivers. A fan at 0 RPM can be stopped normally; a label such as “HDD” is a firmware sensor name, not proof of an installed HDD.'
        if not items:r.note='No hardware sensors are visible to this process.'
        return r
