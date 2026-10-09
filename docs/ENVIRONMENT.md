# ENVIRONMENT — P00-T01 inventory (2026-10-09)

Scoped per track. Nothing here is guessed; each line is from a command run on the host.

## Desktop host (DESKTOP-L0 track)

| Item | Observed |
|---|---|
| OS | Microsoft Windows 11 Pro 10.0.26200, x64 |
| CPU / RAM | 14 logical processors · 15,862 MB |
| Disk | C: 476 GB total, 34 GB free (93 % used) |
| Python | 3.13.15 (MSC v.1944 64-bit), pip 26.2.1 |
| Python packages present | numpy 2.5.3 · opencv-python 5.0.0.93 · Pillow 12.3.0 |
| Python packages absent | pytest · scipy · imagehash (pytest to be installed as dev dependency) |
| Node | v22.23.2 · npm 10.9.8 |
| Git / GitHub | git 2.55.0.windows.3 · gh 2.101.0 authenticated as Adnan-Zulfiqar (https) |
| Remote | `AdnanZulfiqar21/Detect-A-Clip`: PUBLIC, isEmpty=true, no refs, no default branch yet |

## Android track

| Item | Observed |
|---|---|
| JDK / javac | absent (`java`, `javac` not on PATH; no `C:\Program Files\Java`, Adoptium or Microsoft JDK folders) |
| Android Studio / SDK | absent (`%LOCALAPPDATA%\Android`, `C:\Program Files\Android` missing; `ANDROID_HOME`/`ANDROID_SDK_ROOT` unset) |
| adb / Gradle | absent |
| Devices | none connected; none inventoried |
| API 37 `MediaProjectionConfig.Builder` | UNVERIFIED on host (documentary only, S04/Q03) |

## iPhone track

| Item | Observed |
|---|---|
| macOS / Xcode / iOS SDK | absent (Windows host) |
| Provisioning / Developer account | not inventoried; not available on this host |
| Devices | none |
| ScreenCaptureKit iOS 27 symbols / ReplayKit deprecation attributes | UNVERIFIED (documentary only, S05–S11, V11) |

## Consequence

Desktop L0 (P04-T01…T07 LAB scope) can start once the desktop-scoped G00 and G03-L0 exist;
it does not need either phone (F06). Both mobile tracks remain research with compile
status at best IMPLEMENTED_NOT_VERIFIED until the toolchain and a device exist.
