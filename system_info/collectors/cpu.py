"""CPU identity, turbo controls, frequencies and relevant troubleshooting data."""
import glob
import psutil
from .base import Collector, read_file, run_cmd
from ..inventory import numeric

def _flatten_lscpu(text):
    out={}
    for line in text.splitlines():
        key,sep,val=line.partition(':')
        if sep:out[key.strip()]=val.strip()
    return out

def boost_status():
    no_turbo=read_file('/sys/devices/system/cpu/intel_pstate/no_turbo')
    if no_turbo in ('0','1'):return 'Enabled' if no_turbo=='0' else 'Disabled'
    boost=read_file('/sys/devices/system/cpu/cpufreq/boost')
    if boost in ('0','1'):return 'Enabled' if boost=='1' else 'Disabled'
    return 'Control is not exposed by the CPU driver'

class CpuCollector(Collector):
    name='cpu';title='Processor'
    def collect(self):
        r=self.new_result();text=run_cmd(['lscpu']);info=_flatten_lscpu(text or '')
        raw=read_file('/proc/cpuinfo') or ''
        proc={line.partition(':')[0].strip():line.partition(':')[2].strip() for line in raw.splitlines() if ':' in line}
        r.add('Model name',info.get('Model name') or proc.get('model name'))
        r.add('Physical cores',psutil.cpu_count(logical=False));r.add('Logical processors',psutil.cpu_count(logical=True))
        for key,label in [('Architecture','Architecture'),('Socket(s)','CPU sockets'),('Thread(s) per core','Threads per core'),('Virtualization','Virtualization'),('L2 cache','L2 cache'),('L3 cache','L3 cache')]:r.add(label,info.get(key))
        freq=psutil.cpu_freq()
        policy=sorted(glob.glob('/sys/devices/system/cpu/cpufreq/policy*'))
        maximums=[numeric(p+'/cpuinfo_max_freq') for p in policy];maximums=[v/1000 for v in maximums if v is not None]
        maximum=max(maximums) if maximums else freq.max if freq and freq.max else None
        r.add('Turbo / boost',boost_status())
        r.add('Maximum reported frequency (includes boost when exposed)',round(maximum/1000,2) if maximum else None,'GHz')
        r.add('Frequency interpretation','Driver-reported ceiling, not a guaranteed sustained or all-core clock')
        if freq:
            r.add('Current average frequency',round(freq.current/1000,2),'GHz')
            if freq.min:r.add('Minimum reported frequency',round(freq.min/1000,2),'GHz',advanced=True)
        if policy:
            r.add('Frequency driver',read_file(policy[0]+'/scaling_driver'))
            r.add('Power governor',read_file(policy[0]+'/scaling_governor'))
            cap=numeric(policy[0]+'/scaling_max_freq')
            if cap is not None:r.add('Current policy frequency limit',round(cap/10**6,2),'GHz')
            pref=read_file(policy[0]+'/energy_performance_preference')
            if pref:r.add('Energy preference',pref)
        r.add('CPU usage (short sample)',psutil.cpu_percent(interval=0.2),'%')
        r.add('Microcode',proc.get('microcode'))
        for key in ['Vendor ID','CPU op-mode(s)','Byte Order','On-line CPU(s) list','CPU family','Model','Stepping','Address sizes','L1d cache','L1i cache','NUMA node(s)']:
            if info.get(key):r.add(key,info[key],advanced=True)
        flags=(info.get('Flags') or proc.get('flags') or '').split()
        if flags:r.add('Instruction extensions',sorted({f for f in flags if f.startswith(('avx','sse','fma','aes','sha','vmx','svm'))}),advanced=True)
        r.add('Load averages (1 / 5 / 15 minutes)',list(psutil.getloadavg()),advanced=True)
        for key,value in info.items():
            if key.startswith('Vulnerability '):r.add_record({'kind':'vulnerability','name':key[14:],'status':value,'advanced':True})
        if not text:r.note='lscpu unavailable; showing information from the kernel and psutil.'
        return r
