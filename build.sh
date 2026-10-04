#!/bin/sh
set -eu
python3 -m pip install -r requirements.txt pyinstaller==6.22.3
system_info_arch=$(uname -m)
set -- --noconfirm --clean --onefile --name "SystemInfo-1.2-Linux-${system_info_arch}" --distpath deliverables
if [ "$system_info_arch" = x86_64 ]; then
    set -- "$@" --add-binary "vendor/libxcb-cursor.so.0:." --add-binary "vendor/iw:bundled_tools"
fi
python3 -m PyInstaller "$@" launch_system_info.py
