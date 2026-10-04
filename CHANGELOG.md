# 1.2.0

Added default partition/volume UUID and PARTUUID display with fstab associations.
Separated firmware permissions, unavailable inventories and unsupported live RAM
timings. Made trusted system-tool discovery distribution-neutral. Rebuilt the
x86-64 release with older compatibility dependencies and audited its glibc ABI.
Added regression coverage for UUID matching, privacy and firmware access states.

# 1.1.0

Reorganized the utility around personal hardware information and troubleshooting.
Added an Overview tab and an optional technical-details view; separated physical
storage, graphics adapters/displays, and physical/virtual network interfaces.
Added protected SMBIOS reads, memory bank/module inventory, CPU turbo controls,
Wi-Fi querying fallback, battery health and runtime calculations, and read-only
protected drive health. Clarified unsupported data and units. Expanded regression
and GUI tests.
