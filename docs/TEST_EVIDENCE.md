# TEST_EVIDENCE — Detect A Clip

Each row cites the command, date, code version and configuration. **Desktop/JVM runs are
LAB or harness evidence on synthetic material.** None is device, rights, legal, store or
release evidence. Tests without a row are planned, not run. Host for every run below:
Windows 11 Pro x64, Python 3.13.15, Temurin JDK 17.0.20.1, kotlinc 2.4.21.

## Automated suites

| Suite | Command | Last result | Code |
|---|---|---|---|
| L0 Python (180 tests, incl. golden freshness, static privacy guard and result-text parity) | `cd l0 && python -m pytest -o addopts=""` | **180 passed** 2026-10-11 locally (idx-flat-5 goldens); CI see below | `cd7e7f0` |
| Pure-Kotlin JVM (76 tests: shared GoldenRunner, Ed25519 RFC vectors and platform agreement, installed pack store incl. halted-child-JVM recovery and revoked signer, coordinator, lifecycle DIAGNOSTIC + RECOGNITION with injected frames, capture boundary, consent, eligibility, recognition golden ×400, DAC-DHASH-v1 ×42, exact path ×9, end-to-end ×6, format contract ×49, manifest contract ×68, full pipeline ×12, result display ×11, FrameView strides/ownership) | `bash android/run-jvm-tests.sh` | **OK (76 tests)** 2026-10-11 | `3bd085a`+ |
| Android app build (AGP 9.4.1, Gradle 9.8.1, compileSdk 37, minSdk 34) | `bash android/gradle-local.sh :app:assembleDebug` | **BUILD SUCCESSFUL** 2026-10-10 (`8ea39ae`); both `dac.sourceMode=user_choice` (default) and `app_only` built earlier | `app-debug.apk`, capture disabled (`BuildConfig.CAPTURE_ENABLED = false`) |
| Android APK permissions | `aapt2 dump permissions app/build/outputs/apk/debug/app-debug.apk` | **only** FOREGROUND_SERVICE, FOREGROUND_SERVICE_MEDIA_PROJECTION, POST_NOTIFICATIONS (re-checked at `8ea39ae`); no INTERNET / network / audio; allowBackup=false | CTRL-G00 A1 (build level) |
| Android lint | `bash android/gradle-local.sh :app:lintDebug` | **No issues found** 2026-10-10 | `8ea39ae` |
| Android unit tests, Gradle-compiled, **run by direct JUnit** (not a Gradle test task) | `bash android/gradle-local.sh :app:compileDebugUnitTestKotlin` then `bash android/junit-on-gradle-classes.sh` | **OK (76 tests)** 2026-10-11 | `3bd085a`+; Gradle's own `testDebugUnitTest` cannot fork its test JVM on this host and runs in CI instead |

### CI (GitHub Actions on PR #1, ubuntu-latest / macos-latest runners)

