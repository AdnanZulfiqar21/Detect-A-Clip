# TEST_EVIDENCE — Detect A Clip

Each row cites the command, date, code version and configuration. **Desktop/JVM runs are
LAB or harness evidence on synthetic material.** None is device, rights, legal, store or
release evidence. Tests without a row are planned, not run. Host for every run below:
Windows 11 Pro x64, Python 3.13.15, Temurin JDK 17.0.20.1, kotlinc 2.4.21.

## Automated suites

| Suite | Command | Last result | Code |
|---|---|---|---|
| L0 Python (124 tests) | `cd l0 && python -m pytest -o addopts=""` | **124 passed** 2026-10-09 | branch `impl/l0-desktop` |
| Pure-Kotlin JVM (32 tests: coordinator, lifecycle, consent, eligibility, recognition golden ×400 cases, DAC-DHASH-v1 golden ×42 frames, end-to-end pack→decision golden ×6 queries, parser/JSON bounds) | `bash android/run-jvm-tests.sh` | **OK (32 tests)** 2026-10-09 | branch `impl/l0-desktop` |
| Android app (Gradle, instrumented) | — | **NOT RUN** (SDK licence pending, B-09; no device, B-01) | — |
| iOS (`swift test`, XCTest) | — | **NOT RUN** (no Mac, B-02) | — |

## Roadmap test IDs

| Test ID | Scope | Status | Evidence | Result / limits |
|---|---|---|---|---|
| TRACE-01 | Roadmap IDs | PASS (document level) | `tests/test_trace.py` | 86 tasks, 54 tests, 13 gate rows, 11 decisions; every referenced ID defined |
| SEC-01 | Pack tamper/parse bounds (L0 dev) | PASS (dev scope) | `tests/test_pack.py` | byte flip, field tamper, unknown/revoked/substituted key, oversize/extra-key manifest, truncation, inflated counts, bad locator; state unchanged on rejection |
| SEC-02 | Interrupt grant/init/sampling/compute/commit | PASS (harness) | Python `test_coordinator.py`; Kotlin `ScanCoordinatorTest`, `CaptureLifecycleTest` | fail closed, one lease, projection stopped at most once; device run BLOCKED |
| LIFE-01 | 1,000 delayed-worker orderings | PASS (harness) | Python + Kotlin (1,000 each, incl. lifecycle randomisation) | 0 stale publications |
| LIFE-02 | Double taps / rapid restarts / interleavings | PASS (harness) | `test_rapid_restarts_and_interleaved_callbacks_1000`, Kotlin `doubleStartSingleLease` | single lease |
| LIFE-03 | Normal close vs abort vs ambiguous callback | PASS (harness) | `test_user_stop_within_100ms…`, Kotlin `asynchronousAckIsTrustedOnlyWithAttributableAdapter` | unattributable stop fails closed; real attribution needs devices |
| LIFE-04 | Default memory mode | PASS (harness) | `test_process_death_loses_result…`, expiry/rollback tests | D08 persistence not built (unapproved) |
| CONS-02 / CONS-03 | Terms receipt, reopen, translation-only change | PASS (JVM logic) | Kotlin `ConsentAndEligibilityTest` | Android storage adapter and UI not compiled |
| CAP-07 | Expired/mismatched cell, untrusted time | PASS (JVM logic) | `EligibilityGate` tests | device identity of cells not established |
| IDX-01 | Index size, build, staging, atomic activation | PASS (desktop dev scope) | LAB reports (bytes/hour per descriptor), `tests/test_store.py` | 50/100/250 MB packs and device cold-start not measured |
| RIGHTS-02 | Epoch cannot roll back (incl. restored state) | PASS (dev scope) | `test_epoch_survives_restore_of_old_state_file` | licensed packs absent (B-05) |
| RIGHTS-03 | Unaccepted D07 region method refused | PASS (dev scope) | `test_unaccepted_region_assurance_method…` | no licensed grants |
| RIGHTS-04 | Lab lease through reboot / rollback / untrusted time | PASS (desktop analogue) | `test_lab_lease_*` | device clocks and real leases not tested |
| AI-01 | Clean known works | PASS (LAB, exploratory) | FINAL `lab_final_*` | CLEAN correct named 60/60 for every descriptor on the sealed FINAL family (10 works); far below F05 counts |
| AI-02 | Absent works | INCONCLUSIVE (LAB) | FINAL reports | false VERIFIED 0/66 all descriptors; THUMB32 1/66 FALSE_POSSIBLE; n cannot bound a 2 % rate |
| AI-03 | Edited / montage | INCONCLUSIVE (LAB) | FINAL reports | EDITED correct named 45/60 (HASH64) to 35/60 (THUMB512); no wrong title; MONTAGE never VERIFIED |
| AI-05 | Shared intros, recaps, stock footage | PASS (LAB, exploratory) | FINAL reports | SERIES_INTRO series level 4/4; RECAP 4/4 correct; STOCK_SHARED abstained 4/4; no episode named without unique evidence |
| AI-06 | Independent evaluation | BLOCKED | — | no independent evaluator (B-06) |
| (port) | Kotlin verification/decision = Python reference | PASS (JVM) | `RecognitionGoldenTest`, mutation check caught an injected off-by-one | Swift port uncompiled |
| (port) | DAC-DHASH-v1 bit-exact Python = Kotlin | PASS (JVM) | `DacDhashGoldenTest` | candidate descriptor only |
| (port) | End-to-end: Python pack → Kotlin parse/hash/retrieve/verify/decide | PASS (JVM) | `EndToEndGoldenTest` (single, brightness, absent, montage, shared intro, unique episode) | synthetic block frames; no OpenCV preprocessing, no quality checks, no device |
| AI-07 | Distinct non-match states | PASS (LAB) | UNUSABLE 9/9 expected in every family; OUTSIDE_CATALOGUE unconstructible | — |
| DATA-L00…L03, CAP-A*, CAP-I*, UX-*, OPS-*, REL-* | Device, network, store | BLOCKED | — | B-01, B-02, B-07, B-08, B-09 |

## LAB report index (synthetic, purpose LAB)

| Report | Family | Thresholds | Notes |
|---|---|---|---|
| `lab_report_20261009T135848Z` | gen-2 gallery | dev | historical; SEEN; OF-01 origin |
| `lab_dev_*_20261009T19*` | DEV (v3.1) | dev-uncalibrated-2 | tuning family |
| `evidence/calibration/calibration_*.json` | CALIBRATION | grid | frozen per descriptor |
| `lab_final_*_20261009T194*/195*` | FINAL (sealed, run once) | frozen calibration | code = commit `45e0123` for recognition; "+dirty" marks unrelated store/test files written during the run |
| `lab_calibrated_*_20261009T1953*` | DEV + CALIBRATION | frozen calibration | DEV OF-01 cases: no wrong title for HASH64; THUMB32 1 FALSE_POSSIBLE |

Recognition times in reports are desktop CPU times under 12 parallel workers, excluding
synthetic rendering. They are not F05 device latencies.
