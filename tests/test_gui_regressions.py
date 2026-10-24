import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QTreeWidget
from system_info.cancellation import checkpoint
from system_info.collectors.base import Collector
from system_info.demo import example_snapshot, fixture_collectors
from system_info.gui import Window, Worker

APP = QApplication.instance() or QApplication([])


class GuiRegressionTests(unittest.TestCase):
    def setUp(self):
        self.window = Window(auto_collect=False, persist=False)
        self.window.show_result(example_snapshot()); self.window.show(); APP.processEvents()

    def tearDown(self):
        if self.window.worker and not self.window.worker.action: self.window.worker.cancel.set()
        self.wait()
        self.window.close(); APP.processEvents()

    def wait(self):
        deadline = time.monotonic() + 10
        while self.window.worker:
            APP.processEvents(); time.sleep(.005)
            if time.monotonic() > deadline: self.fail('Worker did not finish')
        APP.processEvents()

    def test_completed_workers_are_released(self):
        for _ in range(5):
            worker = Worker(context={'dmi_sections':[]}, collectors=fixture_collectors(), parent=self.window)
            self.window.start_worker(worker, self.window.show_result); self.wait()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertLessEqual(len(self.window.findChildren(Worker)), 1)

    def test_rebuild_releases_old_trees(self):
        for _ in range(10): self.window.rebuild()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(len(self.window.findChildren(QTreeWidget)), len(self.window.snapshot.categories))

    def test_tab_and_collapsed_group_survive_refresh(self):
        index = next(i for i,c in enumerate(self.window.snapshot.categories) if c.name == 'storage')
        self.window.tabs.setCurrentIndex(index)
        tree = self.window.trees[index]
        group = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if tree.topLevelItem(i).text(0)=='Installed drives')
        group.setExpanded(False)
        self.window.technical.setChecked(True)
        self.assertEqual(self.window.tabs.currentIndex(), index)
        tree = self.window.trees[index]
        group = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if tree.topLevelItem(i).text(0)=='Installed drives')
        self.assertFalse(group.isExpanded())

    def slow_worker(self):
        entered = threading.Event()
        class Slow(Collector):
            name='slow'; title='Slow'
            def collect(self):
                entered.set(); self.context['cancel_event'].wait(5); checkpoint()
                return self.new_result()
        worker = Worker(collectors=[Slow], parent=self.window)
        self.window.start_worker(worker, self.window.show_result)
        self.assertTrue(entered.wait(2))
        return worker

    def test_cancel_keeps_last_complete_snapshot(self):
        original = self.window.snapshot
        self.slow_worker(); self.window.cancel.click(); self.wait()
        self.assertIs(self.window.snapshot, original)
        self.assertTrue(self.window.export.isEnabled())
        self.assertIn('Cancelled', self.window.status.text())

    def test_close_cancels_normal_collection_and_waits_safely(self):
        self.slow_worker(); self.window.close(); self.wait(); APP.processEvents()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window.auto_timer.isActive())

    def test_protected_result_refresh_is_connected_before_start(self):
        with patch('system_info.gui.read_protected', return_value=[{'type':1,'fields':{}}]), \
             patch.object(self.window, 'collect') as refresh:
            self.window.read_firmware()
            self.assertFalse(self.window.cancel.isEnabled())
            self.wait(); APP.processEvents()
            self.assertEqual(self.window.context['dmi_sections'][0]['type'], 1)
            refresh.assert_called_once()

    def test_busy_read_cannot_launch_another_protected_request(self):
        self.slow_worker()
        with patch('system_info.gui.read_protected') as read:
            self.window.read_firmware(); self.window.read_health()
            read.assert_not_called()
        self.window.cancel.click(); self.wait()

    def test_copy_report_respects_private_checkbox(self):
        self.window.copy_report()
        self.assertNotIn('DEMO-SERIAL-PRIVATE', QApplication.clipboard().text())
        self.window.private.setChecked(False); self.window.copy_report()
        self.assertIn('DEMO-SERIAL-PRIVATE', QApplication.clipboard().text())

    def test_auto_refresh_never_starts_duplicate_workers(self):
        worker = self.slow_worker()
        self.window.collect(); self.window.collect()
        self.assertIs(self.window.worker, worker)
        self.window.cancel.click(); self.wait()

    def test_new_controls_fit_small_window(self):
        self.window.resize(850, 560); APP.processEvents()
        for button in (self.window.refresh, self.window.copy, self.window.export, self.window.protected,
                       self.window.drive_health, self.window.cancel):
            point = button.mapTo(self.window, button.rect().bottomRight())
            self.assertLess(point.x(), self.window.width())
            self.assertLess(point.y(), self.window.height())

    def test_queued_refresh_cannot_restart_collection_after_close(self):
        self.window.close()
        self.window.collect()
        self.assertIsNone(self.window.worker)
