#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "$0")" && pwd)
python_bin=${SYSTEM_INFO_PYTHON:-python3.12}
build_root=${SYSTEM_INFO_BUILD_ROOT:-/tmp/system-info-build}
export SYSTEM_INFO_BUILD_ROOT="$build_root"
"$python_bin" -m pip check
"$python_bin" -m PyInstaller --noconfirm --clean \
  --workpath "$build_root/work" --distpath "$build_root/dist" "$project_dir/SystemInfo-portable.spec"
"$python_bin" "$project_dir/tools/audit_bundle.py" "$build_root/dist/SystemInfo" \
  --max-glibc "${SYSTEM_INFO_MAX_GLIBC:-2.35}" > "$build_root/abi-audit.json"
"$python_bin" "$project_dir/tools/collect_licenses.py" \
  "$build_root/dist/SystemInfo/share" "$build_root/native-sources.json"
QT_QPA_PLATFORM=offscreen "$build_root/dist/SystemInfo/SystemInfo" --self-test
