"""Packaged GUI/report smoke test, using disposable illustrative fixtures only."""
import json
import tempfile
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from .gui import Window, Worker
from .demo import fixture_collectors
from .reports import render_report, write_report
from .version import VERSION


def run(args=()):
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    window = Window(auto_collect=False, persist=False); window.show()
    try:
        worker = Worker(context={'dmi_sections':[], 'dmi_status':'not_reported'},
                        collectors=fixture_collectors(), parent=window)
        window.start_worker(worker, window.show_result)
        deadline = time.monotonic() + 15
        while window.worker:
            app.processEvents(); time.sleep(.01)
            if time.monotonic() > deadline: raise AssertionError('Fixture collection timed out')
        app.processEvents()
        assert window.snapshot is not None and window.tabs.count() == 11
        assert not window.windowIcon().isNull()
        payload = render_report(window.snapshot)
        assert json.loads(payload)['app_version'] == VERSION
        assert all(value not in payload for value in ('DEMO-HOST-PRIVATE','DEMO-SERIAL-PRIVATE','DEMO-UUID-PRIVATE','aa:bb:cc:dd:ee:ff'))
        window.copy_report()
        assert 'DEMO-SERIAL-PRIVATE' not in QApplication.clipboard().text()
        with tempfile.TemporaryDirectory(prefix='system-info-test-') as directory:
            for format, extension in [('json','.json'), ('text','.txt')]:
                path = Path(directory) / ('report'+extension)
                write_report(path, render_report(window.snapshot, format))
                assert path.stat().st_size > 0
        if '--screenshot' in args:
            app.processEvents()
            assert window.grab().save(args[args.index('--screenshot') + 1])
        storage = next(i for i, category in enumerate(window.snapshot.categories) if category.name == 'storage')
        window.tabs.setCurrentIndex(storage); window.search.setText('NVMe')
        tree = window.trees[storage]
        assert any(not tree.topLevelItem(i).isHidden() for i in range(tree.topLevelItemCount()))
        window.search.clear(); window.technical.setChecked(True)
        assert window.tabs.currentIndex() == storage
        print(f'System Info {VERSION} self-test passed: fixture collection, GUI, search, private JSON/text/copy exports and icon')
        return 0
    finally:
        if window.worker:
            window.worker.cancel.set(); window.worker.wait(5000); app.processEvents()
        window.close(); app.processEvents()
