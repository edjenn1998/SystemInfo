# System Info App — Plan

## Goal
Collect in-depth system information, grouped by category (CPU, RAM, storage,
GPU, motherboard/BIOS, OS/kernel, network, displays, USB/PCI devices, power,
users/sessions). Pluggable into a future GUI.

## Architecture (GUI-ready)

```
system_info/
├── PLAN.md              this plan
├── main.py              CLI entry point (thin, only formatting/arg parsing)
├── app.py               SystemInfoApp orchestrator (GUI can import this)
├── core.py              CategoryResult / SystemSnapshot data models
├── collectors/          one pure module per category
│   ├── base.py          Collector ABC + safe-run helpers
│   ├── cpu.py
│   ├── memory.py
│   ├── storage.py
│   ├── gpu.py
│   ├── board.py         motherboard/BIOS/chassis
│   ├── network.py       NICs, IPs, DNS, routes
│   ├── display.py       monitors/RES
│   ├── devices.py       USB/PCI overview
│   ├── power.py         battery/AC
│   └── system.py        OS, kernel, uptime, boot, hostname, users
└── renderers/
    ├── text.py          console renderer (current UI)
    └── (json.py)        already trivial via snapshot.to_dict()
```

## Key decisions
- **Collectors are pure:** each `Collector.collect() -> CategoryResult` returns
  data objects only — no printing, no sys.exit. Easy for any UI to consume.
- **Uniform result model (`core.py`):** `Field`, `CategoryResult`,
  `SystemSnapshot`. Each category returns named fields plus structured lists.
  Snapshots are JSON-serializable (`to_dict`) for logging/debugging.
- **Graceful degradation:** each collector reads from `psutil`, `/proc`,
  `/sys`, `dmidecode`-style files, or shells out (`lscpu`, `lsblk`, `ip`,
  `xrandr`) and reports "unavailable" per-field instead of crashing.
- **Extensibility:** add a category = add a collector and register it in
  `app.py`. The GUI later builds tabs from `snapshot.categories`.
- **Threading-ready:** orchestrator supports `collect_all(parallel=True)`
  (collectors are independent, no shared state).

## Verification
- `python3 main.py` (table output), `python3 main.py --json`,
  `python3 main.py cpu memory`, `python3 main.py --list`.
