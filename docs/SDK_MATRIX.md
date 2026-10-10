# SDK_MATRIX (P00-T02, CAP-A03 / CAP-I03 groundwork)

Each symbol has three separate states: **documented** (official docs say so), **installed**
(present in a pinned SDK's headers/stubs on a build machine) and **measured** (observed on a
named device). Android symbols are installed and compiled as of 2026-10-10; nothing is measured on a device yet (B-01).
iOS "installed" facts come from the hosted macOS CI runner's headers (`ios/scripts/sdk_probe.sh`,
swift-core workflow, 2026-10-10): newest Xcode 26.6 (17F113), iOS SDK 26.5; nothing is measured (B-02).

| Track | Symbol / feature | Documented | Installed | Measured | Note |
|---|---|---|---|---|---|
| Android | `MediaProjectionManager.createScreenCaptureIntent(MediaProjectionConfig)` (API 34) | Yes (S03) | **YES** (compiled vs platform 37.0, 2026-10-10) | NO (B-01) | Used by `MainActivity` |
| Android | `MediaProjectionConfig.createConfigForUserChoice()` (API 34) | Yes (S03) | **YES** (javap + compile) | NO | Used by `MainActivity` |
| Android | `MediaProjectionConfig.Builder`, `setSourceEnabled(int, boolean)`, `setInitiallySelectedSource(int)`, `PROJECTION_SOURCE_DISPLAY/APP/APP_CONTENT`, `isSourceEnabled`, `getProjectionSources` (API 37) | Yes (S04, Q03) | **YES** (`javap` on platforms/android-37.0/android.jar; compiled behind `SDK_INT >= 37` in `app_only` mode) | Emulator only (Android 17 `CE2A.260420.019`): with DISPLAY disabled the picker **still offered and enabled "Share entire screen"** | Not enforced on the emulator; enforcement on devices is CAP-A03 (B-01) |
| Android | `MediaProjection.Callback.onStop/onCapturedContentResize/onCapturedContentVisibilityChanged`, `MediaProjection.stop()` | Yes (S01) | **YES** (javap + compile) | NO | Visibility/resize recorded only, never a privacy boundary |
| Android | `ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION` | Yes (V05) | **YES** (compile) | NO | Post-close FGS survival is CAP-A04 |
| Android | Android 15 QPR1 status chip and lock auto-stop | Yes (S01, V04) | n/a | NO | Lab handles lock via SCREEN_OFF and onStop |
| iOS | `SCContentSharingPicker`, `SCStream`, `SCStreamOutput`, `SCStreamDelegate` | Metadata lists iOS 27 (S06–S08, V09) | **NO**: `ScreenCaptureKit.framework` is absent from the iOS 26.5 SDK (Xcode 26.6); a Swift typecheck importing it fails | NO | Needs the iOS 27 SDK (Xcode 27), not on the hosted runner; adapter stays uncompiled. No product minimum inferred (D11) |
| iOS | `SCShareableContent`, `allowedPickerModes` | Metadata does not list iOS (S10, S11) | NO (framework absent in iOS 26.5 SDK) | NO | Do not use on iOS unless headers say otherwise |
| iOS | `RPSystemBroadcastPickerView`, `RPBroadcastSampleHandler` | Bounded range ending 27 (V11, V12) | **YES** in iOS 26.5 SDK: `API_AVAILABLE(ios(12.0))` and `API_AVAILABLE(ios(10.0), …)`; **no** `API_DEPRECATED` attribute in these headers | NO | Header deprecation must be re-read in the iOS 27 SDK; deprecation ≠ removal ≠ rejection. Not used by the app |
| iOS | `UIApplication.beginBackgroundTask(withName:expirationHandler:)`, `backgroundTimeRemaining` | Yes (V16) | **YES** (compiled in `ios/LabApp` for iOS 26.5, arm64 unsigned and simulator) | NO | Diagnostic remaining time only |

## Pinned toolchain on the authoring host (2026-10-09, updated 2026-10-10)

| Tool | Version | Source | Use |
|---|---|---|---|
| Temurin JDK | 17.0.20.1+1 | Adoptium API | Kotlin compile, future Gradle |
| Kotlin compiler | 2.4.21 | JetBrains GitHub release | Pure-Kotlin JVM tests |
| JUnit / Hamcrest | 4.13.2 / 1.3 | Maven Central (SHA-1 verified) | JVM tests |
| Gradle | 8.14.3 | services.gradle.org | Superseded by 9.8.1 (AGP 9 needs Gradle 9); unused |
| Android cmdline-tools | 22.0 | dl.google.com | platforms;android-37.0, build-tools;37.0.0, platform-tools installed 2026-10-10 after owner licence acceptance |
| Gradle | 9.8.1 | services.gradle.org (SHA-256 verified) | Android build |
| Android Gradle Plugin | 9.4.1 (built-in Kotlin, stdlib 2.4.10) | Google Maven | Android build |

Android build verified on 2026-10-10 with AGP 9.4.1 + Gradle 9.8.1 + compileSdk 37 (see TEST_EVIDENCE).

## Hosted macOS CI toolchain (GitHub `macos-latest`, 2026-10-10)

| Tool | Version | Use |
|---|---|---|
| macOS | 26.6.2 (25G83), arm64 | runner |
| Xcode (selected) | 26.6 (17F113); 26.0.1–26.5 also installed | Swift core, iOS app |
| Swift | 6.3.3 (Swift 5 language mode in the package and app) | `swift build`, `swift test` |
| iOS SDK | 26.5 (device and simulator) | core compile for iOS, LAB app, UI test |
| XcodeGen | Homebrew, version printed in the job log | generates `ios/LabApp` project |
