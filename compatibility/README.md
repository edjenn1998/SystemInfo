# Historical 1.2 build records

The manifest, standalone-Python record and ABI report in this folder describe the
older **System Info 1.2** executable. Its audited minimum was glibc 2.30.
The old binary remains in its original GitHub release.

Current AppImages use the maintained Ubuntu 22.04 baseline and a newly generated
native audit (release asset `abi-audit.json`), with a glibc 2.35 maximum build gate.
`SystemInfo-portable.spec` now supplies the inspectable payload used by the new
build scripts. `SYSTEM_INFO_COMPAT_ROOT` and the old vendor binaries are not used
for official current builds. See APPIMAGE.md and NOTICE.md in the project root.
