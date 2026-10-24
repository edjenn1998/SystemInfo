"""Collector base class + shared, safe command/file helpers."""

from __future__ import annotations

import shutil
import os
import sys
import subprocess
import signal
import time
from abc import ABC, abstractmethod
from pathlib import Path

from ..core import CategoryResult
from ..cancellation import Cancelled, checkpoint, collection_scope


def which(cmd: str) -> str | None:
    system = shutil.which(cmd)
    if system: return system
    if Path(cmd).name == cmd:
        for folder in ('/usr/sbin','/sbin','/usr/bin','/bin'):
            path = Path(folder) / cmd
            if path.is_file() and os.access(path, os.X_OK): return str(path)
    if cmd == 'iw':
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        for folder in ('bundled_tools', 'vendor'):
            path = root / folder / 'iw'
            if path.is_file() and os.access(path, os.X_OK): return str(path)
    return None


def system_environment():
    """Use system libraries for external system tools, not bundled Qt/Python libs."""
    environment = {**os.environ, 'LC_ALL': 'C'}
    if getattr(sys, 'frozen', False):
        original = environment.pop('LD_LIBRARY_PATH_ORIG', None)
        if original is None: environment.pop('LD_LIBRARY_PATH', None)
        else: environment['LD_LIBRARY_PATH'] = original
        for key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'PYTHONHOME', 'PYTHONPATH'):
            environment.pop(key, None)
    return environment


def run_process(args: list[str], timeout: int = 5):
    """Read-only tool invocation with bounded runtime and cooperative cancellation."""
    checkpoint()
    executable = which(args[0])
    if executable is None: return None
    bundle = getattr(sys, '_MEIPASS', None)
    bundled = bundle and os.path.commonpath([os.path.abspath(executable), bundle]) == bundle
    environment = {**os.environ, 'LC_ALL': 'C'} if bundled else system_environment()
    process = None
    completed = False
    try:
        process = subprocess.Popen([executable, *args[1:]], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
            env=environment, start_new_session=True)
        deadline = time.monotonic() + timeout
        while True:
            checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0: return None
            try:
                stdout, stderr = process.communicate(timeout=min(.1, remaining))
                completed = True
                checkpoint()
                return subprocess.CompletedProcess([executable, *args[1:]], process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                continue
    except OSError:
        return None
    finally:
        if process is not None and not completed:
            try: os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError): pass
            try:
                process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                # A detached descendant can retain inherited pipe descriptors.
                # Do not let cleanup defeat the original command timeout.
                for stream in (process.stdout, process.stderr):
                    if stream is not None: stream.close()
                try: process.wait(timeout=.2)
                except subprocess.TimeoutExpired: pass


def run_cmd(args: list[str], timeout: int = 5) -> str | None:
    proc = run_process(args, timeout)
    return proc.stdout if proc is not None and proc.returncode == 0 else None


def read_file(path: str) -> str | None:
    checkpoint()
    try:
        value = Path(path).read_text(encoding='utf-8', errors='replace').strip()
        checkpoint()
        return value
    except (OSError, PermissionError):
        return None


class Collector(ABC):
    """A category collector. Must remain pure: return data, never print."""

    name: str = ""
    title: str = ""

    def __init__(self, context=None):
        self.context = context if context is not None else {}

    def new_result(self) -> CategoryResult:
        self._result = CategoryResult(name=self.name, title=self.title)
        return self._result

    @abstractmethod
    def collect(self) -> CategoryResult:
        ...

    def run(self) -> CategoryResult:
        """Template method so one broken collector never sinks the app."""
        with collection_scope(self.context.get('cancel_event')):
            result = self.new_result()
            try:
                value = self.collect()
                checkpoint()
                return value
            except Cancelled:
                raise
            except Exception as exc:  # graceful degradation by design
                result = getattr(self, "_result", result)
                result.note = f"Some information could not be collected: {exc}"
                return result
