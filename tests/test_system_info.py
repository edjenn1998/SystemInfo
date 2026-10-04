import unittest
from unittest.mock import patch
from system_info.app import SystemInfoApp
from system_info.collectors.base import Collector
from system_info.collectors.storage import StorageCollector
from system_info.collectors.gpu import _parse_lspci_gpus
from system_info.gui import safe_report
class Tests(unittest.TestCase):
    def test_partial_result(self):
        class Broken(Collector):
            name='test';title='Test'
            def collect(self):
                r=self.new_result();r.add('saved',123);raise ValueError('bad field')
        r=Broken().run();self.assertEqual(r.fields[0].value,123);self.assertIn('bad field',r.note)
    def test_storage_hierarchy(self):
        data=[{'path':'/dev/a','children':[{'path':'/dev/a1'}]}]
        result=StorageCollector()._flatten_devices(data)
        self.assertEqual(result[1]['parent'],'/dev/a');self.assertIn('children',data[0])
    def test_no_collectors(self): self.assertEqual(SystemInfoApp([]).category_names,[])
    def test_gpu(self):
        out='01:00.0 VGA compatible controller [0300]: Example GPU [1002:1234]\n\tKernel driver in use: amdgpu\n02:00.0 Audio device [0403]: Audio [1002:4321]\n\tKernel driver in use: snd'
        self.assertEqual(_parse_lspci_gpus(out)[0]['driver'],'amdgpu')
    def test_hugepage_units(self):
        from system_info.collectors.memory import MemoryCollector
        with patch("system_info.collectors.memory._parse_meminfo",return_value={"HugePages_Total":12}), patch.object(MemoryCollector,"_dimm_slots",return_value=[]):
            field=next(f for f in MemoryCollector().collect().fields if f.label=="HugePages_Total")
            self.assertEqual(field.unit,"pages")
    def test_timezone(self):
        from datetime import datetime
        from system_info.collectors.system import SystemCollector
        self.assertEqual(SystemCollector._timezone(),datetime.now().astimezone().strftime("%Z UTC%z"))
    def test_redaction(self):
        data={'categories':[{'fields':[{'label':'Hostname','value':'secret'}],'records':[{'kind':'disk','serial':'secret','size':123}]}]}
        clean=safe_report(data);self.assertEqual(clean['categories'][0]['records'][0]['serial'],'[hidden]');self.assertEqual(data['categories'][0]['fields'][0]['value'],'secret')
if __name__=='__main__':unittest.main()
