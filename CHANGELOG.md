# 1.4.0

- Add installed RAM, procfs usable RAM and **Unavailable to Linux**, calculated in
  bytes before display rounding. Withhold the difference for missing, incomplete,
  duplicate or inconsistent firmware inventory; never display a negative value.
- Explain firmware/iGPU/mapping and other reservations without attributing the
  entire difference to hardware. RAM use is usable minus available memory.
- Group the existing Qt Memory tab into System Memory, Memory Configuration,
  Installed Modules and Swap, with interpretation tooltips and swap availability.
- Distinguish configured transfer rate from firmware-reported module maximum;
  decode array error correction and conservatively identify ECC-capable modules
  only with corroborating width information. Do not infer accessible slots/channels.
- Explicitly mark tCL/tRCD/tRP/tRAS and command rate as unavailable: no validated
  safe portable interface is implemented. SPD profiles are never active timings.
- Add calculation, binary-unit, inventory-validation and offscreen UI regressions.
  No new runtime dependencies; protected firmware reads remain optional.
- Refresh the verified AppImage build-tool pin and make the temporary AppDir root
  world-readable/searchable for upstream's new packaging permission validation.

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
