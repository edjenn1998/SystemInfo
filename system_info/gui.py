"""Hardware-first Qt interface with an overview, technical view and protected reads."""
import copy
import json
import sys
import time
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QLineEdit,QTabWidget,QTreeWidget,QTreeWidgetItem,QCheckBox,QFileDialog,QMessageBox,QInputDialog)
from .app import SystemInfoApp
from .protected import read_protected

SENSITIVE=('serial','uuid','hostname','nodename','username','fqdn','ipv4','ipv6','MAC_address','gateway','host','terminal','dns','mountpoint','product sku','asset','SSID','service tag','fstab')
TABS={'overview':'Overview','system':'System / OS','cpu':'Processor','memory':'Memory','board':'Motherboard / BIOS','storage':'Storage','gpu':'Graphics','network':'Network','devices':'Devices','power':'Power / Battery','hardware':'Sensors'}
GROUPS={'disk':'Installed drives','partition':'Partitions / filesystems','volume':'Logical / encrypted volumes','virtual_disk':'Software / virtual disks','filesystem':'Filesystems and space usage',
 'gpu':'GPU adapters','display':'Connected displays','display_connector':'Unused display connectors',
 'network_adapter':'Physical network adapters','virtual_interface':'Virtual network interfaces','bluetooth':'Bluetooth adapters','route':'Routes',
 'battery':'Battery','power_input':'Power inputs','memory_module':'Memory banks / devices','usb_device':'USB devices','usb_hub':'USB hubs',
 'internal_controller':'Internal controllers','sensor':'Sensor readings','vulnerability':'CPU security status',
 'summary_drive':'Installed storage','summary_network':'Network','observation':'Troubleshooting observations'}
LABELS={'uuid':'Filesystem / container UUID','partuuid':'Partition UUID (PARTUUID)','fstab_entries':'Matching fstab entries','parent':'Parent drive / partition','health_percent':'Battery health (% of design capacity)','wear_percent':'Capacity wear (%)','charge_percent':'Current charge (%)',
 'full_capacity_mAh':'Full capacity now (mAh)','design_capacity_mAh':'Original design capacity (mAh)','remaining_charge_mAh':'Remaining charge (mAh)',
 'full_capacity_Wh':'Full capacity now (Wh)','design_capacity_Wh':'Original design capacity (Wh)','remaining_energy_Wh':'Remaining energy (Wh)',
 'time_estimate':'Runtime / charging estimate','MAC_address':'MAC address','IPv4_addresses':'IPv4 addresses','IPv6_addresses':'IPv6 addresses',
 'advertised_AP_rate':'Access point advertised rate (not negotiated speed)','transmit_link_rate':'Negotiated transmit link rate',
 'receive_link_rate':'Negotiated receive link rate','signal_percent':'Signal quality (%)','frequency_MHz':'Wi-Fi frequency (MHz)',
 'dedicated_memory_GiB':'Dedicated graphics memory (GiB)','size_bytes':'Exact capacity (bytes)','current_resolution':'Current desktop resolution',
 'preferred_reported_mode':'Preferred reported display mode','used_percent':'Space used (%)','link_speed_Mbit_s':'Link speed (Mbit/s)',
 'critical_limit_C':'Driver critical temperature (°C)'}
TECH_KEYS={'slot','vendor_id','device_id','subsystem','modules','drm_device','size_bytes','bus','device_number','USB_ID','rank','data_width','total_width','voltage','GPU_device','health_basis'}

def safe_report(data):
    data=copy.deepcopy(data)
    for cat in data['categories']:
        for f in cat['fields']:
            if any(s.lower() in f['label'].lower() for s in SENSITIVE):f['value']='[hidden]'
        for rec in cat['records']:
            for key in list(rec):
                sensitive=any(s.lower() in key.lower() for s in SENSITIVE) or key.lower() in ('hw','gw')
                sensitive=sensitive or (rec.get('kind')=='user' and key=='name') or (rec.get('kind')=='filesystem' and key=='name')
                if sensitive:rec[key]='[hidden]'
    return data

def fmt(value):
    if value is None:return 'Not reported'
    if isinstance(value,bool):return 'Yes' if value else 'No'
    if isinstance(value,(list,tuple)):return ', '.join(map(str,value))
    return str(value)

class Worker(QThread):
    result=Signal(object);failed=Signal(str)
    def __init__(self,context=None,action=None,device=None,parent=None):
        super().__init__(parent);self.context=dict(context or {});self.action=action;self.device=device
    def run(self):
        try:
            if self.action:self.result.emit(read_protected(self.action,self.device))
            else:self.result.emit(SystemInfoApp(context=self.context).collect_all())
        except Exception as exc:self.failed.emit(str(exc))

