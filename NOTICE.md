# Third-party notices

System Info is distributed under **GPL-3.0**; see LICENSE. Third-party components
retain their respective licenses. Current releases generate notices and exact
dependency inventories from the actual build environment; they are included at
`usr/share/system-info/` inside the AppImage.

- Qt/PySide6: open-source LGPLv3/GPLv3 distribution. Generated notices name the
  actual version and link to version-specific Qt/PySide source.
- Python: Python Software Foundation license; https://www.python.org/downloads/source/
- psutil: BSD-3-Clause; https://github.com/giampaolo/psutil
- iw: its permissive license, plus libnl dependency notices. The maintained
  distribution package used for each build is recorded in native-packages.txt.
- PyInstaller: GPL with distribution exception; https://pyinstaller.org/
- AppImage runtime: MIT, with musl, libfuse, squashfuse, zstd and zlib components;
  https://github.com/AppImage/type2-runtime. Hash-verified runtime/component license
  texts are included; corresponding build/source instructions are in its BUILD.md.

Application source and pinned build tooling permit rebuilding with replacement
libraries. The pre-existing `licenses.tar.xz`, `compatibility/` manifests and
`vendor/` binaries are historical **1.2** records; their old version/license wording
does not describe current releases. Current packages use generated notices and a
fresh system iw package, not those old vendor binaries. GPU drivers and optional
privileged utilities remain supplied by the user's operating system.
