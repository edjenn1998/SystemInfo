# Implemented architecture

Read-only collectors -> ordered SystemSnapshot -> derived Overview -> Qt display
or shared JSON/text report rendering. CLI and GUI use the same orchestrator.

- `core.py`: typed fields/categories/snapshots and JSON-safe normalization.
- `app.py`: bounded parallel/sequential collection, shared context, deterministic
  category order, progress and cancellation.
- `collectors/`: CPU, memory, board, storage, graphics/displays, network/Bluetooth,
  devices, power, sensors and OS data. Missing optional tools degrade gracefully.
- `cancellation.py` and `collectors/base.py`: scoped tokens, readable file helpers,
  bounded subprocess reads and restored system-library environments.
- `reports.py`: shared recursive best-effort privacy, JSON/text output and atomic
  file export. Raw library snapshots remain available; report identifiers require
  explicit UI/CLI opt-in.
- `protected.py` / `smbios.py`: explicitly requested read-only system-tool access
  and bounded firmware decoding. The GUI/bundled Python stay unprivileged.
- `gui.py`: serialized workers, auto-refresh/cancel controls, view preservation,
  export/copy, optional-tool visibility and safe teardown.
- `demo.py` / `selftest.py`: illustrative fixtures and deterministic packaged checks.
- `packaging/`, `tools/`, CI: maintained AppImage payload, pinned toolchain,
  dependency/license inventories and ABI validation.

See README.md and AUDIT.md for operating instructions and remaining limits.
Future hardware coverage should use driver/firmware documentation and new fixtures;
live RAM timings and invasive hardware probes are not implemented.
