# IMPLEMENTATION_STATUS — Detect A Clip

Statuses: NOT_STARTED · IN_PROGRESS · IMPLEMENTED_NOT_VERIFIED · PASS · FAIL · BLOCKED ·
INCONCLUSIVE · DEFERRED · UNVERIFIED. A PASS cites a command/run, date, commit and
configuration in `docs/TEST_EVIDENCE.md`. "Source exists" is never "complete".

Tracks: **DESKTOP-L0** (Python harness on this Windows host) · **ANDROID** · **IOS**.

## Phase summary

| Phase | Status | Notes |
|---|---|---|
| P00 | IN_PROGRESS | T01 done; T02 UNVERIFIED (no SDK installed); T03/T04/T05 BLOCKED (B-03/B-04); T06/T07/T08/T09 in progress on desktop track. |
| P01 | NOT_STARTED / BLOCKED | Source preparation possible; compile + capture BLOCKED (B-01). |
| P02 | BLOCKED | B-02. Source/spec preparation only. |
| P03 | IN_PROGRESS (L0 items only) | L1 items BLOCKED (B-05). |
| P04 | IN_PROGRESS (desktop LAB only) | RELEASE purpose BLOCKED (B-06). |
| P05–P10 | NOT_STARTED | Need native gates and external inputs. |
| P11 | DEFERRED | Per roadmap. Nothing enabled. |

## Task register (86 tasks)

| Task | Track | Status | Evidence / note |
|---|---|---|---|
| P00-T01 | ALL | PASS (inventory) | `docs/ENVIRONMENT.md` 2026-10-09. Desktop: Win 11 Pro x64, 14 logical CPUs, 15.8 GB RAM, 34 GB free; Python 3.13.15, numpy 2.5.3, opencv 5.0.0, Pillow 12.3.0, Node 22.23.2, git 2.55, gh 2.101 (authenticated). Absent: JDK, Android SDK/adb/Gradle, Android device, macOS/Xcode/iPhone, provisioning. |
| P00-T02 | ANDROID/IOS | UNVERIFIED | No installed headers on host. Documentary status only (S03/S04/Q03, S05–S11, V11). Local SDK install attempt tracked in RESUME_STATE. |
| P00-T03 | ALL | BLOCKED | B-03 |
| P00-T04 | ALL | BLOCKED | B-04. Limited development authorization recorded in DECISIONS.md. |
| P00-T05 | ALL | BLOCKED | B-05 (counsel). Query vs corpus act separation is encoded in schema `RightsGrant.permitted_acts`. |
| P00-T06 | DESKTOP-L0 | IN_PROGRESS | Desktop CTRL-G00 controls exist in code (no network, no frame files, memory-only). THREAT_MODEL / DPIA_SCREENING documents NOT_STARTED. |
| P00-T07 | DESKTOP-L0 | IMPLEMENTED_NOT_VERIFIED | `l0/dac_l0/synth/`: 20 works × 3 editions, 10 absent works, 6 natural scenes, 7 synthetic private/overlay screens; hashes in `l0/assets/ASSET_MANIFEST.json`. Needs named rights reviewer sign-off (grant status PENDING_REVIEW). |
| P00-T08 | DESKTOP-L0 | IMPLEMENTED_NOT_VERIFIED | `l0/dac_l0/eval/protocol.py`: frozen splits, separate denominators, Wilson + cluster bootstrap, rare-event rule. Independent AI-06 setup review not available. |
| P00-T09 | ALL | PASS (document level) | TRACE-01 test; see TEST_EVIDENCE. |
| P01-T01 | ANDROID | IMPLEMENTED_NOT_VERIFIED | `android/`: no INTERNET, capture disabled by default, mediaProjection FGS, coordinator/selector + JVM tests. Not compiled (B-09); Part A not run (B-01). |
| P01-T02…T08 | ANDROID | BLOCKED | B-01 (device), B-09 (SDK). CAP-A03 plan in `android/CAP-A03_PLAN.md`. |
| P02-T01…T06 | IOS | BLOCKED | B-02. Swift coordinator port + XCTests + checklist in `ios/` (IMPLEMENTED_NOT_VERIFIED). |
| P03-T01 | DESKTOP-L0 | IMPLEMENTED_NOT_VERIFIED | `l0/dac_l0/schemas.py` work/edition IDs and locators. Series/episode/alias tables and migrations not yet built. |
| P03-T02 | L1 | BLOCKED | B-05; L0 contributor grant manifest in `l0/assets/RIGHTS_MANIFEST.json`. |
| P03-T03 | DESKTOP-L0 | PASS (desktop) | Reproducible build (bit-exact rebuild test); bytes per reference hour measured (IDX-01 desktop). |
| P03-T04 | DESKTOP-L0 | PASS (L0 dev scope) | Signed UNCALIBRATED manifest, fail-closed loader, SEC-01 basic tests. |
| P03-T05, T06, T07 | L1 | BLOCKED | B-05 |
| P04-T01 | DESKTOP-L0 | IMPLEMENTED_NOT_VERIFIED | Quality flags + normalisation + black-bar crop on fixtures. Device frames BLOCKED. |
| P04-T02 | DESKTOP-L0 | PASS (LAB) | HASH64 / THUMB32 / THUMB144 baselines at 2 s; see LAB report. 1 s/5 s/shot sampling and the 528 B row not yet compared. |
| P04-T03 | DESKTOP-L0 | IN_PROGRESS | Temporal verification + montage segmentation implemented; montage/recap/shared-footage queries not yet in the evaluation set. |
| P04-T04 | DESKTOP-L0 | NOT_STARTED | |
| P04-T05 | DESKTOP-L0 | IN_PROGRESS | One result enum; OUTSIDE_CATALOGUE unreachable; thresholds UNCALIBRATED (OF-01 open). |
| P04-T06 | DESKTOP-L0 | IN_PROGRESS | Clean/edited/absent/unusable LAB run done; leakage audit not done. |
| P04-T07 | DESKTOP-L0 | BLOCKED | Independent evaluator absent (B-06). |
| P04-T08 | ANDROID/IOS | BLOCKED | B-01/B-02/B-07 |
| P05-T01…T07 | ALL | NOT_STARTED | Need G00/G-NATIVE. |
| P06-T01…T08 | ALL | NOT_STARTED | |
| P07-T01…T07 | ALL | BLOCKED | B-03 + native gates |
| P08-T01…T07 | ALL | BLOCKED | B-05 |
| P09-T01…T07 | ALL | BLOCKED | D04 / B-04 |
| P10-T01…T06 | ALL | BLOCKED | B-08 |
| P11-T01…T06 | ALL | DEFERRED | Roadmap. |

## Gate register (13 rows)

| Gate | Status | Note |
|---|---|---|
| G00 (desktop L0) | IN_PROGRESS | Needs lawful synthetic assets + protocol + CTRL-G00 desktop controls. No phone required. |
| G00 (Android) | BLOCKED | B-01 + DATA-L00 Part A |
| G00 (iOS) | BLOCKED | B-02 + DATA-L00 Part A |
| G01 | BLOCKED | B-01 |
| G02 | BLOCKED | B-02 |
| G03-L0 | IN_PROGRESS | Engineering items done (schemas, builder, UNCALIBRATED manifest, tamper rejection). Rights reviewer sign-off of the synthetic grant still needed. |
| G03-L1 | BLOCKED | B-05 |
| G04 | IN_PROGRESS (LAB) | First LAB report recorded; RELEASE purpose BLOCKED (B-06). |
| G05–G10 | NOT_STARTED / BLOCKED | |
| G11 | DEFERRED | |
