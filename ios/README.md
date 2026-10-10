# iPhone track (P02): Swift core and specification

**Status:** the iOS app build, archive, signing and every device test are BLOCKED (B-02): this
Windows host has no Xcode project, iOS SDK, provisioning or iPhone. The platform-independent
Swift core in `DetectAClipLab/` is a SwiftPM package. It is compiled and tested only by the
`swift-core` GitHub Actions job on a macOS runner (`.github/workflows/swift-core.yml`): first
pass at `3f77273` (macOS 26.6.2, Xcode 26.6, Swift 6.3.3); results in `docs/TEST_EVIDENCE.md`. That job is not an iOS app build and not device evidence.

## What is here

| File | Purpose |
|---|---|
| `Sources/ScanCoordinator.swift`, `Tests/ScanCoordinatorTests.swift` | Port of `l0/dac_l0/coordinator.py` (F03 event table); LIFE-01/03 orderings |
| `Sources/FrameSelector.swift` | ≤2 fps, ≤3 owned frames, monotonic timestamps |
| `Sources/CaptureLifecycle.swift`, `Tests/CaptureLifecycleTests.swift`, `Tests/RecognitionLifecycleTests.swift`, `Tests/CaptureBoundaryTests.swift` | Port of the Kotlin lifecycle: DIAGNOSTIC and RECOGNITION modes, background-task guard, injected-frame races, picker denial and frame-geometry refusal |
| `Sources/ConsentAndEligibility.swift`, `Tests/ConsentAndEligibilityTests.swift` | Terms receipt (translation-only change re-prompts) and pre-scan eligibility gate |
| `Sources/MiniJson.swift`, `Sources/PackIndex.swift`, `Tests/FormatContractTests.swift` | Strict JSON and the `idx-flat-4` format contract (49 shared cases, result display names) |
| `Sources/PackLoader.swift`, `Tests/ManifestContractTests.swift` | Manifest V2 loader (CryptoKit Ed25519/SHA-256); 68 shared cases |
| `Sources/RecognitionSession.swift`, `Tests/PipelineGoldenTests.swift` | FrameView (RGB/BGR, strides) + session; 12 shared pipeline queries |
| `Sources/Recognition.swift`, `DacDhash.swift`, `DacExact.swift` and their golden tests | Verification/decision, DAC-DHASH-v1, DAC-CROP-v1/DAC-QUAL-v1 |
| `Sources/ScreenCaptureAdapter.swift` | ScreenCaptureKit adapter skeleton behind `canImport(ScreenCaptureKit) && os(iOS)`; excluded from the macOS build; symbol signatures UNVERIFIED |

## Capture paths to investigate separately (D11: no blanket minimum)

1. **ScreenCaptureKit on iOS** (S05 to S11, V09, V10). The investigated sample lists iOS/Xcode 27.
   Pin each symbol from installed headers (CAP-I03): `SCContentSharingPicker`, `SCStream`,
   `SCStreamOutput`, `SCStreamDelegate`. The documented display and current-app paths do **not**
   establish arbitrary third-party-app isolation, so consumer scope stays BLOCKED (D01).
2. **ReplayKit broadcast extension** (S13, V11, V12). Research candidate only. Verify
   introduced, deprecated and obsoleted attributes separately. Deprecation is not removal,
   and neither is a store rejection.

## First Mac session checklist (P02-T01/T02, DATA-L00 Part A)

1. Record Xcode, SDK, device OS build and provisioning profile.
2. Run `swift test` in `DetectAClipLab/` on that Mac as well and record it next to the CI result in `docs/TEST_EVIDENCE.md`.
3. Build a minimal visual-only app target with capture disabled: no camera, microphone,
   Photos or file output, and no analytics or crash SDK. ATS is **not** an egress firewall (Q01),
   so DATA-L00 Part A needs independently verified network isolation.
4. Request the finite background task early and end it on completion or expiry (V16).
   No audio keepalive.
