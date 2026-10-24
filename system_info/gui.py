"""Hardware-first Qt UI; normal collection and exports stay unprivileged."""
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Qt, QTimer, QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTabWidget, QTreeWidget, QTreeWidgetItem, QCheckBox,
    QFileDialog, QMessageBox, QInputDialog, QProgressBar, QComboBox,
    QDialog, QPlainTextEdit, QDialogButtonBox,
)
from .app import SystemInfoApp
from .protected import read_protected
from .cancellation import Cancelled
from .reports import safe_report as safe_report  # public compatibility import
from .reports import render_report, write_report
from .version import VERSION

TABS = {'overview':'Overview','system':'System / OS','cpu':'Processor','memory':'Memory',
        'board':'Motherboard / BIOS','storage':'Storage','gpu':'Graphics','network':'Network',
        'devices':'Devices','power':'Power / Battery','hardware':'Sensors'}
GROUPS = {'disk':'Installed drives','partition':'Partitions / filesystems','volume':'Logical / encrypted volumes',
          'virtual_disk':'Software / virtual disks','filesystem':'Filesystems and space usage',
          'gpu':'GPU adapters','display':'Connected displays','display_connector':'Unused display connectors',
          'network_adapter':'Physical network adapters','virtual_interface':'Virtual network interfaces',
          'bluetooth':'Bluetooth adapters','route':'Routes','battery':'Battery','power_input':'Power inputs',
          'memory_module':'Memory banks / devices','usb_device':'USB devices','usb_hub':'USB hubs',
          'internal_controller':'Internal controllers','sensor':'Sensor readings','vulnerability':'CPU security status',
          'summary_drive':'Installed storage','summary_network':'Network','observation':'Troubleshooting observations'}
LABELS = {'uuid':'Filesystem / container UUID','partuuid':'Partition UUID (PARTUUID)',
          'fstab_entries':'Matching fstab entries','parent':'Parent drive / partition',
          'other_parents':'Also belongs to','health_percent':'Battery health (% of design capacity)',
          'wear_percent':'Capacity wear (%)','charge_percent':'Current charge (%)',
          'full_capacity_mAh':'Full capacity now (mAh)','design_capacity_mAh':'Original design capacity (mAh)',
          'remaining_charge_mAh':'Remaining charge (mAh)','full_capacity_Wh':'Full capacity now (Wh)',
          'design_capacity_Wh':'Original design capacity (Wh)','remaining_energy_Wh':'Remaining energy (Wh)',
          'time_estimate':'Runtime / charging estimate','MAC_address':'MAC address',
          'IPv4_addresses':'IPv4 addresses','IPv6_addresses':'IPv6 addresses',
          'advertised_AP_rate':'Access point advertised rate (not negotiated speed)',
          'transmit_link_rate':'Negotiated transmit link rate','receive_link_rate':'Negotiated receive link rate',
          'signal_percent':'Signal quality (%)','frequency_MHz':'Wi-Fi frequency (MHz)',
          'dedicated_memory_GiB':'Dedicated graphics memory (GiB)','size_bytes':'Exact capacity (bytes)',
          'current_resolution':'Current desktop resolution','preferred_reported_mode':'Preferred reported display mode',
          'used_percent':'Space used (%)','link_speed_Mbit_s':'Link speed (Mbit/s)',
          'critical_limit_C':'Driver critical temperature (°C)'}
TECH_KEYS = {'slot','vendor_id','device_id','subsystem','modules','drm_device','size_bytes',
             'bus','device_number','USB_ID','rank','data_width','total_width','voltage','GPU_device','health_basis'}


def asset_path():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets/system-info.svg'


def fmt(value):
    if value is None: return 'Not reported'
    if isinstance(value, bool): return 'Yes' if value else 'No'
    if isinstance(value, (list, tuple)): return ', '.join(map(str, value))
    return str(value)