| Commit | Workflow / job | Result |
|---|---|---|
| `05f437b` | ci: Python, pure Kotlin, Android | **success** (pure Kotlin OK 55; Android BUILD SUCCESSFUL, 51 tasks) |
| `05f437b`, `70f672c` | swift-core | **failure**: Swift 6.3.3 could not type-check `DacDhash.swift:18` in reasonable time |
| `63d1a45` | swift-core | `swift build` **succeeded** (Swift core library compiled on macOS); `swift test` **failed** to compile one test closure (`PipelineGoldenTests.swift:75`) |
| `3f77273` | swift-core | **success**: `swift build` + `swift test`, 38 tests, 0 failures, 0 skipped (macOS 26.6.2, Xcode 26.6, Swift 6.3.3); run 38069331306 |
| `3f77273` | ci | **success**: Python 172 passed; pure Kotlin OK (56); Android assemble + lint + Gradle `testDebugUnitTest` 56 tests, 0 failures; run 38069331278 |
| `8ea39ae` | swift-core | **success**: 43 tests, 0 failures, 0 skipped, incl. `CaptureBoundaryTests` (5); run 38072195095 |
| `8ea39ae` | ci | **success**: Python 172 passed; pure Kotlin OK (64); Android assemble + lint + Gradle `testDebugUnitTest` 64 tests, 0 failures, 0 errors, 0 skipped; run 38072195084 |
| `673f4bc` | swift-core `ios-sdk` | probe ran (Xcode 26.6, iOS SDK 26.5; ScreenCaptureKit absent); iOS compile **failed** on a wrong scheme name |
| `3d4dec7` | swift-core `ios-sdk` | **success**: Swift core `xcodebuild` for `generic/platform=iOS` (arm64, unsigned) and `generic/platform=iOS Simulator`; probe typecheck correctly fails for ScreenCaptureKit |
| `3d4dec7` | ci | **success**: Python 172; pure Kotlin 71; Gradle `testDebugUnitTest` 71 incl. the halted-child-JVM store test |
| `5d67f4b` | swift-core `ios-app` | **success**: XcodeGen 2.46.0; LAB app built unsigned for iOS devices; XCUITest `testTermsGateAndStartRefusedWithoutCaptureCell` passed on iPhone 17 Pro simulator, iOS 26.5 (63 s); run 38074672108 |
| `0be2ccc` | swift-core (3 jobs) | **success**: `swift test` 57 tests, 0 failures, 0 skipped (incl. `PackStoreTests` 7 with the `_exit` crash child, `LabFlowTests` 7); iOS core compile; LAB app build + UI test; run 38075819185 |
| `0be2ccc` | ci | **success**: Python 180 passed; pure Kotlin OK (71); Gradle `testDebugUnitTest` 71, 0 failures; run 38075819156 |
| `d0727fb` | ci + swift-core | **success**: Python, pure Kotlin, Android (ci); `swift test` 60 tests, 0 failures, 0 skipped (incl. `PixelBufferFrameTests` 3); iOS core compile; LAB app build + UI test with the accessibility changes; runs 38076577340 / 38076574765 |
| `2fb5544` (final code) | ci | **success**: Python 180 passed; pure Kotlin OK (72); Android assemble + lint + Gradle `testDebugUnitTest` 72 tests, 0 failures, 0 skipped; run 38077113139 |
| `2fb5544` (final code) | swift-core (3 jobs) | **success**: `swift test` 61 tests, 0 failures, 0 skipped (incl. revoked-signer store test); Swift core built for iOS device + simulator; LAB app built unsigned for iOS devices, `LabJourneyUITests` passed on iPhone 17 Pro simulator iOS 26.5; run 38077108303 |
| `622ddad` (final code) | ci + android-emulator | **success**: Python 180, pure Kotlin 76, Android build/lint/`testDebugUnitTest` 76; API 36 emulator `LabJourneyTest` (8) + `EngineOnArtTest` (8) = **OK (16 tests)** on push and pull_request runs 38104261512 / 38104264906; swift-core unchanged since `6db2692` (success) |

The CI rows are source-level evidence only. `swift-core` compiles the platform-independent
Swift package; it is not an iOS app build, archive, signing or device test, and the
ScreenCaptureKit adapter is not compiled anywhere (the framework is absent from the newest
available iOS SDK, 26.5). The `ios-app` job's simulator UI test and unsigned device build are not
device, signing, archive or store evidence.

| Android **emulator** manual run (not a device) | Android Emulator 37.2.12, AVD Pixel 7, `system-images;android-37.0;google_apis;x86_64` (Android 17, build `CE2A.260420.019`, userdebug), WHPX; APK installed with `adb install -r`, driven by `adb`/`uiautomator` | 2026-10-10, see the emulator table below | capture disabled build; synthetic only |
| Android instrumented / device tests | — | **NOT RUN** (no device, B-01) | — |
| iOS app build / ScreenCaptureKit adapter / device tests | — | **NOT RUN** (no Xcode project, provisioning or iPhone, B-02) | — |

### Android emulator session (2026-10-10, LAB debug APK with capture disabled; emulator ≠ device)