class Window(QMainWindow):
    def __init__(self,auto_collect=True):
        super().__init__();self.setWindowTitle('System Info • 1.2');self.resize(1220,820);self.setMinimumSize(850,560)
        self.snapshot=None;self.worker=None;self.context={};self.trees=[];self.closed_when_finished=False
        root=QWidget();self.setCentralWidget(root);layout=QVBoxLayout(root);layout.setContentsMargins(18,14,18,14)
        title=QLabel('System Info');title.setStyleSheet('font-size:26px;font-weight:600');layout.addWidget(title)
        layout.addWidget(QLabel('Understand your hardware • Useful readings for troubleshooting'))
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Search this tab…');self.search.textChanged.connect(self.filter_rows);row.addWidget(self.search,1)
        self.refresh=QPushButton('Refresh');self.refresh.clicked.connect(self.collect);row.addWidget(self.refresh)
        self.export=QPushButton('Export report…');self.export.clicked.connect(self.save);self.export.setEnabled(False);row.addWidget(self.export);layout.addLayout(row)
        tools=QHBoxLayout();self.technical=QCheckBox('Show technical details');self.technical.toggled.connect(self.rebuild);tools.addWidget(self.technical);tools.addStretch()
        self.protected=QPushButton('Read memory / BIOS details');self.protected.setToolTip('Read memory bank inventory and protected BIOS identifiers. Your desktop may ask for authorization.');self.protected.clicked.connect(self.read_firmware);tools.addWidget(self.protected)
        self.drive_health=QPushButton('Read drive health');self.drive_health.setToolTip('Read SMART health for an installed drive using smartctl. Your desktop may ask for authorization.');self.drive_health.clicked.connect(self.read_health);tools.addWidget(self.drive_health);layout.addLayout(tools)
        self.tabs=QTabWidget();self.tabs.setUsesScrollButtons(True);self.tabs.currentChanged.connect(self.filter_rows);layout.addWidget(self.tabs,1)
        self.note=QLabel();self.note.setWordWrap(True);self.note.setStyleSheet('padding:6px;color:#666;');layout.addWidget(self.note)
        bottom=QHBoxLayout();self.private=QCheckBox('Hide identifying details in exported reports');self.private.setChecked(True);bottom.addWidget(self.private);bottom.addStretch();self.status=QLabel('Ready');bottom.addWidget(self.status);layout.addLayout(bottom)
        if auto_collect:self.collect()
    def busy(self,value):
        for button in (self.refresh,self.protected,self.drive_health):button.setEnabled(not value)
    def start_worker(self,worker,callback):
        if self.worker and self.worker.isRunning():return
        self.busy(True);self.worker=worker;worker.result.connect(callback);worker.failed.connect(self.failure);worker.finished.connect(self.finished);worker.start()
    def finished(self):
        self.busy(False)
        if self.closed_when_finished:self.close()
    def collect(self):
        if self.worker and self.worker.isRunning():return
        self.status.setText('Collecting…');self.start_worker(Worker(self.context,parent=self),self.show_result)
    def failure(self,message):
        self.status.setText('Read incomplete');QMessageBox.warning(self,'System Info',message)
    def read_firmware(self):
        self.status.setText('Waiting for authorization / reading firmware…')
        def received(sections):self.context['dmi_sections']=sections;self.status.setText('Firmware inventory read — updating…')
        worker=Worker(action='firmware',parent=self)
        self.start_worker(worker,received);worker.finished.connect(lambda:QTimer.singleShot(0,self.collect) if 'dmi_sections' in self.context and not self.closed_when_finished else None)
    def read_health(self):
        if not self.snapshot:return
        cat=self.snapshot.get('storage');drives=[d for d in cat.records if d.get('kind')=='disk'] if cat else []
        if not drives:QMessageBox.information(self,'Drive health','No physical drive is available.');return
        labels=[f'{d.get("name")} • {d.get("device")}' for d in drives]
        label,ok=QInputDialog.getItem(self,'Read drive health','Select a physical drive:',labels,0,False)
        if not ok:return
        device=drives[labels.index(label)].get('device');self.status.setText('Waiting for authorization / reading drive…')
        def received(data):self.context.setdefault('smart_reports',{})[device]=data
        worker=Worker(action='smart',device=device,parent=self);self.start_worker(worker,received)
        worker.finished.connect(lambda:QTimer.singleShot(0,self.collect) if device in self.context.get('smart_reports',{}) and not self.closed_when_finished else None)
    def show_result(self,snapshot):
        self.snapshot=snapshot;self.rebuild();self.export.setEnabled(True);self.status.setText('Updated • '+time.strftime('%H:%M:%S'))
    def rebuild(self,*args):
        if not self.snapshot:return
        selected=self.tabs.currentIndex();self.tabs.blockSignals(True);self.tabs.clear();self.trees=[];technical=self.technical.isChecked()
        for cat in self.snapshot.categories:
            tree=QTreeWidget();tree.setHeaderLabels(['Property','Value']);tree.setAlternatingRowColors(True);tree.setColumnWidth(0,360);tree.setUniformRowHeights(True);tree.setStyleSheet('QTreeView::item { min-height: 21px; }')
            for f in cat.fields:
                if f.advanced and not technical:continue
                if f.value is None:
                    if technical:QTreeWidgetItem(tree,[f.label,'Not reported by this system'])
                    continue
                item=QTreeWidgetItem(tree,[f.label,f.display()]);item.setToolTip(0,f.label);item.setToolTip(1,f.display())
            groups={};device_nodes={}
            for rec in cat.records:
                if rec.get('advanced') and not technical:continue
                kind=rec.get('kind','record')
                group=device_nodes.get(rec.get('parent')) if kind in ('partition','volume') else None
                if group is None:
                    group=groups.get(kind)
                    if group is None:
                        group=QTreeWidgetItem(tree,[GROUPS.get(kind,kind.replace('_',' ').capitalize()),'']);group.setExpanded(True);groups[kind]=group
                        font=group.font(0);font.setBold(True);group.setFont(0,font)
                name=rec.get('model') or rec.get('name') or rec.get('device') or rec.get('connector') or kind
                subtitle=rec.get('drive_type') or rec.get('status') or rec.get('adapter_type') or rec.get('size') or ''
                if kind=='sensor':subtitle=f'{rec.get("value")} {rec.get("unit","")}'
                node=QTreeWidgetItem(group,[str(name),str(subtitle)]);node.setExpanded(kind not in ('sensor','vulnerability','internal_controller','usb_hub','display_connector','virtual_disk'))
                if rec.get('device') and kind in ('disk','partition','volume'):device_nodes[rec['device']]=node
                for key,value in rec.items():
                    if key in ('kind','advanced','advanced_keys','name') or (not technical and key=='parent'):continue
                    if value is None or value=='' or value==[]:continue
                    if not technical and (key in TECH_KEYS or key in rec.get('advanced_keys',[])):continue
                    if kind=='sensor' and key in ('value','unit') and not technical:continue
                    item=QTreeWidgetItem(node,[LABELS.get(key,key.replace('_',' ').capitalize()),fmt(value)]);item.setToolTip(1,fmt(value))
            self.trees.append(tree);self.tabs.addTab(tree,TABS.get(cat.name,cat.title))
        self.tabs.setCurrentIndex(max(0,min(selected,self.tabs.count()-1)));self.tabs.blockSignals(False);self.filter_rows()
    def filter_rows(self,*args):
        index=self.tabs.currentIndex()
        if index<0 or index>=len(self.trees):return
        self.note.setText(self.snapshot.categories[index].note or '')
        tree=self.trees[index];query=self.search.text().lower()
        def unhide(item):
            item.setHidden(False)
            for i in range(item.childCount()):unhide(item.child(i))
        def visit(item):
            own=query in (item.text(0)+' '+item.text(1)).lower()
            matched_children=[visit(item.child(i)) for i in range(item.childCount())]
            matched=own or any(matched_children);item.setHidden(not matched)
            if own:unhide(item)
            if query and matched:item.setExpanded(True)
            return matched
        for i in range(tree.topLevelItemCount()):visit(tree.topLevelItem(i))
    def save(self):
        path,_=QFileDialog.getSaveFileName(self,'Export report','system-info.json','JSON (*.json)')
        if not path:return
        try:
            data=self.snapshot.to_dict()
            if self.private.isChecked():data=safe_report(data)
            with open(path,'w',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False)
            self.status.setText('Report saved (includes collected technical data)')
        except OSError as exc:QMessageBox.warning(self,'Export failed',str(exc))
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.closed_when_finished=True;self.status.setText('Finishing the current read before closing…');event.ignore()
        else:event.accept()

def main():
    app=QApplication(sys.argv);app.setStyle('Fusion');window=Window();window.show();return app.exec()
