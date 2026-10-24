# Building and verifying System Info

For download/run instructions, including no-FUSE launching, see README.md.

## Official environment

Ubuntu 22.04 x86_64, Python **3.12.15**, and `requirements-build.txt`. Native Qt
dependencies and a fresh system `iw` come from maintained distribution packages;
their exact versions are recorded in each build. Tool/runtime/license hashes are
pinned in `packaging/appimage/toolchain.json`.

```sh
sudo apt-get update
sudo apt-get install iw libegl1 libgl1 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 binutils desktop-file-utils xvfb xauth
# Supply Python 3.12.15; CI uses actions/setup-python.
python3.12 -m venv .venv-build
. .venv-build/bin/activate
python -m pip install -r requirements-build.txt
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
SYSTEM_INFO_PYTHON="$PWD/.venv-build/bin/python" \
SYSTEM_INFO_BUILD_ROOT=/tmp/system-info-build \
bash packaging/appimage/build-appimage.sh
```

Use a clean environment and unused build directory. Building/testing uses extracted
tools and no-FUSE execution, so a FUSE package is not needed. Continuous upstream
URLs can change; a hash mismatch stops the build until deliberately reviewed and
repinned. This is a repeatable documented process, not a claim of byte-identical
results across OS updates.

`build.sh` creates an inspectable payload under `$SYSTEM_INFO_BUILD_ROOT/dist/SystemInfo/`
through `SystemInfo-portable.spec`; it does not install Python dependencies
automatically. `SYSTEM_INFO_IW` can override the helper path for local inspection,
but official notice collection requires the maintained distribution `iw` package.
Old `SYSTEM_INFO_COMPAT_ROOT` and `SYSTEM_INFO_BUILD_MODE` settings are historical.

## Build checks and outputs

The build requires Qt's portable dispatch shims and the iw helper, runs `readelf`
and `ldd` on every ELF object, collects actual native/Python licenses, and tests
the payload. Incomplete inspections fail the build. Current releases reject a
glibc minimum above **2.35**; `SYSTEM_INFO_MAX_GLIBC` can be overridden for local
newer native builds, but that does not make them compatible with older systems.

The final AppImage is tested with offscreen and X11 Qt backends and CLI startup.
GUI smoke tests use illustrative fixtures and never invoke protected reads. The
static runtime has no glibc dependency; the ABI audit covers the payload. Symbol
compatibility alone does not guarantee every desktop/driver/permission setup.

Outputs under `dist/`:

- `SystemInfo-1.3.0-x86_64.AppImage`
- `SHA256SUMS`
- `abi-audit.json`
- `python-dependencies.txt`
- `native-packages.txt`

Current licenses, Python/native inventories and toolchain hashes are also inside
the AppImage at `usr/share/system-info/`. The historical v1.2 glibc 2.30 audit in
`compatibility/` does not apply to these v1.3.0 builds.

## Release procedure

Use the successful GitHub workflow's `SystemInfo-Linux-x86_64` artifact. Download
it, check hashes and run both extraction launch methods with clean library paths.
Check a real unprivileged collection without publishing machine identifiers.
Tag the exact tested commit and upload the five generated files as release assets.
Keep older releases and keep generated binaries out of Git history.