| Check | Observed | Result |
|---|---|---|
| Launch | Terms dialog first; `dumpsys media_projection` = null; no app service | PASS |
| Layout on Android 15+ edge-to-edge | **FAIL before fix**: banner and *Start scan* drawn under the action bar (Start at y=253, bar to y≈283). Fixed (NoActionBar theme + system-bar/cutout insets); after the fix every control is below the status bar | FIXED, re-checked |
| Decline, reopen | Start disabled, "Terms not accepted"; Terms prompt shown again on reopen | PASS |
| Start → disclosure → *Not now* | No system prompt; state IDLE | PASS |
| Start → *Continue* | Real Android 17 prompt "Share your screen with Detect A Clip LAB?", default "Share one app"; `user_choice` mode also offers "Share entire screen" (CAP-A03 data point, emulator) | observed |
| Prompt → *Cancel* | State FAILED, "Screen sharing was not allowed or was revoked. Nothing was kept.", Details PERMISSION_DENIED; no app service; media projection null (ED-28) | PASS |
| Prompt → share one app (Clock) within 29 s | State CANCELLED, "Cancelled. No result was kept.", Details IN_APP_CANCEL; no media projection created (capture disabled) | PASS |
| Grant later than the 60 s permission budget | State FAILED, PERMISSION_TIMEOUT (fail closed) | PASS |
| Force-stop and reopen | IDLE, no result (memory-only), Terms acceptance kept | PASS |
| CAP-A03 `app_only` build (`-Pdac.sourceMode=app_only`, `SOURCE_MODE = "app_only"`, API 37 path compiled) | The system picker still listed **"Share entire screen"**, it was selectable and enabled **"Share screen"**. The system log did not show which projection config the picker received, so this run cannot tell "config not honoured" from "config not delivered" | **NOT ENFORCED on this emulator**; CAP-A03 stays a device test; D01 consumer scope must not rely on the app-only request |
| App-private files | only `shared_prefs/consent.xml` with key `terms.receipt`; no INTERNET/network permission | PASS |
| Instrumented `LabJourneyTest` (UiAutomator 2.4.0, `am instrument`, 7 tests: Terms gate, controls below the status bar, Not now, picker Cancel, rotation + Back, grant with capture off, font scale 2.0) | **OK (7 tests)** in 210 s after two harness fixes (emulator System UI freezes; Android 17 prompt hides its buttons in landscape) | PASS (emulator) |
| Rotate while the system prompt is open | Prompt stays, buttons off-screen in landscape; Back → PERMISSION_DENIED, no service, no projection; result survives rotating back | PASS |
| Kill the app process (`kill -9`) while the prompt is open | Prompt stays; after the emulator's System UI froze in the app chooser and was restarted, the app reopened IDLE with no service, no projection and no ghost scan. The grant-after-kill step itself could not be completed on this emulator | PARTIAL (emulator ANR) |
| Screen off while the prompt is open | Android dismissed the prompt; app recorded PERMISSION_DENIED; projection null | PASS |
| Forced backup (`bmgr backupnow`) | "Backup is not allowed" (`allowBackup=false`) | PASS |
| `EngineOnArtTest` (instrumented): every golden on Android's ART runtime | **OK (8 tests)** on the API 37 emulator, 2026-10-11: recognition 400, dac_dhash 42, exact 9, e2e 6, format 60 + 15 display, manifest 68, pipeline 12, all 0 mismatches (idx-flat-5 goldens); Ed25519 served by `AndroidOpenSSL`; pipeline per-frame median 3 ms / max 36 ms, finish max 7 ms at 64×36 on x86 emulator (not a device number) | PASS (emulator) |
| `EngineOnArtTest` on the **Android 16** CI emulator (`BE2A.250530.026.F3`, run 38103633491) | all goldens 0 mismatches (pipeline 12, recognition 400, exact 9, format 75, e2e 6, manifest 68, dac_dhash 42); `Signature("Ed25519")` provider `AndroidKeyStoreBCWorkaround` but the X.509 key spec cannot be loaded, so the verifier backend is **pure-kotlin** (ED-33); pure and platform verifiers agree on 68/68 signed cases. Before ED-33 this runtime rejected every valid pack (run 38096375545: 11 mismatches, all ACCEPT cases). Pipeline per-frame median 5–18 ms on the software-rendered CI emulator (not a device number) | PASS (emulator, CI) |
| `LabJourneyTest#journeyWorksWithNotificationsDenied` (P05-T06b, D09) | POST_NOTIFICATIONS revoked: Terms, Start, system prompt and Cancel -> PERMISSION_DENIED work unchanged; no notification prompt from the app; no service, no projection | PASS (emulator, 2026-10-11) |
| CI emulator (`android-emulator.yml`, ubuntu-latest + KVM, Android 16 `BE2A.250530.026.F3`, `swiftshader_indirect`) | `LabJourneyTest` **OK (7 tests)** in 84 s at `640113d`, run 38087540726 | PASS (emulator, CI) |
| CI emulator on API 37 (Linux host) | `surfaceflinger` aborts in the goldfish mapper (`Assertion failed: !rcEnc->featureInfo()->hasReadColorBufferDma`) with `swiftshader_indirect`, `swangle_indirect` (+`-feature -ReadColorBufferDma`) and `guest`; an emulator/host defect, not the app. API 37 coverage comes from the Windows host run above | emulator limitation |

