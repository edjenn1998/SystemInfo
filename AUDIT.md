# System Info 1.3.0 review

Reviewed the original 1.2 source, collectors, Qt UI, 34 tests, fixture, vendor
ELFs, license archive and compatibility/build records. All original tests passed.

| Finding | Resolution |
| --- | --- |
| Export privacy only touched top-level record keys, leaking nested identifiers and copies in summary prose. | Shared recursive redaction, known-value/prose handling, credential scrubbing and schema-preserving metadata. |
| CLI JSON/text exports lacked the GUI's default privacy. | Private reports by default; explicit `--include-identifiers`, consistent metadata, atomic file output and stderr-only progress. |
| Export could truncate an existing report on a failed write. | Private temporary file, fsync and atomic replacement; cleanup on failure. |
| Nonfinite driver values could create nonstandard JSON or bogus numeric readings. | Normalize nonfinite values to unavailable and reject them in numeric/sensor helpers. |
| Battery runtime/capacity disappeared when design capacity was unavailable; tiny rates were rounded away. | Separate available capacity/runtime from health and use unrounded rates for estimates. |
| A full battery could imply external power despite an explicit offline AC reading. | Prefer exposed online/offline input state over that inference. |
| Non-system memory arrays could be counted as RAM; incomplete inventory could claim full installed capacity. | Filter system arrays, label partial capacities and retain soldered-device distinctions. |
| Unknown or string rotational flags could mislabel drives. | Preserve unknown flags and parse reported boolean forms explicitly, including sysfs fallback. |
| Shared logical volumes could appear multiple times. | Deduplicate by device path and retain additional parent associations. |
| Remote filesystem usage reads could stall hardware collection. | Report their presence without querying remote space by default. |
| Some direct subprocess calls leaked bundled library paths; SMART masks could look like authorization failure. | Common system-tool environment/timeout handling and valid SMART payload parsing regardless of health-bitmask status. |
| Refreshes retained finished workers and discarded tab widgets without deleting them. | Explicit worker/widget cleanup, serialized reads and guarded after-read refreshes. |
| Closing/queued refresh timing could restart collection after the window closed. | Stop timers, cancel normal reads and block queued restarts during/after close. |
| Collection had no cancellation/progress; command cleanup could outlive its timeout. | Shared cooperative tokens, bounded command/pipe cleanup and progress while retaining the previous complete report. |
| X11 modes with negative offsets were ignored; truncated trailing SMBIOS headers were accepted. | Parse signed offsets and reject partial trailing headers. |
| Self-test depended on host hardware and could quit while collection still ran. | Disposable illustrative GUI/report/worker self-test, plus separate real unprivileged collection checks. |
| No tracked AppImage packaging/CI/ignore files or current generated license inventory. | Add pinned build sources, native ABI checks, fresh iw dependency, current notices and Ubuntu 22.04 CI. |
| README described an older binary and contained stale licensing instructions. | Beginner-friendly AppImage guide, explicit compatibility change, GPL notice and historical-record labeling. |

## Verification and remaining limits

88 tests cover original behavior and new failures, plus packaged GUI/report/CLI
smoke checks. Automated protected-read tests use mocks/fixtures and do not ask for
administrator authorization. Live battery/firmware/SMART access still depends on
the target computer and installed desktop authorization agent.

Redaction is best-effort, not guaranteed anonymity. The UI intentionally displays
raw local data; export/copy privacy is separate. Commands are bounded, but native
driver/filesystem calls can delay cooperative stopping. No RAM-timing probes,
hardware writes, SMART self-tests/repairs or uploads have been introduced.

The new maintained Ubuntu 22.04 AppImage baseline requires glibc 2.35; the older
v1.2 glibc 2.30 binary remains available without these new fixes. Reports retain
schema version 1.2 with additive app-version/privacy metadata. Old vendor binaries,
compatibility records and original release assets are preserved.
