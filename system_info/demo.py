"""Illustrative data for screenshots/self-tests; never a claimed hardware reading."""
import copy
from .collectors.base import Collector
from .core import CategoryResult, SystemSnapshot
from .overview import overview


def example_snapshot():
    snapshot = SystemSnapshot()
    system = CategoryResult('system', 'System / OS').add('Distribution', 'Example Linux 24.04').add('Kernel', '6.x (demo)')
    system.add('Hostname (nodename)', 'DEMO-HOST-PRIVATE'); snapshot.add(system)
    cpu = CategoryResult('cpu', 'Processor').add('Model name', 'Example 8-core processor')
    cpu.add('Physical cores', 8).add('Logical processors', 16).add('Maximum reported frequency (includes boost when exposed)', 4.2, 'GHz')
    cpu.add('Turbo / boost', 'Enabled').add('CPU usage (short sample)', 12.5, '%'); snapshot.add(cpu)
    memory = CategoryResult('memory', 'Memory').add('Usable RAM', 31.2, 'GiB').add('RAM usage', 28, '%')
    memory.add('Installed RAM (firmware)', 32, 'GiB').add('Memory banks reported', 2)
    memory.add('Memory inventory status', 'Illustrative fixture; no protected hardware read was performed')
    memory.add_record({'kind':'memory_module','name':'DIMM A','size':'16384 MB','memory_type':'DDR5','populated':True,'serial':'DEMO-SERIAL-PRIVATE'})
    snapshot.add(memory)
    board = CategoryResult('board', 'Motherboard / BIOS').add('Computer model', 'Example workstation')
    board.add('System manufacturer', 'Example Hardware').add('BIOS version', '1.0 (demo)').add('Boot mode', 'UEFI')
    snapshot.add(board)
    storage = CategoryResult('storage', 'Storage').add('Installed drives detected', 1)
    storage.add_record({'kind':'disk','name':'Example NVMe SSD','device':'/dev/nvme0n1','drive_type':'NVMe SSD','capacity':'1.00 TB (931.3 GiB)','SMART health':'Passed','serial':'DEMO-SERIAL-PRIVATE'})
    storage.add_record({'kind':'partition','name':'nvme0n1p1','device':'/dev/nvme0n1p1','parent':'/dev/nvme0n1','filesystem':'ext4','uuid':'DEMO-UUID-PRIVATE','mountpoint':'/'})
    snapshot.add(storage)
    gpu = CategoryResult('gpu', 'Graphics').add('Installed GPU adapters', 1)
    gpu.add_record({'kind':'gpu','name':'Example integrated graphics','driver':'example-driver'})
    gpu.add_record({'kind':'display','name':'Example display','current_resolution':'1920x1080'}); snapshot.add(gpu)
    network = CategoryResult('network', 'Network')
    network.add_record({'kind':'network_adapter','name':'Example Ethernet adapter','adapter_type':'Ethernet','state':'up','link_speed_Mbit_s':1000,'MAC_address':'aa:bb:cc:dd:ee:ff'})
    network.add('Bluetooth adapters detected', 1); snapshot.add(network)
    devices = CategoryResult('devices', 'Devices').add('USB devices (excluding hubs)', 2)
    devices.add_record({'kind':'usb_device','name':'Example keyboard'}); snapshot.add(devices)
    power = CategoryResult('power', 'Power / Battery').add('Power source', 'External power').add('Batteries detected', 0)
    power.note = 'This illustrative desktop fixture has no battery.'; snapshot.add(power)
    sensors = CategoryResult('hardware', 'Sensors')
    sensors.add_record({'kind':'sensor','name':'CPU • Package id 0','chip':'coretemp','label':'Package id 0','value':44,'unit':'°C','critical_limit_C':100})
    snapshot.add(sensors)
    snapshot.categories.insert(0, overview(snapshot))
    return snapshot


def fixture_collectors():
    classes = []
    for category in example_snapshot().categories:
        if category.name == 'overview': continue
        def collect(self, value=category): return copy.deepcopy(value)
        classes.append(type('Fixture_' + category.name, (Collector,),
                            {'name':category.name, 'title':category.title, 'collect':collect}))
    return classes