Host limits: 15.5 GB RAM with about 2 GB free made the emulator's System UI freeze several times (ANR); a CI
emulator job (`android-emulator.yml`, KVM, API 36) repeats the instrumented suite. Locally `-gpu swiftshader_indirect`
worked; `swangle_indirect` made the whole system unresponsive on this host. Not covered by the emulator: frames, OEM behaviour, real lock/chip/notification timing, energy, and
anything needing capture enabled (G00/DATA-L00 Part B). These stay device tests (B-01).

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
| CONS-02 / CONS-03 | Terms receipt, reopen, translation-only change | PASS (JVM logic) | Kotlin `ConsentAndEligibilityTest` | Android storage adapter and UI compiled (AGP); no device run |
| CAP-07 | Expired/mismatched cell, untrusted time | PASS (JVM logic) | `EligibilityGate` tests | device identity of cells not established |
| IDX-01 | Index size, build, staging, atomic activation | PASS (desktop dev scope) | LAB reports (bytes/hour per descriptor), `tests/test_store.py` | 50/100/250 MB packs and device cold-start not measured |
| RIGHTS-02 | Epoch cannot roll back (incl. restored state) | PASS (dev scope) | `test_epoch_survives_restore_of_old_state_file` | licensed packs absent (B-05) |
| RIGHTS-03 | Unaccepted D07 region method refused | PASS (dev scope) | `test_unaccepted_region_assurance_method…` | no licensed grants |
| RIGHTS-04 | Lab lease through reboot / rollback / untrusted time | PASS (desktop analogue) | `test_lab_lease_*` | device clocks and real leases not tested |
| AI-01 | Clean known works | PASS (LAB, exploratory) | FINAL `lab_final_*` | CLEAN correct named 60/60 for every descriptor on the sealed FINAL family (10 works); far below F05 counts |
| AI-02 | Absent works | INCONCLUSIVE (LAB) | FINAL reports | false VERIFIED 0/66 all descriptors; THUMB32 1/66 FALSE_POSSIBLE; n cannot bound a 2 % rate |
| AI-03 | Edited / montage | INCONCLUSIVE (LAB) | FINAL reports | EDITED correct named 45/60 (HASH64) to 35/60 (THUMB512); no wrong title; MONTAGE never VERIFIED |
| AI-05 | Shared intros, recaps, stock footage | PASS (LAB, exploratory) | FINAL reports | SERIES_INTRO series level 4/4; RECAP 4/4 correct; STOCK_SHARED abstained 4/4; no episode named without unique evidence |
| AI-01/02/03/05 (v4) | Sealed FINAL4, fixtures-v4, CAL4 calibration | PASS / INCONCLUSIVE (LAB) | `lab_final4_HASH64_20261009T230913Z`, `lab_final4_DACDHASH_20261009T231309Z` | wrong-title VERIFIED 0 and POSSIBLE 0 for both; CLEAN 119–120/120; EDITED 78 (HASH64) / 85 (DACDHASH) /120; ABSENT abstained 130/130; 20 works per family, still far below F05 counts |
| (port) | DAC-CROP-v1 / DAC-QUAL-v1 / mirrored hash Python = Kotlin = Swift | PASS (JVM, macOS CI) | `ExactPathGoldenTest`, `ExactPathGoldenTests` | synthetic frames |
| AI-06 | Independent evaluation | BLOCKED | — | no independent evaluator (B-06) |
| (port) | Kotlin and Swift verification/decision = Python reference | PASS (JVM, macOS CI) | `RecognitionGoldenTest`, `RecognitionGoldenTests` (400 cases); mutation check caught an injected off-by-one | — |
| (port) | DAC-DHASH-v1 bit-exact Python = Kotlin | PASS (JVM) | `DacDhashGoldenTest` | candidate descriptor only |
| (port) | End-to-end: Python pack → Kotlin parse/hash/retrieve/verify/decide | PASS (JVM) | `EndToEndGoldenTest` (single, brightness, absent, montage, shared intro, unique episode) | synthetic block frames; no OpenCV preprocessing, no quality checks, no device |
| AI-07 | Distinct non-match states | PASS (LAB) | UNUSABLE 9/9 expected in every family; OUTSIDE_CATALOGUE unconstructible | — |
| (contract) | Index format v3/v4/v5 verdicts and result display names Python = Kotlin = Swift = ART | PASS (JVM, macOS CI, emulator) | `FormatContractTest`/`FormatContractTests`/`EngineOnArtTest` on `golden_format_cases.txt` (60 cases + 15 display rows incl. series names, ED-32) | — |
| (contract) | Manifest V2 verdicts Python = Kotlin, state unchanged on rejection | PASS (JVM) | `ManifestContractTest` on `golden_manifest_cases.txt` (68: validity windows, offsets, calendar edges, rollback, signature, compatibility) | Swift `ManifestContractTests` pass in CI with CryptoKit (not skipped) |
| (pipeline) | Delivered frames → selector → DAC-CROP/QUAL/DHASH (+mirror) → retrieval → verification → decision, Python = Kotlin | PASS (JVM) | `PipelineGoldenTest` on `golden_pipeline.txt` (12 queries incl. letterbox, pillarbox, PiP, mirror, black feed, static, montage, shared intro, jitter), padded RGBA strides | synthetic frames; no OS capture |
| (pipeline) | Recognition-mode lifecycle with injected frames | PASS (JVM) | `RecognitionLifecycleTest` (commit with work/edition/episode, cancel mid-verify, late frames, stale worker after lock, deadline overrun, entitlement revoked at commit, DIAGNOSTIC unchanged) | no screen capture; device timing B-01 |
| (boundary) | Consent denial, unsolicited grants, frame geometry | PASS (JVM, macOS CI) | Kotlin `CaptureBoundaryTest` (8), Swift `CaptureBoundaryTests` (5); APK permission dump | OS refusal of a consent-less mediaProjection FGS, real `ImageReader`/`CVPixelBuffer` layouts and the iOS picker are device checks (B-01, B-02) |
| (privacy) | Static guard: logging/network/media/Photos APIs, capture-path persistence, permission set, capture-off defaults, iOS usage keys | PASS (static, CI) | `l0/tests/test_privacy_static.py` (7); mutation adding `print`/`Log.d`/`UserDefaults`/`Files.write` fails 3 tests | Source-level only; DATA-L01/L02 device inspection BLOCKED |
| (UI) | iOS LAB journey: Terms first, decline keeps scanning off, Terms readable, Start refused before any prompt | PASS (simulator, CI) | `LabJourneyUITests` on iPhone 17 Pro simulator iOS 26.5; `LabFlowTests` (7) | Simulator only; no capture path on iOS (B-02) |
| (UI) | Result wording identical on Android and iOS, reserved outcomes unreachable | PASS (static) | `l0/tests/test_ui_text_parity.py` | en-GB only |
| SEC-01b | Ed25519 verification on Android | PASS (emulators) | platform provider on Android 17; pure-Kotlin RFC 8032 fallback on Android 16; `Ed25519Test` (RFC 8032 §7.1 vectors, tampered/non-canonical inputs, 68-case agreement) | self-implemented verifier awaits independent review (P06-T08); physical devices B-01 |
| SEC-03 | Stale tuple, revoked signer, mixed tuple, corrupt staged update | PASS (dev scope: desktop, JVM, macOS) | Rollback floors and restored-state tests; `revokedSignerBlocksActivationOfAnInstalledPack` (Kotlin) / `testRevokedSignerBlocksActivationOfAnInstalledPack` (Swift); manifest/payload mismatch cases (68); torn-write and halted-process store tests | Development key only; no licensed tuple or release key (B-05, P06-T05) |
| IDX-01b | Store recovery after abrupt termination | PASS (desktop, JVM, macOS) | Python `test_store.py::test_abrupt_termination_at_every_io_step_recovers` (`os._exit`); Kotlin `PackStoreTest` (child JVM `Runtime.halt`, before and mid-write); Swift `PackStoreTests` (`_exit` crash child, before and mid-write) | desktop/CI filesystems only; Android/iOS device storage not tested |
| DATA-L00…L03, CAP-A*, CAP-I*, UX-*, OPS-*, REL-* | Device, network, store | BLOCKED | — | B-01, B-02, B-07, B-08 |

