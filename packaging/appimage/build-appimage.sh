#!/usr/bin/env bash
set -euo pipefail
project_dir=$(cd -- "$(dirname -- "$0")/../.." && pwd)
python_bin=${SYSTEM_INFO_PYTHON:-python3.12}
build_root=${SYSTEM_INFO_BUILD_ROOT:-/tmp/system-info-build}
export SYSTEM_INFO_PYTHON="$python_bin" SYSTEM_INFO_BUILD_ROOT="$build_root"
version=$("$python_bin" -c 'import sys; sys.path.insert(0,sys.argv[1]); from system_info.version import VERSION; print(VERSION)' "$project_dir")
if [[ $(uname -m) != x86_64 ]]; then
  printf '%s\n' 'This AppImage build targets x86_64 only.' >&2
  exit 1
fi
"$python_bin" -c 'import sys; assert sys.version_info[:2] == (3,12), "Official AppImages use Python 3.12"'
bash "$project_dir/build.sh"
"$python_bin" "$project_dir/tools/fetch_appimage_tools.py" "$build_root/tools"
(cd "$build_root/tools" && ./appimagetool --appimage-extract)
app_dir=$(mktemp -d "$build_root/SystemInfo.AppDir.XXXXXX")
trap 'rm -rf -- "$app_dir"' EXIT
# The packaged root must be searchable by users other than the build account.
chmod 755 "$app_dir"
mkdir -p "$app_dir/usr/lib/system-info" "$app_dir/usr/share/system-info" "$project_dir/dist"
cp -a "$build_root/dist/SystemInfo/." "$app_dir/usr/lib/system-info/"
mv "$app_dir/usr/lib/system-info/share/"* "$app_dir/usr/share/system-info/"
rmdir "$app_dir/usr/lib/system-info/share"
cp "$project_dir/packaging/appimage/AppRun" "$app_dir/AppRun"; chmod +x "$app_dir/AppRun"
cp "$project_dir/packaging/appimage/io.github.edjenn1998.SystemInfo.desktop" "$app_dir/"
cp "$project_dir/assets/system-info.svg" "$app_dir/io.github.edjenn1998.SystemInfo.svg"
ln -s io.github.edjenn1998.SystemInfo.svg "$app_dir/.DirIcon"
cp "$build_root/abi-audit.json" "$project_dir/dist/abi-audit.json"
cp "$build_root/abi-audit.json" "$project_dir/packaging/appimage/toolchain.json" "$app_dir/usr/share/system-info/"
mkdir -p "$app_dir/usr/share/system-info/licenses/appimage-runtime"
for name in runtime musl libfuse squashfuse zstd zlib; do
  cp "$build_root/tools/$name-license" "$app_dir/usr/share/system-info/licenses/appimage-runtime/"
done
cp "$build_root/tools/qt-lgpl-license" "$app_dir/usr/share/system-info/licenses/Qt-LGPL-3.txt"
output="$project_dir/dist/SystemInfo-$version-x86_64.AppImage"
ARCH=x86_64 "$build_root/tools/squashfs-root/AppRun" --no-appstream \
  --runtime-file "$build_root/tools/runtime" "$app_dir" "$output"
chmod +x "$output"
QT_QPA_PLATFORM=offscreen "$output" --appimage-extract-and-run --self-test
QT_QPA_PLATFORM=xcb xvfb-run -a "$output" --appimage-extract-and-run --self-test
"$output" --appimage-extract-and-run --cli --list
cp "$app_dir/usr/share/system-info/python-dependencies.txt" "$app_dir/usr/share/system-info/native-packages.txt" "$project_dir/dist/"
(cd "$project_dir/dist" && sha256sum "$(basename "$output")" abi-audit.json python-dependencies.txt native-packages.txt > SHA256SUMS)
