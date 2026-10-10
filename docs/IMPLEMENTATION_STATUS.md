# IMPLEMENTATION_STATUS — Detect A Clip

Statuses: NOT_STARTED · IN_PROGRESS · IMPLEMENTED_NOT_VERIFIED · PASS · FAIL · BLOCKED ·
INCONCLUSIVE · DEFERRED · UNVERIFIED. PASS rows cite evidence in `docs/TEST_EVIDENCE.md`.
"Compiled on the JVM" means pure-Kotlin files only; the Android app is compiled separately with AGP.

Tracks: **DESKTOP-L0** (Python harness) · **ANDROID** · **IOS**.

## What exists, by platform (2026-10-10)

| Platform | Works now | Not verified / missing |
|---|---|---|
| Desktop L0 | Synthetic fixtures (v3.1, v4) with challenge cases; descriptors incl. the integer-exact DACDHASH path; index format contract `idx-flat-4` (reads v3) with names, aliases and shared scenes; temporal verification; series/episode-aware decision; result display names; calibration; manifest V1/V2 with fail-closed validity rules; crash-safe pack store; lab leases; LAB runner. 172 tests | Real footage, real devices, release statistics |
| Android | LAB app builds to a debug APK (AGP 9.4.1, compileSdk 37); lint clean; no INTERNET in the merged manifest; capture off by default; a declined picker never starts the capture service; CAP-A03 `app_only` config compiled. Pure-Kotlin engine: format contract, manifest V2 loader, `RecognitionSession` + `FrameView`, lifecycle DIAGNOSTIC and RECOGNITION modes. 64 unit tests (kotlinc, Gradle-compiled direct JUnit, and Gradle `testDebugUnitTest` in CI) | Any device run (B-01); RECOGNITION mode is not wired to real capture (ED-25) |
| iOS | Swift core package (CI: `swift build` + `swift test`) mirrors the Kotlin engine (format v4, manifest V2 via CryptoKit, session, lifecycle with background-task guard, consent/eligibility) with XCTests on the shared golden files; ScreenCaptureKit adapter skeleton | Swift core compiled and tested by the macOS CI job (first pass `3f77273`); iOS app, signing, ScreenCaptureKit adapter and devices (B-02) |

## Unfinished implementation vs external verification

| Kind | Items |
|---|---|
| Executable here, done this round | Pack validity rules, edition index fix, format contract in three languages, crash-recovery proof, manifest V2, recognition path with injected frames, result display parity, CI workflows (all green), Swift core compile/test, capture-boundary fixes (ED-28) |
| Implementation still open (no external input needed, but needs a method decision) | DACDHASH partial montage segmentation; POSSIBLE-under-competition setting; UI_LIKE has no exact-path counterpart; series display names (format has no series-name table, results show the series ID); wiring RECOGNITION mode to real capture (waits for gate evidence by design) |
| External verification only | Device runs (B-01, B-02, B-07); rights and licensed packs (B-05); independent evaluation (B-06); legal review (P05-T01); store review (B-08); owner decisions (B-04) |

## Task register (86 tasks)

