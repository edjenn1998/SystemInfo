# Build with the pinned standalone Python and verified compatibility libraries.
import os
from pathlib import Path
root=Path(os.environ['SYSTEM_INFO_COMPAT_ROOT'])
paths=[root/'lib/x86_64-linux-gnu',root/'usr/lib/x86_64-linux-gnu']
binaries=[]
for path in paths:
    for file in sorted(path.glob('*.so*')):
        if file.is_file() and file.name not in ('libc.so.6','libm.so.6','libpthread.so.0','libdl.so.2','librt.so.1','ld-linux-x86-64.so.2'):
            binaries.append((str(file),'.'))
binaries.append((str(root/'sbin/iw' if (root/'sbin/iw').exists() else root/'usr/sbin/iw'),'bundled_tools'))
a=Analysis(['launch_system_info.py'],pathex=[],binaries=binaries,datas=[],hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=[],noarchive=False)
# Network/TLS and VNC plugins are not used by this local QtWidgets application.
# Exclude their optional host OpenSSL3 dependency rather than bundling a newer ABI.
a.binaries=[entry for entry in a.binaries if not (entry[0] in ('libcrypto.so.3','libssl.so.3') or '/tls/' in entry[0] or entry[0].endswith('/libqvnc.so'))]
pyz=PYZ(a.pure)
if os.environ.get('SYSTEM_INFO_BUILD_MODE')=='onedir':
    exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SystemInfo-1.2-Linux-x86_64',debug=False,strip=False,upx=False,console=True)
    coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='SystemInfo-1.2-Linux-x86_64')
else:
    exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='SystemInfo-1.2-Linux-x86_64',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True)