## LAB report index (synthetic, purpose LAB)

| Report | Family | Thresholds | Notes |
|---|---|---|---|
| `lab_report_20261009T135848Z` | gen-2 gallery | dev | historical; SEEN; OF-01 origin |
| `lab_dev_*_20261009T19*` | DEV (v3.1) | dev-uncalibrated-2 | tuning family |
| `evidence/calibration/calibration_*.json` | CALIBRATION | grid | frozen per descriptor |
| `lab_final_*_20261009T194*/195*` | FINAL (sealed, run once) | frozen calibration | code = commit `45e0123` for recognition; "+dirty" marks unrelated store/test files written during the run |
| `lab_calibrated_*_20261009T1953*` | DEV + CALIBRATION | frozen calibration | DEV OF-01 cases: no wrong title for HASH64; THUMB32 1 FALSE_POSSIBLE |
| `lab_dev4_*` | DEV (v4 queries) | dev-uncalibrated-2 | DACDHASH 8 wrong-title POSSIBLE before calibration (kept) |
| `evidence/calibration/v4/*` | CAL4 | grid | frozen HASH64, DACDHASH |
| `lab_final4_*` | FINAL4 (sealed, run once) | frozen CAL4 calibration | recognition code = commit `965ec1d`; "+dirty" = iOS/test files written during the run |

Recognition times in reports are desktop CPU times under 12 parallel workers, excluding
synthetic rendering. They are not F05 device latencies.