class Worker(QThread):
    result = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    progress = Signal(int, int, str)

    def __init__(self, context=None, action=None, device=None, parent=None, collectors=None):
        super().__init__(parent)
        self.context = dict(context or {})
        self.action, self.device = action, device
        self.cancel = threading.Event()
        self.succeeded = False
        self.collectors = collectors

    def run(self):
        try:
            data = (read_protected(self.action, self.device) if self.action else
                    SystemInfoApp(collectors=self.collectors, context=self.context).collect_all(cancel=self.cancel, progress=self.progress.emit))
            self.succeeded = True
            self.result.emit(data)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self, auto_collect=True, persist=None):
        super().__init__()
        self.setWindowTitle(f'System Info • {VERSION}')
        self.setWindowIcon(QIcon(str(asset_path())))
        self.resize(1220, 820); self.setMinimumSize(850, 560)
        self.snapshot = None; self.worker = None; self.context = {}; self.trees = []
        self.closed_when_finished = False
        self.persist = auto_collect if persist is None else persist
        self.settings = QSettings('edjenn1998', 'SystemInfo')
        self.auto_timer = QTimer(self); self.auto_timer.timeout.connect(self.collect)
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root); layout.setContentsMargins(18, 14, 18, 14)
        title = QLabel('System Info'); title.setStyleSheet('font-size:26px;font-weight:600'); layout.addWidget(title)
        layout.addWidget(QLabel('Understand your hardware • Useful readings for troubleshooting'))
        row = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText('Search this tab…')
        self.search.textChanged.connect(self.filter_rows); row.addWidget(self.search, 1)
        self.refresh = QPushButton('Refresh'); self.refresh.clicked.connect(self.collect); row.addWidget(self.refresh)
        self.copy = QPushButton('Copy report'); self.copy.clicked.connect(self.copy_report); self.copy.setEnabled(False); row.addWidget(self.copy)
        self.export = QPushButton('Export report…'); self.export.clicked.connect(self.save); self.export.setEnabled(False); row.addWidget(self.export)
        row.addWidget(QLabel('Auto'))
        self.interval = QComboBox()
        for text, seconds in [('Off',0),('5 s',5),('15 s',15),('30 s',30),('60 s',60)]: self.interval.addItem(text, seconds)
        self.interval.currentIndexChanged.connect(self.change_interval); row.addWidget(self.interval)
        layout.addLayout(row)
        tools = QHBoxLayout()
        self.technical = QCheckBox('Show technical details'); self.technical.toggled.connect(self.rebuild); tools.addWidget(self.technical)
        self.about = QPushButton('About / tools'); self.about.clicked.connect(self.show_tools); tools.addWidget(self.about)
        tools.addStretch()
        self.protected = QPushButton('Read memory / BIOS details')
        self.protected.setToolTip('Read protected firmware inventory. Authorization does not unlock live RAM timings.')
        self.protected.clicked.connect(self.read_firmware); tools.addWidget(self.protected)
        self.drive_health = QPushButton('Read drive health')
        self.drive_health.setToolTip('Read-only smartctl query for a selected installed drive; desktop authorization may be requested.')
        self.drive_health.clicked.connect(self.read_health); tools.addWidget(self.drive_health)
        layout.addLayout(tools)
        self.tabs = QTabWidget(); self.tabs.setUsesScrollButtons(True); self.tabs.currentChanged.connect(self.filter_rows)
        layout.addWidget(self.tabs, 1)
        self.note = QLabel(); self.note.setWordWrap(True); self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setStyleSheet('padding:6px;'); layout.addWidget(self.note)
        progress = QHBoxLayout()
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0); progress.addWidget(self.progress, 1)
        self.cancel = QPushButton('Cancel'); self.cancel.clicked.connect(self.cancel_collection); self.cancel.setEnabled(False); progress.addWidget(self.cancel)
        layout.addLayout(progress)
        bottom = QHBoxLayout()
        self.private = QCheckBox('Hide identifying details in exported / copied reports'); self.private.setChecked(True)
        self.private.setToolTip('Hides known identifiers, including nested values. Free-form vendor text may still identify a machine.')
        bottom.addWidget(self.private); bottom.addStretch()
        self.status = QLabel('Ready'); self.status.setTextFormat(Qt.TextFormat.PlainText); self.status.setWordWrap(True)
        self.status.setMinimumWidth(220)
        bottom.addWidget(self.status); layout.addLayout(bottom)
        if self.persist:
            geometry = self.settings.value('geometry')
            if geometry: self.restoreGeometry(geometry)
            self.technical.setChecked(self.settings.value('technical', False, type=bool))
        if auto_collect: self.collect()

    def change_interval(self, *_):
        self.auto_timer.stop()
        seconds = self.interval.currentData()
        if seconds and not self.closed_when_finished: self.auto_timer.start(seconds * 1000)

    def busy(self, value):
        for button in (self.refresh, self.protected, self.drive_health): button.setEnabled(not value)

    def start_worker(self, worker, callback, after=None):
        if self.worker or self.closed_when_finished:
            worker.deleteLater(); return False
        self.busy(True); self.worker = worker
        self.cancel.setEnabled(not bool(worker.action)); self.progress.setRange(0, 0)
        worker.result.connect(callback); worker.failed.connect(self.failure)
        worker.cancelled.connect(lambda: self.status.setText('Cancelled • previous report kept'))
        worker.progress.connect(self.update_progress)
        def finished():
            if self.worker is not worker: return
            self.worker = None; self.busy(False); self.cancel.setEnabled(False)
            self.progress.setRange(0, 100); self.progress.setValue(100)
            self.progress.setFormat('Ready' if worker.succeeded else 'Stopped')
            worker.deleteLater()
            if self.closed_when_finished:
                QTimer.singleShot(0, self.close)
            elif worker.succeeded and after:
                QTimer.singleShot(0, after)
        worker.finished.connect(finished); worker.start()
        return True

    def update_progress(self, current, total, title):
        self.progress.setRange(0, max(total, 1)); self.progress.setValue(current)
        self.progress.setFormat(f'{current}/{total} • {title}')

    def collect(self):
        if self.worker or self.closed_when_finished: return
        self.status.setText('Collecting…' + (' previous report remains visible' if self.snapshot else ''))
        self.start_worker(Worker(self.context, parent=self), self.show_result)

    def cancel_collection(self):
        if self.worker and not self.worker.action:
            self.worker.cancel.set(); self.cancel.setEnabled(False)
            self.status.setText('Cancelling at the next readable checkpoint…')

    def failure(self, message):
        self.status.setText('Read incomplete • previous report kept' if self.snapshot else 'Read incomplete')
        if not self.closed_when_finished: QMessageBox.warning(self, 'System Info', message)

    def read_firmware(self):
        if self.worker: return
        self.status.setText('Waiting for authorization / reading firmware…')
        def received(sections):
            self.context['dmi_sections'] = sections
            self.status.setText('Firmware inventory read — updating…')
        self.start_worker(Worker(action='firmware', parent=self), received, after=self.collect)

    def read_health(self):
        if self.worker or not self.snapshot: return
        from .inventory import valid_drive_path
        cat = self.snapshot.get('storage')
        drives = [d for d in cat.records if d.get('kind') == 'disk' and valid_drive_path(d.get('device'))] if cat else []
        if not drives:
            QMessageBox.information(self, 'Drive health', 'No supported physical drive is available.'); return
        labels = [f'{d.get("name")} • {d.get("device")}' for d in drives]
        label, ok = QInputDialog.getItem(self, 'Read drive health', 'Select a physical drive:', labels, 0, False)
        if not ok: return
        device = drives[labels.index(label)]['device']
        self.status.setText('Waiting for authorization / reading drive…')
        def received(data): self.context.setdefault('smart_reports', {})[device] = data
        self.start_worker(Worker(action='smart', device=device, parent=self), received, after=self.collect)

    def show_result(self, snapshot):
        self.snapshot = snapshot; self.rebuild(); self.export.setEnabled(True); self.copy.setEnabled(True)
        incomplete = sum(bool(c.note and c.note.startswith('Some information could not be collected')) for c in snapshot.categories)
        self.status.setText('Updated • ' + time.strftime('%H:%M:%S') + (f' • {incomplete} incomplete categories' if incomplete else ''))

    @staticmethod
    def tree_state(tree):
        expanded = set()
        def visit(item):
            if item.isExpanded(): expanded.add(item.data(0, Qt.ItemDataRole.UserRole))
            for i in range(item.childCount()): visit(item.child(i))
        for i in range(tree.topLevelItemCount()): visit(tree.topLevelItem(i))
        return expanded, tree.verticalScrollBar().value()

    def rebuild(self, *args):
        if not self.snapshot: return
        current = self.tabs.currentWidget()
        selected = current.property('category') if current else None
        states = {tree.property('category'): self.tree_state(tree) for tree in self.trees}
        self.tabs.blockSignals(True)
        while self.tabs.count():
            widget = self.tabs.widget(0); self.tabs.removeTab(0); widget.deleteLater()
        self.trees = []; technical = self.technical.isChecked()
        for cat in self.snapshot.categories:
            tree = QTreeWidget(); tree.setProperty('category', cat.name)
            tree.setHeaderLabels(['Property', 'Value']); tree.setAlternatingRowColors(True)
            tree.setColumnWidth(0, 360); tree.setUniformRowHeights(True)
            tree.setStyleSheet('QTreeView::item { min-height: 21px; }')
            expanded, scroll = states.get(cat.name, (None, 0))
            def item(parent, values, key, default=False):
                node = QTreeWidgetItem(parent, values); node.setData(0, Qt.ItemDataRole.UserRole, key)
                node.setExpanded(key in expanded if expanded is not None else default)
                return node
            for index, field in enumerate(cat.fields):
                if field.advanced and not technical: continue
                if field.value is None and not technical: continue
                value = field.display() if field.value is not None else 'Not reported by this system'
                node = item(tree, [field.label, value], f'field/{field.label}/{index}')
                node.setToolTip(0, field.label); node.setToolTip(1, value)
            groups, device_nodes = {}, {}
            for index, rec in enumerate(cat.records):
                if rec.get('advanced') and not technical: continue
                kind = rec.get('kind', 'record')
                group = device_nodes.get(rec.get('parent')) if kind in ('partition', 'volume') else None
                if group is None:
                    group = groups.get(kind)
                    if group is None:
                        group = item(tree, [GROUPS.get(kind, kind.replace('_', ' ').capitalize()), ''], f'group/{kind}', True)
                        groups[kind] = group; font = group.font(0); font.setBold(True); group.setFont(0, font)
                name = rec.get('model') or rec.get('name') or rec.get('device') or rec.get('connector') or kind
                subtitle = rec.get('drive_type') or rec.get('status') or rec.get('adapter_type') or rec.get('size') or ''
                if kind == 'sensor': subtitle = f'{rec.get("value")} {rec.get("unit", "")}'
                key = f'record/{kind}/{rec.get("device") or rec.get("slot") or name}/{index}'
                node = item(group, [str(name), str(subtitle)], key,
                            kind not in ('sensor','vulnerability','internal_controller','usb_hub','display_connector','virtual_disk'))
                if rec.get('device') and kind in ('disk', 'partition', 'volume'): device_nodes[rec['device']] = node
                for prop, value in rec.items():
                    if prop in ('kind','advanced','advanced_keys','name') or (not technical and prop == 'parent'): continue
                    if value is None or value == '' or value == []: continue
                    if not technical and (prop in TECH_KEYS or prop in rec.get('advanced_keys', [])): continue
                    if kind == 'sensor' and prop in ('value','unit') and not technical: continue
                    child = item(node, [LABELS.get(prop, prop.replace('_', ' ').capitalize()), fmt(value)], key+'/'+prop)
                    child.setToolTip(1, fmt(value))
            self.trees.append(tree); self.tabs.addTab(tree, TABS.get(cat.name, cat.title))
            tree.verticalScrollBar().setValue(scroll)
        selected_index = next((i for i, tree in enumerate(self.trees) if tree.property('category') == selected), 0)
        self.tabs.setCurrentIndex(selected_index); self.tabs.blockSignals(False); self.filter_rows()

    def filter_rows(self, *args):
        index = self.tabs.currentIndex()
        if index < 0 or index >= len(self.trees): return
        self.note.setText(self.snapshot.categories[index].note or '')
        tree = self.trees[index]; query = self.search.text().casefold()
        def unhide(item):
            item.setHidden(False)
            for i in range(item.childCount()): unhide(item.child(i))
        def visit(item):
            own = query in (item.text(0)+' '+item.text(1)).casefold()
            matched = any([visit(item.child(i)) for i in range(item.childCount())]) or own
            item.setHidden(not matched)
            if own: unhide(item)
            if query and matched: item.setExpanded(True)
            return matched
        for i in range(tree.topLevelItemCount()): visit(tree.topLevelItem(i))

    def save(self):
        if self.snapshot is None: return
        path, selected = QFileDialog.getSaveFileName(self, 'Export report', 'system-info.json', 'JSON (*.json);;Text (*.txt)')
        if not path: return
        format = 'text' if Path(path).suffix.casefold() == '.txt' or selected.startswith('Text') else 'json'
        try:
            write_report(path, render_report(self.snapshot, format, self.private.isChecked()))
            self.status.setText('Report saved • includes collected technical data')
        except (OSError, ValueError) as exc: QMessageBox.warning(self, 'Export failed', str(exc))

    def copy_report(self):
        if self.snapshot is None: return
        QApplication.clipboard().setText(render_report(self.snapshot, 'text', self.private.isChecked()))
        self.status.setText('Copied • ' + ('identifiers hidden' if self.private.isChecked() else 'identifiers included'))

    def show_tools(self):
        import psutil
        from PySide6.QtCore import qVersion
        from .collectors.base import which
        lines = [f'System Info {VERSION}', f'Qt {qVersion()} • psutil {psutil.__version__}',
                 'Normal collection is read-only and unprivileged.',
                 'Optional protected reads use fixed system tools through desktop authorization.', '', 'Optional tools:']
        bundle = str(getattr(sys, '_MEIPASS', ''))
        for name in ('lscpu','lsblk','lspci','lsusb','ip','iw','nmcli','xrandr','smartctl','dmidecode','pkexec'):
            path = which(name)
            status = 'Bundled fallback' if path and bundle and path.startswith(bundle) else path or 'Not installed'
            lines.append(f'{name}: {status}')
        dialog = QDialog(self); dialog.setWindowTitle('About System Info / optional tools'); dialog.resize(700, 460)
        layout = QVBoxLayout(dialog); text = QPlainTextEdit('\n'.join(lines)); text.setReadOnly(True); layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        dialog.exec()

    def closeEvent(self, event):
        self.auto_timer.stop()
        self.closed_when_finished = True
        if self.worker:
            if not self.worker.action: self.worker.cancel.set()
            self.status.setText('Finishing the current read before closing…'); event.ignore()
        else:
            if self.persist:
                self.settings.setValue('geometry', self.saveGeometry())
                self.settings.setValue('technical', self.technical.isChecked())
            event.accept()


def main():
    app = QApplication(sys.argv); app.setStyle('Fusion')
    app.setApplicationName('SystemInfo'); app.setApplicationDisplayName('System Info')
    app.setDesktopFileName('io.github.edjenn1998.SystemInfo')
    window = Window(); window.show(); return app.exec()
