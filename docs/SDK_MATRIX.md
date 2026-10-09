# SDK_MATRIX (P00-T02, CAP-A03 / CAP-I03 groundwork)

Each symbol has three separate states: **documented** (official docs say so), **installed**
(present in a pinned SDK's headers/stubs on a build machine) and **measured** (observed on a
named device). Nothing below is installed or measured yet.

| Track | Symbol / feature | Documented | Installed | Measured | Note |
|---|---|---|---|---|---|
| Android | `MediaProjectionManager.createScreenCaptureIntent(MediaProjectionConfig)` (API 34) | Yes (S03) | NO (B-09) | NO (B-01) | Used by `MainActivity` |
| Android | `MediaProjectionConfig.createConfigForUserChoice()` (API 34) | Yes (S03) | NO | NO | Used by `MainActivity` |
| Android | `MediaProjectionConfig.Builder`, `setSourceEnabled(int, boolean)`, `PROJECTION_SOURCE_DISPLAY/APP/APP_CONTENT` (API 37) | Yes (S04, Q03) | NO | NO | Deliberately not compiled yet; see `android/CAP-A03_PLAN.md` |
| Android | `MediaProjection.Callback.onCapturedContentResize/VisibilityChanged` (API 34) | Yes (S01) | NO | NO | Recorded only, never a privacy boundary |
| Android | `ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION` | Yes (V05) | NO | NO | Post-close FGS survival is CAP-A04 |
| Android | Android 15 QPR1 status chip and lock auto-stop | Yes (S01, V04) | n/a | NO | Lab handles lock via SCREEN_OFF and onStop |
| iOS | `SCContentSharingPicker`, `SCStream`, `SCStreamOutput`, `SCStreamDelegate` | Metadata lists iOS 27 (S06–S08, V09) | NO (B-02) | NO | No product minimum inferred (D11) |
| iOS | `SCShareableContent`, `allowedPickerModes` | Metadata does not list iOS (S10, S11) | NO | NO | Do not use on iOS unless headers say otherwise |
| iOS | `RPSystemBroadcastPickerView`, `RPBroadcastSampleHandler` | Bounded range ending 27 (V11, V12) | NO | NO | Deprecation ≠ removal ≠ rejection |
| iOS | `UIApplication.beginBackgroundTask(withName:expirationHandler:)` | Yes (V16) | NO | NO | Diagnostic remaining time only |

## Pinned toolchain on the authoring host (2026-10-09)

| Tool | Version | Source | Use |
|---|---|---|---|
| Temurin JDK | 17.0.20.1+1 | Adoptium API | Kotlin compile, future Gradle |
| Kotlin compiler | 2.4.21 | JetBrains GitHub release | Pure-Kotlin JVM tests |
| JUnit / Hamcrest | 4.13.2 / 1.3 | Maven Central (SHA-1 verified) | JVM tests |
| Gradle | 8.14.3 | services.gradle.org | Not yet used (needs Android SDK) |
| Android cmdline-tools | 22.0 | dl.google.com | No packages installed (licence pending, B-09) |

The Android Gradle plugin and Kotlin plugin versions in `android/build.gradle.kts` are
proposed pins and unverified until the SDK is installed.
