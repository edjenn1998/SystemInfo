import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtWidgets import QApplication
from system_info.core import CategoryResult,SystemSnapshot
from system_info.gui import Window,safe_report
from system_info.overview import overview

APP=QApplication.instance() or QApplication([])
def example_snapshot():
    snap=SystemSnapshot()
    board=CategoryResult('board','Motherboard / BIOS');board.add('Computer model','Dell XPS 13 9305');board.add('System manufacturer','Dell');board.add('BIOS version','1.29.0');snap.add(board)
    cpu=CategoryResult('cpu','Processor');cpu.add('Model name','Intel Core i7-1165G7');cpu.add('Physical cores',4);cpu.add('Logical processors',8);cpu.add('Maximum reported frequency (includes boost when exposed)',4.7,'GHz');snap.add(cpu)
    ram=CategoryResult('memory','Memory');ram.add('Usable RAM',15.36,'GiB');ram.add('RAM usage',28,'%');ram.add('Memory banks reported','Read protected hardware details to retrieve firmware inventory');snap.add(ram)
    storage=CategoryResult('storage','Storage');storage.add('Installed drives detected',1);storage.add_record({'kind':'disk','name':'Samsung PM991a NVMe 1024GB','device':'/dev/nvme0n1','drive_type':'NVMe SSD','capacity':'1.02 TB (953.9 GiB)'})
    storage.add_record({'kind':'virtual_disk','name':'loop0','advanced':True});snap.add(storage)
    graphics=CategoryResult('gpu','Graphics');graphics.add('Installed GPU adapters',1);graphics.add_record({'kind':'gpu','name':'Intel Iris Xe Graphics','driver':'i915'});graphics.add_record({'kind':'display','name':'Built-in display • eDP-1','preferred_reported_mode':'1920x1080'})
    for i in range(6):graphics.add_record({'kind':'display_connector','name':'Unused connector '+str(i),'advanced':True})
    snap.add(graphics)
    network=CategoryResult('network','Network');network.add_record({'kind':'network_adapter','name':'Intel Wi-Fi 6 AX200','adapter_type':'Wi-Fi','state':'up'});network.add_record({'kind':'virtual_interface','name':'tailscale0','advanced':True});network.add_record({'kind':'virtual_interface','name':'lo','advanced':True});snap.add(network)
    power=CategoryResult('power','Power');power.add('Power source','Battery');power.add_record({'kind':'battery','name':'BAT0','model':'DELL H754V14','charge_percent':73,'status':'Discharging','full_capacity_mAh':5372,'health_note':'Design capacity not reported'});power.add_record({'kind':'power_input','name':'AC','advanced':True});snap.add(power)
    snap.categories.insert(0,overview(snap));return snap

class GUITests(unittest.TestCase):
    def setUp(self):self.w=Window(auto_collect=False);self.w.show_result(example_snapshot());self.w.show();APP.processEvents()
    def tearDown(self):self.w.close();APP.processEvents()
    def tab(self,name):
        index=next(i for i,c in enumerate(self.w.snapshot.categories) if c.name==name);self.w.tabs.setCurrentIndex(index);return self.w.trees[index]
    def groups(self,tree):return [tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if tree.topLevelItem(i).childCount()]
    def test_storage_defaults_and_technical_toggle(self):
        tree=self.tab('storage');groups=self.groups(tree);self.assertEqual(len(groups),1);self.assertEqual(groups[0].text(0),'Installed drives');self.assertEqual(groups[0].childCount(),1)
        self.w.technical.setChecked(True);tree=self.tab('storage');self.assertEqual(len(self.groups(tree)),2)
    def test_graphics_not_eight_cards(self):
        groups=self.groups(self.tab('gpu'));self.assertEqual([g.text(0) for g in groups],['GPU adapters','Connected displays'])
        self.assertEqual(groups[0].childCount(),1)
    def test_virtual_network_hidden(self):self.assertEqual([g.text(0) for g in self.groups(self.tab('network'))],['Physical network adapters'])
    def test_search_keeps_matching_hierarchy(self):
        tree=self.tab('storage');self.w.search.setText('NVMe');group=self.groups(tree)[0];self.assertFalse(group.isHidden());self.assertFalse(group.child(0).isHidden())
    def test_redaction_new_network_fields(self):
        report={'categories':[{'fields':[],'records':[{'kind':'network_adapter','SSID':'private','MAC_address':'secret','IPv4_addresses':['192.168.1.1']}]}]}
        cleaned=safe_report(report);self.assertTrue(all(cleaned['categories'][0]['records'][0][k]=='[hidden]' for k in ['SSID','MAC_address','IPv4_addresses']))
    def test_overview_and_controls_fit(self):
        self.assertEqual(self.w.tabs.tabText(0),'Overview');self.w.resize(850,560);APP.processEvents()
        for button in [self.w.refresh,self.w.protected,self.w.drive_health,self.w.export]:
            point=button.mapTo(self.w,button.rect().bottomRight());self.assertLess(point.x(),self.w.width());self.assertLess(point.y(),self.w.height())

if __name__=='__main__':unittest.main()
