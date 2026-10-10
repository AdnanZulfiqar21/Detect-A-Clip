# SDK_MATRIX (P00-T02, CAP-A03 / CAP-I03 groundwork)

Each symbol has three separate states: **documented** (official docs say so), **installed**
(present in a pinned SDK's headers/stubs on a build machine) and **measured** (observed on a
named device). Android symbols are installed and compiled as of 2026-10-10; nothing is measured on a device yet (B-01); iOS is neither installed nor measured (B-02).

| Track | Symbol / feature | Documented | Installed | Measured | Note |
|---|---|---|---|---|---|
| Android | `MediaProjectionManager.createScreenCaptureIntent(MediaProjectionConfig)` (API 34) | Yes (S03) | **YES** (compiled vs platform 37.0, 2026-10-10) | NO (B-01) | Used by `MainActivity` |
| Android | `MediaProjectionConfig.createConfigForUserChoice()` (API 34) | Yes (S03) | **YES** (javap + compile) | NO | Used by `MainActivity` |
| Android | `MediaProjectionConfig.Builder`, `setSourceEnabled(int, boolean)`, `setInitiallySelectedSource(int)`, `PROJECTION_SOURCE_DISPLAY/APP/APP_CONTENT`, `isSourceEnabled`, `getProjectionSources` (API 37) | Yes (S04, Q03) | **YES** (`javap` on platforms/android-37.0/android.jar; compiled behind `SDK_INT >= 37` in `app_only` mode) | NO | Enforcement on devices is CAP-A03 |
| Android | `MediaProjection.Callback.onStop/onCapturedContentResize/onCapturedContentVisibilityChanged`, `MediaProjection.stop()` | Yes (S01) | **YES** (javap + compile) | NO | Visibility/resize recorded only, never a privacy boundary |
| Android | `ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION` | Yes (V05) | **YES** (compile) | NO | Post-close FGS survival is CAP-A04 |
| Android | Android 15 QPR1 status chip and lock auto-stop | Yes (S01, V04) | n/a | NO | Lab handles lock via SCREEN_OFF and onStop |
| iOS | `SCContentSharingPicker`, `SCStream`, `SCStreamOutput`, `SCStreamDelegate` | Metadata lists iOS 27 (S06–S08, V09) | NO (B-02) | NO | No product minimum inferred (D11) |
| iOS | `SCShareableContent`, `allowedPickerModes` | Metadata does not list iOS (S10, S11) | NO | NO | Do not use on iOS unless headers say otherwise |
| iOS | `RPSystemBroadcastPickerView`, `RPBroadcastSampleHandler` | Bounded range ending 27 (V11, V12) | NO | NO | Deprecation ≠ removal ≠ rejection |
| iOS | `UIApplication.beginBackgroundTask(withName:expirationHandler:)` | Yes (V16) | NO | NO | Diagnostic remaining time only |

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
