# System Info 1.2 — personal hardware information and troubleshooting

Download **SystemInfo-1.2-Linux-x86_64**, enable Properties → Permissions →
Allow executing as a program, and double-click it. Python, Qt, psutil, and a
Wi-Fi querying fallback are bundled. The first launch may take a moment while
its libraries unpack into a private temporary directory.

    chmod +x SystemInfo-1.2-Linux-x86_64
    ./SystemInfo-1.2-Linux-x86_64

This executable targets Intel/AMD x86-64 GNU/Linux. Its bundled ELF libraries
were audited to require glibc 2.30 or newer. The GUI and CLI were tested on the
build system; this is not a guarantee of operation on every distribution.
A graphical desktop and standard graphics drivers are required for the GUI.
ARM and musl-based distributions such as Alpine require separate native builds.
Hardware collection adapts to available Linux interfaces and tools; it does not
assume a particular computer model. Missing firmware data remains unavailable.

## What changed

- Overview: computer identity, OS, CPU/core layout, RAM, BIOS, installed drives,
  graphics, network, battery, key temperatures and readings that warrant attention.
- Processor: turbo/boost control, driver-reported maximum clock (including boost
  where the driver exposes it), frequency limits, governor and current usage.
  A reported maximum is not a promise of sustained/all-core frequency.
- Memory: usable RAM, installed capacity and firmware banks when readable,
  populated/empty counts, manufacturer, part number, type, rated/configured speed,
  form factor and rank. Soldered devices are not described as upgrade slots.
  Live CL/tRCD/tRP/tRAS timings are not supported by this app. Firmware
  authorization does not unlock timings. Access errors and missing firmware
  inventory are reported separately.
- Motherboard / BIOS: manufacturer, model, revision, BIOS version/date, boot mode,
  Secure Boot when readable, and protected system/board identifiers.
- Storage: physical drives and type (NVMe, SATA, USB, SSD/HDD), model, capacity,
  firmware and available health readings. Partitions and logical volumes appear
  beneath their drive with filesystem UUID, PARTUUID, label, mount points and
  matching `/etc/fstab` entries. Loop devices remain technical details.
  fstab mount options are never collected because they can contain credentials.
- Graphics: adapters separated from displays. Unused connectors are technical
  details and are never counted as additional GPUs. Supported/preferred display
  modes are not mislabeled as the current desktop resolution.
- Network: physical Wi-Fi/Ethernet and Bluetooth, adapter/driver identity, Wi-Fi
  link rate, signal, SSID and traffic errors where available. Loopback and VPN
  interfaces are technical details. AP advertised rate is labeled separately
  when the negotiated link rate cannot be obtained. Link rate is not a speed test.
- Power / Battery: power source, charge, status, manufacturer/model, full/design
  capacity, health/wear, cycle count, volts/amps/watts and runtime estimate.
  Health is full capacity divided by design capacity, not current charge.
- Devices: connected and built-in USB devices first; hubs and controller plumbing
  stay in the technical view.
- Sensors: useful labeled readings, with duplicate Dell driver readings moved
  to the technical view. A zero-RPM fan can be stopped normally.

JSON export includes collected technical data. Export privacy is enabled by
default and hides UUIDs, fstab identifiers, network addresses, SSIDs and serials.
Disable export privacy if your troubleshooting report needs these identifiers.
It cannot guarantee that every vendor-supplied free-form string is anonymous.

## Read protected hardware details

Click **Read memory / BIOS details** for memory bank and protected BIOS
information. Your desktop's authorization agent may ask for your administrator
password. The operation reads only `/sys/firmware/dmi/tables/DMI` with the system
`cat` executable and decodes SMBIOS inside the app. The GUI stays unprivileged.
If direct reading fails, a trusted system `dmidecode` may be used as a fallback.
It does not edit firmware or probe memory buses.
The inventory stays in memory for the session; opening the app again may require
another read. Firmware that omits a field cannot be made to report it.

Desktop authorization uses `pkexec` (polkit). On a system without a desktop
polkit agent or exposed SMBIOS table, this operation cannot obtain the data.
Normal collection still works.

## Read drive health

Click **Read drive health**, select an installed drive, and authorize the
read-only `smartctl -j -a` command. This requires the system `smartmontools`
package; on Debian/Ubuntu it can be installed with:

    sudo apt install smartmontools

The report includes supported SMART status, temperature, hours, NVMe endurance
usage/errors and SATA reallocated/pending/uncorrectable counts. Some USB bridges
or controllers do not expose SMART. Protected health readings are cached for
this session; click the button again to update them. No self-test, write or repair
command is run. Firmware details and SMART reads use trusted system binaries,
never an elevated copy of the bundled Python executable.

## Source, tests and build

Python 3.10+ (3.12 recommended):

    python3 -m venv .venv
    . .venv/bin/activate
    python3 -m pip install -r requirements.txt
    python3 launch_system_info.py
    python3 -m unittest discover -s tests -v

CLI:

    python3 launch_system_info.py --cli --json
    python3 launch_system_info.py --cli overview
    python3 launch_system_info.py --cli cpu memory
    python3 launch_system_info.py --cli --list

Use `./build.sh` to build on a compatible Linux system. The bundled iw binary
needs libnl when running directly from source; install `iw` from your distribution
instead if needed. The standalone build includes its libnl dependencies.

Tests cover firmware bank decoding and truncated input, physical-drive filtering,
one GPU versus seven connectors, battery unit/health calculations, turbo controls,
Wi-Fi rates, command validation, redaction and GUI behavior. Protected reads are
tested with fixtures; actual firmware permissions and battery data must be verified
on the target computer.

## Third-party components

Application version: 1.2.0. Third-party license texts/notices are included in `licenses.tar.xz`.
Qt/PySide6 uses LGPLv3/GPLv3 or commercial licensing; psutil uses BSD-3-Clause;
PyInstaller has a bootloader distribution exception; iw and xcb-cursor have
permissive licenses. Review licenses and choose a license for your own application
before public distribution. Rebuildable source and dependency versions are included.

## Portable release build

The release uses CPython 3.12.15 from python-build-standalone (20261003),
PySide6_Essentials 6.8.3, psutil 7.2.2 and PyInstaller 6.22.3.
`compatibility/manifest.json` records SHA256-verified Debian bullseye packages.
Extract those packages with `dpkg-deb -x` into a compatibility root, install
the pinned dependencies into a standalone-Python virtual environment, then run:

    SYSTEM_INFO_COMPAT_ROOT=/path/to/root LD_LIBRARY_PATH=/path/to/root/usr/lib/x86_64-linux-gnu:/path/to/root/lib/x86_64-linux-gnu python -m PyInstaller --clean --noconfirm --workpath /tmp/system-info-build --distpath /tmp/system-info-dist SystemInfo-portable.spec

Use `SYSTEM_INFO_BUILD_MODE=onedir` for an inspectable build and run
`scripts/audit_linux_abi.py` on that directory. `compatibility/abi-audit.json`
records the release dependency audit. `build.sh` instead makes a native build;
its minimum glibc depends on the machine used to build it. For broad
distribution, build on an older supported baseline and test target desktops.
