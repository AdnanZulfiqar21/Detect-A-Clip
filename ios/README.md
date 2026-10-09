# iPhone track (P02): source and specification only

**Status: BLOCKED for compile, archive and every device test (B-02).** This Windows host has
no macOS, Xcode, iOS SDK, provisioning or iPhone. Nothing in this folder has been compiled.
No iOS build is claimed to pass.

## What is here

| File | Purpose | Status |
|---|---|---|
| `DetectAClipLab/Package.swift` | Swift package for the platform-independent coordinator and its tests (`swift test` on a Mac) | IMPLEMENTED_NOT_VERIFIED |
| `DetectAClipLab/Sources/ScanCoordinator.swift` | Port of `l0/dac_l0/coordinator.py` (F03 event table) | IMPLEMENTED_NOT_VERIFIED |
| `DetectAClipLab/Tests/ScanCoordinatorTests.swift` | LIFE-01/03 orderings, fail-closed stop attribution, background expiry | NOT_RUN |
| `DetectAClipLab/Sources/FrameSelector.swift` | ≤2 fps, ≤3 owned frames, monotonic timestamps | IMPLEMENTED_NOT_VERIFIED |
| `DetectAClipLab/Sources/CaptureLifecycle.swift` | Port of the JVM-tested Kotlin lifecycle + early background-task request and expiry cancel | IMPLEMENTED_NOT_VERIFIED |
| `DetectAClipLab/Sources/ConsentAndEligibility.swift` | Terms receipt (translation-only change re-prompts) and pre-scan eligibility gate | IMPLEMENTED_NOT_VERIFIED |
| `DetectAClipLab/Sources/ScreenCaptureAdapter.swift` | ScreenCaptureKit adapter skeleton behind `canImport(ScreenCaptureKit) && os(iOS)`; symbol signatures UNVERIFIED | NOT COMPILED |
| `DetectAClipLab/Tests/CaptureLifecycleTests.swift`, `ConsentAndEligibilityTests.swift` | Lifecycle races, background expiry, consent, eligibility | NOT_RUN |

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
2. Run `swift test` in `DetectAClipLab/` and record the result in `docs/TEST_EVIDENCE.md`.
3. Build a minimal visual-only app target with capture disabled: no camera, microphone,
   Photos or file output, and no analytics or crash SDK. ATS is **not** an egress firewall (Q01),
   so DATA-L00 Part A needs independently verified network isolation.
4. Request the finite background task early and end it on completion or expiry (V16).
   No audio keepalive.
