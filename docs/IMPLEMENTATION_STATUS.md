# IMPLEMENTATION_STATUS — Detect A Clip

Statuses: NOT_STARTED · IN_PROGRESS · IMPLEMENTED_NOT_VERIFIED · PASS · FAIL · BLOCKED ·
INCONCLUSIVE · DEFERRED · UNVERIFIED. PASS rows cite evidence in `docs/TEST_EVIDENCE.md`.
"Compiled on the JVM" means pure-Kotlin files only; the Android app is compiled separately with AGP.

Tracks: **DESKTOP-L0** (Python harness) · **ANDROID** · **IOS**.

## What exists, by platform (2026-10-10)

| Platform | Works now | Not verified / missing |
|---|---|---|
| Desktop L0 | Synthetic fixtures (v3.1, v4) with challenge cases; descriptors incl. the integer-exact DACDHASH path; index format contract `idx-flat-5` (reads v3/v4) with names, aliases, shared scenes and series names; temporal verification; series/episode-aware decision; result display names; calibration; manifest V1/V2 with fail-closed validity rules; crash-safe pack store; lab leases; LAB runner. 172 tests | Real footage, real devices, release statistics |
| Android | LAB app builds to a debug APK (AGP 9.4.1, compileSdk 37); lint clean; no INTERNET in the merged manifest; capture off by default; a declined picker never starts the capture service; CAP-A03 `app_only` config compiled; the whole engine reproduces every golden on ART (emulator, `EngineOnArtTest`) with Ed25519 from AndroidOpenSSL. Pure-Kotlin engine: format contract, manifest V2 loader, `RecognitionSession` + `FrameView`, lifecycle DIAGNOSTIC and RECOGNITION modes. 64 unit tests (kotlinc, Gradle-compiled direct JUnit, and Gradle `testDebugUnitTest` in CI) | Any device run (B-01); RECOGNITION mode is not wired to real capture (ED-25) |
| iOS | Swift core package (CI: `swift build` + `swift test`) mirrors the Kotlin engine (format v4, manifest V2 via CryptoKit, session, lifecycle with background-task guard, consent/eligibility) with XCTests on the shared golden files; ScreenCaptureKit adapter skeleton | Swift core compiled and tested on macOS and built for iOS device/simulator in CI; LAB app shell built unsigned and UI-tested on a simulator; ScreenCaptureKit adapter (SDK absent), signing and devices (B-02) |

## Unfinished implementation vs external verification

