"""Orchestrator: wires collectors in order into a SystemSnapshot.

`main.py` (CLI) and any future GUI both go through this class only.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .collectors.board import BoardCollector
from .collectors.cpu import CpuCollector
from .collectors.devices import DevicesCollector
from .collectors.gpu import GpuCollector
from .collectors.memory import MemoryCollector
from .collectors.network import NetworkCollector
from .collectors.power import PowerCollector
from .collectors.storage import StorageCollector
from .collectors.system import SystemCollector
from .collectors.hardware import HardwareCollector
from .core import SystemSnapshot
from .overview import overview
from .collectors.base import run_cmd
from .inventory import DMI_TYPES

# Order here defines default display order everywhere.
ALL_COLLECTORS = [
    SystemCollector,
    CpuCollector,
    MemoryCollector,
    BoardCollector,
    StorageCollector,
    GpuCollector,
    NetworkCollector,
    DevicesCollector,
    PowerCollector,
    HardwareCollector,
]


class SystemInfoApp:
    def __init__(self, collectors=None, context=None):
        self.context = dict(context or {})
        self.collectors = list(ALL_COLLECTORS if collectors is None else collectors)

    @property
    def category_names(self) -> list[str]:
        return (["overview"] if self.collectors else []) + [c.name for c in self.collectors]

    def collect_all(self, parallel: bool = True) -> SystemSnapshot:
        self.prepare_context()
        snapshot = SystemSnapshot()
        if not parallel or len(self.collectors) <= 1:
            for klass in self.collectors:
                snapshot.add(klass(context=self.context).run())
            if self.collectors: snapshot.categories.insert(0, overview(snapshot))
            return snapshot

        with ThreadPoolExecutor(max_workers=len(self.collectors)) as pool:
            results = list(pool.map(lambda k: k(context=self.context).run(), self.collectors))
        for res in results:
            snapshot.add(res)
        if self.collectors: snapshot.categories.insert(0, overview(snapshot))
        return snapshot

    def prepare_context(self):
        from pathlib import Path
        from .smbios import parse_smbios
        from .inventory import dmi_sections
        if 'dmi_sections' in self.context or 'dmi_text' in self.context:
            sections=self.context.get('dmi_sections') or dmi_sections(self.context.get('dmi_text',''))
            self.context['dmi_status']='available' if any(s['type'] in (16,17) for s in sections) else self.context.get('dmi_status','not_reported')
            return
        try:
            self.context['dmi_sections']=parse_smbios(Path('/sys/firmware/dmi/tables/DMI').read_bytes())
            self.context['dmi_status']='available'
        except PermissionError:self.context['dmi_status']='authorization_required'
        except FileNotFoundError:self.context['dmi_status']='interface_absent'
        except (OSError,ValueError):self.context['dmi_status']='read_failed'
        if 'dmi_sections' not in self.context:
            text=run_cmd(['dmidecode','--type',DMI_TYPES]) or ''
            self.context['dmi_text']=text
            if any(s['type'] in (16,17) for s in dmi_sections(text)):self.context['dmi_status']='available'

    def collect(self, names: list[str]) -> SystemSnapshot:
        self.prepare_context()
        wanted = set(names)
        if "overview" in wanted:
            return self.collect_all()
        chosen = [c for c in self.collectors if c.name in wanted]
        missing = wanted - {c.name for c in chosen}
        snapshot = SystemSnapshot()
        for klass in chosen:
            snapshot.add(klass(context=self.context).run())
        for name in sorted(missing):
            snapshot.add(_missing_result(name))
        return snapshot


def _missing_result(name: str):
    from .core import CategoryResult
    r = CategoryResult(name=name, title=name)
    r.note = "unknown category"
    return r
