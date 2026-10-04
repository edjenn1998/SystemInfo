"""Summary and observations derived only from the collected data."""
from .core import CategoryResult

def field_value(cat,*labels):
    if cat:
        for label in labels:
            for f in cat.fields:
                if f.label==label and f.value is not None:return f.display()
    return None

def overview(snapshot):
    r=CategoryResult('overview','Overview')
    system=snapshot.get('system');board=snapshot.get('board');cpu=snapshot.get('cpu');memory=snapshot.get('memory')
    r.add('Computer',field_value(board,'Computer model','Product name'))
    r.add('Manufacturer',field_value(board,'System manufacturer'))
    r.add('Operating system',field_value(system,'Distribution'));r.add('Kernel',field_value(system,'Kernel'))
    r.add('Processor',field_value(cpu,'Model name'))
    cores=field_value(cpu,'Physical cores');threads=field_value(cpu,'Logical processors')
    if cores or threads:r.add('CPU layout',f'{cores or "?"} cores / {threads or "?"} threads')
    r.add('Maximum reported CPU frequency',field_value(cpu,'Maximum reported frequency (includes boost when exposed)','Max freq'))
    r.add('RAM',field_value(memory,'Usable RAM','Total'));r.add('RAM usage',field_value(memory,'RAM usage','Used %'))
    r.add('BIOS version',field_value(board,'BIOS version'))
    if field_value(board,'Boot mode'):r.add('Boot mode',field_value(board,'Boot mode'))
    storage=snapshot.get('storage');gpus=snapshot.get('gpu');network=snapshot.get('network');power=snapshot.get('power');sensors=snapshot.get('hardware')
    if storage:
        disks=[d for d in storage.records if d.get('kind')=='disk']
        r.add('Installed storage',len(disks))
        for d in disks:r.add_record({'kind':'summary_drive','name':d.get('model') or d.get('name'),'type':d.get('drive_type') or d.get('transport'),'capacity':d.get('capacity')})
        for fs in storage.records:
            if fs.get('kind')=='filesystem' and not str(fs.get('device','')).startswith('/dev/loop'):
                if fs.get('mountpoint')=='/':r.add('System drive usage',fs.get('used_percent'),'%')
                if isinstance(fs.get('used_percent'),(int,float)) and fs['used_percent']>=90:r.add_record({'kind':'observation','name':'Storage nearly full','detail':f'{fs.get("mountpoint","Volume")} is {fs["used_percent"]}% used'})
        for d in disks:
            if d.get('SMART health')=='FAILED':r.add_record({'kind':'observation','name':'Drive reports a SMART failure','detail':d.get('name')})
    if gpus:
        physical=[g for g in gpus.records if g.get('kind')=='gpu'];r.add('Graphics adapters',len(physical))
        for g in physical:r.add('Graphics',g.get('name'));r.add('Graphics driver',g.get('driver'))
        displays=[g for g in gpus.records if g.get('kind')=='display'];r.add('Connected displays',len(displays))
    if network:
        adapters=[n for n in network.records if n.get('kind')=='network_adapter']
        for n in adapters:r.add_record({'kind':'summary_network','name':n.get('model') or n.get('name'),'type':n.get('adapter_type'),'state':n.get('state'),'link_rate':n.get('transmit_link_rate') or n.get('link_speed_Mbit_s')})
        r.add('Bluetooth adapters',field_value(network,'Bluetooth adapters detected'))
    if power:
        r.add('Power source',field_value(power,'Power source'))
        for b in power.records:
            if b.get('kind')!='battery':continue
            r.add('Battery charge',b.get('charge_percent'),'%');r.add('Battery status',b.get('status'))
            r.add('Battery health',b.get('health_percent') if b.get('health_percent') is not None else 'Design capacity not reported', '%' if b.get('health_percent') is not None else None)
            if b.get('time_estimate'):r.add('Battery runtime estimate',b['time_estimate'])
            if isinstance(b.get('health_percent'),(int,float)) and b['health_percent']<80:r.add_record({'kind':'observation','name':'Battery capacity has declined','detail':f'{b["health_percent"]}% of design capacity retained'})
    if sensors:
        for s in sensors.records:
            if s.get('unit')=='°C' and (s.get('label') in ('Package id 0','Tctl','Tdie','Composite')) and s.get('chip') in ('coretemp','k10temp','nvme'):
                r.add(s.get('name',s.get('label')),s.get('value'),'°C')
            if s.get('critical_limit_C') is not None and s.get('value',0)>=s['critical_limit_C']:r.add_record({'kind':'observation','name':'Sensor at or above its critical limit','detail':s.get('name')})
    for cat in snapshot.categories:
        if cat.note and 'Some information could not be collected' in cat.note:r.add_record({'kind':'observation','name':cat.title+' collection incomplete','detail':cat.note})
    if not any(d.get('kind')=='observation' for d in r.records):r.add('Troubleshooting observations','No issues flagged by the available readings; this is not a full diagnostic test')
    r.add('Collected at',snapshot.captured_at)
    return r
