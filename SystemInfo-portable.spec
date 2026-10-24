"""Maintained onedir payload shared by native and AppImage builds."""
import ctypes.util
import json
import os
import shutil
import subprocess
from pathlib import Path

project = Path(SPECPATH)
build_root = Path(os.environ.get('SYSTEM_INFO_BUILD_ROOT', '/tmp/system-info-build'))
cache = subprocess.check_output(['ldconfig', '-p'], text=True).splitlines()


def library(name, soname):
    found = ctypes.util.find_library(name) or soname
    for line in cache:
        if line.strip().startswith(found + ' '): return line.split('=>', 1)[1].strip()
    for folder in os.environ.get('LD_LIBRARY_PATH', '').split(':'):
        if folder and (Path(folder) / soname).is_file(): return str(Path(folder) / soname)
    raise RuntimeError(f'Install the system {name} shared library before building')


# Bundle neutral GL dispatch libraries, not vendor-specific graphics drivers.
native = [library(name, soname) for name, soname in (
    ('EGL','libEGL.so.1'), ('GL','libGL.so.1'), ('GLX','libGLX.so.0'), ('GLdispatch','libGLdispatch.so.0'))]
iw = os.environ.get('SYSTEM_INFO_IW') or shutil.which('iw')
if not iw or not Path(iw).is_file():
    raise RuntimeError('Install the system iw package for the bundled Wi-Fi fallback')
a = Analysis(
    [str(project / 'launch_system_info.py')], pathex=[str(project)],
    binaries=[(path, '.') for path in native] + [(iw, 'bundled_tools')],
    datas=[(str(project / 'LICENSE'), '.'), (str(project / 'assets/system-info.svg'), 'assets')],
    excludes=['tkinter','PySide6.QtWebEngineCore','PySide6.QtQml','PySide6.QtQuick'],
    noarchive=False,
)
build_root.mkdir(parents=True, exist_ok=True)
(build_root / 'native-sources.json').write_text(json.dumps([item[1] for item in a.binaries], indent=2))
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SystemInfo',
          debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='SystemInfo')
