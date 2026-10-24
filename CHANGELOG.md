# 1.3.0

- Add shared recursive privacy for JSON/text/copied reports, known identifiers in
  summaries, explicit CLI identifier opt-in and atomic private report writes.
- Add text/copy export, CLI file output/progress/version flags and strict JSON
  normalization for nonfinite sensor/driver values.
- Fix battery capacity/runtime availability, small-rate estimates, AC-state
  interpretation, system-memory filtering and partial-capacity reporting.
- Correct unknown/string rotation flags, shared-volume duplication, SMART optional
  fields/exit masks and remote-filesystem collection blocking.
- Restore system library environments for all system-tool paths, keep protected
  commands read-only and reject invalid requests before tool lookup.
- Add cooperative cancellation/progress, optional serialized auto-refresh, worker
  and tab cleanup, preserved view state and safe closing/queued-refresh handling.
- Improve missing-tool visibility, X11 negative-offset modes, firmware truncation
  checks, file decoding and network fallbacks.
- Add deterministic illustrative self-tests, an original icon and tracked demo
  screenshot, plus native audits, maintained iw packaging and generated notices.
- Publish a modern static-runtime AppImage with no-FUSE fallback. The v1.3 build
  targets Ubuntu 22.04+/glibc 2.35; old v1.2/glibc 2.30 assets remain available.
- 88 automated tests, plus packaged GUI/report/CLI verification.

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
