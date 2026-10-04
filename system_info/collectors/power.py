"""Battery charge, capacity health, and power source in useful units."""
import glob
from .base import Collector, read_file
from ..inventory import numeric, meaningful

def battery_record(path):
    def num(name): return numeric(f'{path}/{name}')
    def text(name): return meaningful(read_file(f'{path}/{name}'))
    rec = {'kind':'battery', 'name':path.rsplit('/',1)[-1], 'model':text('model_name'),
           'manufacturer':text('manufacturer'), 'technology':text('technology'),
           'status':text('status'), 'charge_percent':num('capacity')}
    voltage, current, power = num('voltage_now'), num('current_now'), num('power_now')
    if voltage is not None: rec['voltage_V'] = round(voltage / 10**6, 2)
    if current is not None: rec['current_A'] = round(current / 10**6, 3)
    if power is not None: rec['power_W'] = round(abs(power) / 10**6, 2)
    elif voltage is not None and current is not None:
        rec['power_W'] = round(abs(voltage * current) / 10**12, 2)
    full, design, now = num('energy_full'), num('energy_full_design'), num('energy_now')
    basis = 'energy'
    if full is None or design is None or design <= 0:
        full, design, now = num('charge_full'), num('charge_full_design'), num('charge_now')
        basis = 'charge'
    # Do not compare charge to energy or mix design/nominal voltages for health.
    if full is not None and design is not None and design > 0:
        health = full / design * 100
        rec['health_percent'] = round(health, 1)
        rec['wear_percent'] = round(max(0,100-health),1)
        rec['health_basis'] = 'Reported full capacity / original design capacity'
    else: rec['health_note'] = 'Health cannot be calculated: design or full capacity is not reported.'
    if basis == 'energy':
        for k,v in [('full_capacity_Wh',full),('design_capacity_Wh',design),('remaining_energy_Wh',now)]:
            if v is not None: rec[k] = round(v/10**6,2)
    else:
        for k,v in [('full_capacity_mAh',full),('design_capacity_mAh',design),('remaining_charge_mAh',now)]:
            if v is not None: rec[k] = round(v/1000,1)
        # Original design energy is useful even when charge is used for health.
        v_design = num('voltage_min_design')
        if design is not None and v_design is not None:
            rec['design_energy_Wh_estimate'] = round(design*v_design/10**12,2)
    cycles = num('cycle_count')
    if cycles is not None:
        rec['cycle_count'] = int(cycles)
        if cycles == 0: rec['cycle_note'] = 'Firmware reports 0; some batteries do not maintain this count.'
    rate = rec.get('power_W',0)*10**6 if basis=='energy' else abs(current) if current is not None else None
    if rate is not None and rate > 0 and now is not None:
        remaining = now if rec['status']=='Discharging' else full-now if rec['status']=='Charging' and full is not None else None
        if remaining is not None and remaining >= 0:
            hours=remaining/abs(rate)
            rec['time_estimate'] = f'{int(hours)}h {int((hours%1)*60)}m '+('remaining' if rec['status']=='Discharging' else 'until full')
            rec['estimate_note'] = 'Estimate at the present discharge/charge rate; changes with workload.'
    return {k:v for k,v in rec.items() if v is not None}

class PowerCollector(Collector):
    name='power'
    title='Power / Battery'
    def collect(self):
        r=self.new_result();batteries=[];online=[]
        for path in sorted(glob.glob('/sys/class/power_supply/*')):
            kind=read_file(path+'/type')
            if kind=='Battery':
                if read_file(path+'/present')=='0': continue
                batteries.append(battery_record(path))
            elif kind in ('Mains','USB','USB_C','USB_PD','USB_PD_DRP'):
                value=numeric(path+'/online')
                if value is not None and not path.rsplit('/',1)[-1].startswith('ucsi-source-'): online.append(bool(value))
                r.add_record({'kind':'power_input','name':path.rsplit('/',1)[-1],
                    'type':kind,'online':bool(value) if value is not None else None,'advanced':True})
        states=[b.get('status') for b in batteries]
        source='External power' if any(online) or any(s in ('Charging','Full') for s in states) else 'Battery' if 'Discharging' in states else 'Not reported'
        r.add('Power source',source)
        r.add('Batteries detected',len(batteries))
        for b in batteries: r.add_record(b)
        if not batteries: r.note='No battery is exposed by the system. Desktop power supplies normally do not report capacity or health.'
        else: r.note='Battery health is capacity retained versus design capacity, not the current charge percentage.'
        return r
