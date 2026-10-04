import unittest
from unittest.mock import patch
from system_info.filesystems import parse_fstab,match_fstab
from system_info.collectors.storage import StorageCollector
from system_info.collectors.memory import MemoryCollector
from system_info.app import SystemInfoApp
from system_info.gui import Window,safe_report
from system_info.core import CategoryResult,SystemSnapshot
from test_gui import APP

class FilesystemTests(unittest.TestCase):
    def test_fstab_escapes_and_no_credentials(self):
        entries=parse_fstab('# comment\nUUID=ABCD / ext4 defaults 0 1\nLABEL=Data\\040Disk /mnt/Data\\040Disk ext4 defaults 0 2\n//host/share /mnt/net cifs username=bob,password=secret 0 0')
        self.assertEqual(entries[1]['mountpoint'],'/mnt/Data Disk')
        self.assertNotIn('secret',str(entries));self.assertNotIn('bob',str(entries))
        self.assertEqual(len(match_fstab({'uuid':'abcd'},entries)),1)
        self.assertEqual(len(match_fstab({'label':'Data Disk'},entries)),1)
    def test_partuuid_matching(self):
        entries=parse_fstab('PARTUUID=abc /boot vfat defaults 0 2')
        self.assertEqual(len(match_fstab({'partuuid':'ABC'},entries)),1)
        self.assertEqual(match_fstab({'uuid':'ABC'},entries),[])
    def test_uuid_visible_with_partition_hierarchy(self):
        source=[{'name':'sda','path':'/dev/sda','type':'disk','size':1000000000,'model':'Example SSD','tran':'sata','rota':False,'children':[
            {'name':'sda1','path':'/dev/sda1','type':'part','size':900000000,'fstype':'ext4','uuid':'example-uuid','partuuid':'part-uuid','mountpoint':'/'}]}]
        with patch.object(StorageCollector,'_lsblk',return_value=source),patch('system_info.collectors.storage.device_aliases',return_value={}),patch('system_info.collectors.storage.read_file',side_effect=lambda p:'UUID=example-uuid / ext4 defaults 0 1' if p=='/etc/fstab' else None),patch('system_info.collectors.storage.psutil.disk_partitions',return_value=[]),patch('system_info.collectors.storage.smart_report',return_value={}):
            cat=StorageCollector().collect()
        part=next(r for r in cat.records if r['kind']=='partition');self.assertEqual(part['uuid'],'example-uuid');self.assertEqual(part['parent'],'/dev/sda');self.assertFalse(part['advanced']);self.assertTrue(part['fstab_entries'])
        snap=SystemSnapshot();snap.add(cat);w=Window(auto_collect=False);w.show_result(snap)
        tree=w.trees[0];drive=tree.topLevelItem(2).child(0) if tree.topLevelItemCount()>2 else None
        group=next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if tree.topLevelItem(i).text(0)=='Installed drives')
        disk=group.child(0);node=next(disk.child(i) for i in range(disk.childCount()) if disk.child(i).text(0)=='sda1')
        uuids=[node.child(i) for i in range(node.childCount()) if node.child(i).text(0)=='Filesystem / container UUID']
        self.assertEqual(uuids[0].text(1),'example-uuid');self.assertFalse(uuids[0].isHidden());w.close()
    def test_export_redacts_uuid_and_fstab(self):
        report={'categories':[{'fields':[],'records':[{'kind':'partition','uuid':'secret','partuuid':'secret2','fstab_entries':['UUID=secret → /']}]}]}
        clean=safe_report(report)['categories'][0]['records'][0]
        self.assertEqual(clean['uuid'],'[hidden]');self.assertEqual(clean['fstab_entries'],'[hidden]')
    def test_authorized_firmware_without_banks_not_called_protected(self):
        cat=MemoryCollector(context={'dmi_sections':[{'type':1,'fields':{'Product Name':'Example'}}],'dmi_status':'not_reported'}).collect()
        status=next(f.value for f in cat.fields if f.label=='Memory inventory status')
        self.assertIn('does not report',status);self.assertNotIn('Authorization needed',status)
    def test_missing_firmware_interface_status(self):
        app=SystemInfoApp(context={})
        with patch('pathlib.Path.read_bytes',side_effect=FileNotFoundError),patch('system_info.app.run_cmd',return_value=None):app.prepare_context()
        self.assertEqual(app.context['dmi_status'],'interface_absent')
    def test_permission_status(self):
        app=SystemInfoApp(context={})
        with patch('pathlib.Path.read_bytes',side_effect=PermissionError),patch('system_info.app.run_cmd',return_value=None):app.prepare_context()
        self.assertEqual(app.context['dmi_status'],'authorization_required')

if __name__=='__main__':unittest.main()
