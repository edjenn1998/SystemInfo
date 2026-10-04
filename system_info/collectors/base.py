"""Collector base class + shared, safe command/file helpers."""

from __future__ import annotations

import shutil
import os
import sys
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from ..core import CategoryResult


def which(cmd: str) -> str | None:
    system = shutil.which(cmd)
    if system: return system
    if cmd == 'iw':
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        for folder in ('bundled_tools', 'vendor'):
            path = root / folder / 'iw'
            if path.is_file() and os.access(path, os.X_OK): return str(path)
    return None


def run_cmd(args: list[str], timeout: int = 5) -> str | None:
    """Run a command, return stdout, or None if it can't run/fails."""
    executable = which(args[0])
    if executable is None: return None
    environment = {**os.environ, 'LC_ALL': 'C'}
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle and not executable.startswith(bundle + os.sep):
        original = environment.get('LD_LIBRARY_PATH_ORIG')
        if original is None: environment.pop('LD_LIBRARY_PATH', None)
        else: environment['LD_LIBRARY_PATH'] = original
    try:
        proc = subprocess.run(
            [executable, *args[1:]],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def read_file(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
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
        result = self.new_result()
        try:
            return self.collect()
        except Exception as exc:  # graceful degradation by design
            result = getattr(self, "_result", result)
            result.note = f"Some information could not be collected: {exc}"
            return result