| Kind | Items |
|---|---|
| Executable here, done this round | Pack validity rules, edition index fix, format contract in three languages (now idx-flat-5 with series names), crash-recovery proof, manifest V2, recognition path with injected frames, result display parity, CI workflows (all green), Swift core compile/test, capture-boundary fixes (ED-28), iOS SDK probe and LAB app shell, device-side pack stores, privacy guard, emulator journeys (local API 37, CI API 36), engine goldens on ART |
| Implementation still open (no external input needed, but needs a method decision) | DACDHASH partial montage segmentation; POSSIBLE-under-competition setting; UI_LIKE has no exact-path counterpart; wiring RECOGNITION mode to real capture (waits for gate evidence by design) |
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
| P01-T01 | IN_PROGRESS (build items PASS) | Debug APK builds (AGP 9.4.1, compileSdk 37); merged manifest without INTERNET; lint clean; capture disabled by default; installed and exercised on an Android 17 emulator (picker, deny, grant-with-capture-off, timeout, process death, file inventory; TEST_EVIDENCE). Device, network isolation and witness items of Part A BLOCKED (B-01) |
| P01-T02…T08 | BLOCKED (device) · emulator partial | B-01 (device, G00). Emulator (Android 17, capture disabled): picker deny/grant, rotation, process kill and screen off mid-prompt, permission timeout, memory-only result, backup refusal, and CAP-A03 `app_only` not enforced by the emulator picker (TEST_EVIDENCE). Lifecycle races also covered on the JVM |
| P02-T01 | IN_PROGRESS (installed-header scope) | `ios/scripts/sdk_probe.sh` in CI pins Xcode 26.6 / iOS SDK 26.5: ScreenCaptureKit framework **absent** for iOS; ReplayKit picker/sample handler present without deprecation attributes (SDK_MATRIX). The iOS 27 ScreenCaptureKit symbols need Xcode 27 (B-02) |
| P02-T02 | IN_PROGRESS | a. LAB app shell (`ios/LabApp`, SwiftUI over tested `LabFlow`): Terms gate, eligibility before any prompt, disclosure, Stop/Cancel, Discard, result-on-return; capture disabled; builds unsigned for iOS devices, journey UI test on a simulator (CI). b. finite background-task guard compiled. Picker/stream and DATA-L00 Part A need the ScreenCaptureKit SDK and a device (B-02) |
| P02-T03…T06 | BLOCKED | B-02 (device, provisioning, iOS 27 SDK) |
| P03-T01 | IMPLEMENTED_NOT_VERIFIED | work/edition/series/episode IDs, names, aliases, shared scenes and series names in `idx-flat-5` (v3/v4 migrate); same contract in Python/Kotlin/Swift (60 cases + 15 display rows). Real catalogue metadata needs B-05 |
| P03-T02 | BLOCKED | B-05 (L0 self-grant manifest exists) |
| P03-T03 | PASS (desktop) | reproducible builder, bytes/hour per descriptor |
| P03-T04 | PASS (L0 dev scope) | signed manifests V1/V2, fail-closed loader (ED-21, ED-24), SEC-01; 68 manifest cases Python = Kotlin; Swift via CI |
| P03-T05 | BLOCKED | B-05 |
| P03-T06 | IMPLEMENTED_NOT_VERIFIED (dev fixtures) | Python, Kotlin (`PackStore.kt`) and Swift (`PackStore.swift`) stores: immutable slots, single commit point, floors, fail-closed recovery; recovery after abrupt termination proven in all three (Python `os._exit`, Kotlin halted child JVM, Swift `_exit` child process) at every I/O step (ED-23). Not wired into the LAB apps (ED-25); device storage semantics and licensed packs BLOCKED (B-01, B-02, B-05) |
| P03-T07 | BLOCKED | B-05 |
| P04-T01 | IMPLEMENTED_NOT_VERIFIED | quality flags, uniform-border crop; device frames BLOCKED |
| P04-T02 | PASS (LAB) | 4 descriptors; sampling study (DEV) in `evidence/studies/` |
| P04-T03 | PASS (LAB, exploratory) | temporal verification, montage segments, recaps, stock footage |
| P04-T04 | IMPLEMENTED_NOT_VERIFIED | series→episode→edition→time hierarchy; multilingual work and series names with locale fallback; result display parity Python = Kotlin (15 cases), Swift via CI. Series-level results show the series' own name (ED-32) |
| P04-T05 | PASS (L0 synthetic calibration) | v3.1 (CALIBRATION) and v4 (CAL4) frozen per descriptor; LAB-only status |
| P04-T06 | PASS (LAB) | all kinds incl. leakage audit; sealed FINAL (v3.1) and FINAL4 (v4) each run once; failures kept in reports |
| P04-T07 | BLOCKED | independent evaluator (B-06) |
| P04-T08 | BLOCKED (device) · prep IMPLEMENTED | recognition path (selector → FrameView → DAC-CROP/QUAL/DHASH → retrieval → verification → decision → memory-only commit) = Python on 12 pipeline queries; injected-frame lifecycle tests (ED-25); iOS CVPixelBuffer → luma copy tested on macOS CoreVideo. Device budgets need B-01/B-02/B-07 |
| P05-T01 | IMPLEMENTED_NOT_VERIFIED | `docs/legal/*` DRAFT_FOR_COUNSEL; legal review required |
| P05-T02 | IMPLEMENTED_NOT_VERIFIED | `ConsentRecords` (JVM-tested); Android UI compiled; no device run (B-01) |
| P05-T03 | IMPLEMENTED_NOT_VERIFIED | native picker from user action only; denied/empty picker result fails closed (ED-28); `EligibilityGate` denies unsupported cell/pack before any prompt (JVM, Swift, iOS UI test) |
| P05-T04 | IMPLEMENTED_NOT_VERIFIED | canonical states; honest outcome-specific text identical on Android and iOS (parity test); SYNTHETIC label on every named candidate; memory-only result with 15-minute expiry on return |
| P05-T05 | IMPLEMENTED_NOT_VERIFIED | in-app Stop/Cancel, notification Stop→Cancel switch; UX-02 device runs BLOCKED |
| P05-T06 | IMPLEMENTED_NOT_VERIFIED | decline/changed-terms/late-callback logic tested on JVM |
| P05-T07 | BLOCKED (study) · a. partial | a. live regions for status on Android and iOS; every control reachable at font scale 2.0 (emulator instrumented test); screen-reader walkthrough on devices not done; b. en-GB only; c. study needs D04 |
| P06-T01 | IN_PROGRESS | threat model draft; actual API path evidence BLOCKED |
| P06-T02 | PASS (harness) | lease/generation/race tests (Python + Kotlin + Swift); capture-boundary regressions (consent denial, unsolicited grants, frame geometry) |
| P06-T03 | IMPLEMENTED_NOT_VERIFIED | static guard (`test_privacy_static.py`): no logging/network/media/Photos APIs in shipped sources, no persistence in capture-path files, exact Android permission set, capture disabled by default, no sensitive iOS usage keys; DATA-L02 device inspection BLOCKED |
| P06-T04 | BLOCKED | device soak |
| P06-T05 | IN_PROGRESS | a. SBOM (incl. CI tools); b. bounded strict parsers and signed manifests in three languages; c. key/rollback handling tested for the development key (SEC-03 dev scope: revoked signer, rollback floors, torn staged updates). Release signing keys, rotation and the final licensed tuple are not designed: they need an owner decision and licensed packs (B-04, B-05) |
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
