"""Battery readings: capacity, health and runtime have independent availability."""
import glob
from .base import Collector, read_file
from ..inventory import numeric, meaningful


def battery_record(path):
    def num(name): return numeric(f'{path}/{name}')
    def capacity(name):
        value = num(name)
        return value if value is not None and value >= 0 else None
    def text(name): return meaningful(read_file(f'{path}/{name}'))
    rec = {'kind': 'battery', 'name': path.rsplit('/', 1)[-1], 'model': text('model_name'),
           'manufacturer': text('manufacturer'), 'technology': text('technology'),
           'status': text('status'), 'charge_percent': capacity('capacity')}
    voltage, current, power = capacity('voltage_now'), num('current_now'), num('power_now')
    if voltage is not None: rec['voltage_V'] = round(voltage / 10**6, 2)
    if current is not None: rec['current_A'] = round(current / 10**6, 3)
    if power is None and voltage is not None and current is not None:
        power = voltage * current / 10**6
    if power is not None: rec['power_W'] = round(abs(power) / 10**6, 2)
    energy = [capacity(name) for name in ('energy_full', 'energy_full_design', 'energy_now')]
    charge = [capacity(name) for name in ('charge_full', 'charge_full_design', 'charge_now')]
    for names, values, divisor in (
        (('full_capacity_Wh', 'design_capacity_Wh', 'remaining_energy_Wh'), energy, 10**6),
        (('full_capacity_mAh', 'design_capacity_mAh', 'remaining_charge_mAh'), charge, 1000),
    ):
        for key, value in zip(names, values):
            if value is not None: rec[key] = round(value / divisor, 2)
    valid = next((values for values in (energy, charge)
                  if values[0] is not None and values[1] is not None and values[1] > 0), None)
    if valid is not None:
        health = valid[0] / valid[1] * 100
        rec['health_percent'] = round(health, 1)
        rec['wear_percent'] = round(max(0, 100-health), 1)
        rec['health_basis'] = 'Reported full capacity / original design capacity'
    else:
        rec['health_note'] = 'Health cannot be calculated: design or full capacity is not reported.'
    design_voltage = capacity('voltage_min_design')
    if charge[1] is not None and design_voltage is not None and energy[1] is None:
        rec['design_energy_Wh_estimate'] = round(charge[1] * design_voltage / 10**12, 2)
    cycles = capacity('cycle_count')
    if cycles is not None:
        rec['cycle_count'] = int(cycles)
        if cycles == 0: rec['cycle_note'] = 'Firmware reports 0; some batteries do not maintain this count.'
    values, rate = (energy, abs(power)) if energy[2] is not None and power else (charge, abs(current) if current else None)
    if rate is not None and rate > 0 and values[2] is not None:
        state = (rec['status'] or '').casefold()
        remaining = values[2] if state == 'discharging' else values[0]-values[2] if state == 'charging' and values[0] is not None else None
        if remaining is not None and remaining >= 0:
            hours = remaining / rate
            rec['time_estimate'] = f'{int(hours)}h {int((hours%1)*60)}m ' + ('remaining' if state == 'discharging' else 'until full')
            rec['estimate_note'] = 'Estimate at the present discharge/charge rate; changes with workload.'
    return {k: v for k, v in rec.items() if v is not None}


class PowerCollector(Collector):
    name = 'power'
    title = 'Power / Battery'

    def collect(self):
        r = self.new_result(); batteries = []; online = []
        for path in sorted(glob.glob('/sys/class/power_supply/*')):
            kind = read_file(path+'/type')
            if kind == 'Battery':
                if read_file(path+'/present') == '0': continue
                batteries.append(battery_record(path))
            elif kind in ('Mains', 'USB', 'USB_C', 'USB_PD', 'USB_PD_DRP'):
                value = numeric(path+'/online')
                if value is not None and not path.rsplit('/', 1)[-1].startswith('ucsi-source-'): online.append(bool(value))
                r.add_record({'kind': 'power_input', 'name': path.rsplit('/', 1)[-1],
                              'type': kind, 'online': bool(value) if value is not None else None, 'advanced': True})
        states = [b.get('status') for b in batteries]
        if online:
            source = 'External power' if any(online) else 'Battery' if batteries else 'Not reported'
        else:
            source = 'External power' if 'Charging' in states else 'Battery' if 'Discharging' in states else 'Not reported'
        r.add('Power source', source); r.add('Batteries detected', len(batteries))
        for battery in batteries: r.add_record(battery)
        r.note = ('Battery health is capacity retained versus design capacity, not the current charge percentage.' if batteries else
                  'No battery is exposed by the system. Desktop power supplies normally do not report capacity or health.')
        return r