| Task | Status | Evidence / note |
|---|---|---|
| P00-T01 | PASS | `docs/ENVIRONMENT.md`, `docs/SDK_MATRIX.md` toolchain table |
| P00-T02 | PASS (Android installed/compiled) · UNVERIFIED (iOS) | `docs/SDK_MATRIX.md`: API 34/37 MediaProjection symbols verified with javap and compiled 2026-10-10; device measurement B-01; iOS B-02 |
| P00-T03 | BLOCKED | B-03 |
| P00-T04 | BLOCKED | B-04 |
| P00-T05 | BLOCKED | B-05 |
| P00-T06 | IMPLEMENTED_NOT_VERIFIED | THREAT_MODEL, CTRL-G00 checklist, DPIA screening drafts; reviewer sign-off missing |
| P00-T07 | IMPLEMENTED_NOT_VERIFIED | fixtures v3.1, asset/rights manifests; rights-reviewer sign-off missing |
| P00-T08 | PASS (L0 exploratory protocol) | EVAL_PROTOCOL, preregistered scoring/calibration, sealed FINAL; independent AI-06 setup review missing |
| P00-T09 | PASS (document level) | TRACE-01 |
| P01-T01 | IN_PROGRESS (build items PASS) | Debug APK builds (AGP 9.4.1, compileSdk 37); merged manifest without INTERNET; lint clean; capture disabled by default. Device, network isolation and witness items of Part A BLOCKED (B-01) |
| P01-T02…T08 | BLOCKED | B-01 (device). Lifecycle races covered on JVM only; CAP-A03 `app_only` source configuration compiled (API 37 guard) |
| P02-T01 | UNVERIFIED | documentary symbol review in SDK_MATRIX; headers need Mac (B-02) |
| P02-T02…T06 | BLOCKED | B-02; Swift sources prepared |
| P03-T01 | IMPLEMENTED_NOT_VERIFIED | work/edition/series/episode IDs, names, aliases and shared scenes in `idx-flat-4` (v3 migrates); same contract in Python/Kotlin/Swift (49 cases). Real catalogue metadata needs B-05 |
| P03-T02 | BLOCKED | B-05 (L0 self-grant manifest exists) |
| P03-T03 | PASS (desktop) | reproducible builder, bytes/hour per descriptor |
| P03-T04 | PASS (L0 dev scope) | signed manifests V1/V2, fail-closed loader (ED-21, ED-24), SEC-01; 68 manifest cases Python = Kotlin; Swift via CI |
| P03-T05 | BLOCKED | B-05 |
| P03-T06 | IMPLEMENTED_NOT_VERIFIED (dev fixtures) | immutable slots, single commit point, floors, recovery proven by `os._exit` at every I/O step (ED-23); device storage and licensed/final-tuple part BLOCKED (B-01, B-05) |
| P03-T07 | BLOCKED | B-05 |
| P04-T01 | IMPLEMENTED_NOT_VERIFIED | quality flags, uniform-border crop; device frames BLOCKED |
| P04-T02 | PASS (LAB) | 4 descriptors; sampling study (DEV) in `evidence/studies/` |
| P04-T03 | PASS (LAB, exploratory) | temporal verification, montage segments, recaps, stock footage |
| P04-T04 | IMPLEMENTED_NOT_VERIFIED | series→episode→edition→time hierarchy; multilingual names with locale fallback; result display parity Python = Kotlin (11 cases), Swift via CI. Series-level results show the series ID (no series-name table) |
| P04-T05 | PASS (L0 synthetic calibration) | v3.1 (CALIBRATION) and v4 (CAL4) frozen per descriptor; LAB-only status |
| P04-T06 | PASS (LAB) | all kinds incl. leakage audit; sealed FINAL (v3.1) and FINAL4 (v4) each run once; failures kept in reports |
| P04-T07 | BLOCKED | independent evaluator (B-06) |
| P04-T08 | BLOCKED (device) · prep IMPLEMENTED | recognition path (selector → FrameView → DAC-CROP/QUAL/DHASH → retrieval → verification → decision → memory-only commit) = Python on 12 pipeline queries; injected-frame lifecycle tests (ED-25). Device budgets need B-01/B-02/B-07 |
| P05-T01 | IMPLEMENTED_NOT_VERIFIED | `docs/legal/*` DRAFT_FOR_COUNSEL; legal review required |
| P05-T02 | IMPLEMENTED_NOT_VERIFIED | `ConsentRecords` (JVM-tested); Android UI compiled; no device run (B-01) |
| P05-T03 | IMPLEMENTED_NOT_VERIFIED | native picker from user action; `EligibilityGate` (JVM-tested) |
| P05-T04 | IMPLEMENTED_NOT_VERIFIED | canonical states, uncertain-result wording, memory-only result |
| P05-T05 | IMPLEMENTED_NOT_VERIFIED | in-app Stop/Cancel, notification Stop→Cancel switch; UX-02 device runs BLOCKED |
| P05-T06 | IMPLEMENTED_NOT_VERIFIED | decline/changed-terms/late-callback logic tested on JVM |
| P05-T07 | BLOCKED | accessibility review needs device; study needs D04 |
| P06-T01 | IN_PROGRESS | threat model draft; actual API path evidence BLOCKED |
| P06-T02 | PASS (harness) | lease/generation/race tests (Python + Kotlin + Swift); capture-boundary regressions (consent denial, unsolicited grants, frame geometry) |
| P06-T03 | IMPLEMENTED_NOT_VERIFIED | no logs/SDKs/backups in source; DATA-L02 device inspection BLOCKED |
| P06-T04 | BLOCKED | device soak |
| P06-T05 | IN_PROGRESS | SBOM; bounded parsers; release signing not designed |
| P06-T06 | IMPLEMENTED_NOT_VERIFIED | cell/pack expiry, parsed instants with offsets, untrusted-time denial (JVM + Python, ED-21/ED-26) |
| P06-T07 | IMPLEMENTED_NOT_VERIFIED | data inventory in THREAT_MODEL/privacy draft; counsel BLOCKED |
| P06-T08 | BLOCKED | independent reviewer |
| P07-T01…T07 | BLOCKED | B-03 + native gates; Snapchat OFF |
| P08-T01…T07 | BLOCKED | B-05 |
| P09-T01…T07 | BLOCKED | D04 / B-04 |
| P10-T01…T06 | BLOCKED | B-08 |
| P11-T01…T06 | DEFERRED | roadmap |

## Gates

| Gate | Status |
|---|---|
| G00 desktop | Engineering items ready; named reviewer sign-off missing (D5 in CTRL-G00) |
| G00 Android / iOS | BLOCKED (B-01, B-02) |
| G01 / G02 | BLOCKED |
| G03-L0 | Engineering items ready; rights-reviewer sign-off of the synthetic self-grant missing |
| G03-L1 | BLOCKED (B-05) |
| G04 | LAB record exists (fixtures v3.1 FINAL); RELEASE BLOCKED (B-06) |
| G05–G10 | BLOCKED / NOT_STARTED |
| G11 | DEFERRED |
