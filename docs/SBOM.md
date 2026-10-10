# SBOM — software bill of materials (P06-T05a, partial)

Recorded 2026-10-09 from installed package metadata on the authoring host. Licences are as
declared by each package; **no licence review by counsel has been done.** No model weights,
datasets or third-party media are used anywhere in the project.

## Desktop L0 harness (Python 3.13.15) — not shipped to users

| Package | Version | Declared licence | Role |
|---|---|---|---|
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | arrays |
| opencv-python | 5.0.0.93 | Apache-2.0 | image ops, synthetic rendering, JPEG for the capture channel |
| pillow | 12.3.0 | MIT-CMU | installed on host but removed from requirements (unused) |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Ed25519 dev signing |
| cffi / pycparser | 2.1.1 / 3.0 | MIT-0 / BSD-3-Clause | cryptography deps |
| pytest (+ iniconfig, pluggy, packaging, pygments, colorama) | 9.1.1 | MIT (deps MIT / Apache-2.0 OR BSD-2 / BSD-2) | tests only |

## Android LAB module

| Component | Version | Declared licence | Shipped? |
|---|---|---|---|
| Android framework APIs | compileSdk 37 (platform 37.0 rev 2) | Android SDK License Agreement (accepted by the owner 2026-10-10) | platform |
| Kotlin stdlib | 2.4.10 (AGP 9.4.1 built-in Kotlin) | Apache-2.0 | yes |
| Android Gradle Plugin | 9.4.1 | Apache-2.0 | build only |
| junit | 4.13.2 | EPL-1.0 | test only |
| hamcrest-core | 1.3 | BSD-3-Clause | test only |
| Analytics / crash / networking SDKs | none | — | — |

Merged manifest verified 2026-10-10: no network or audio permissions. The app has no runtime dependencies besides the Kotlin stdlib.

## iOS research package

Swift standard library and Apple frameworks only (Foundation; ScreenCaptureKit/CoreMedia
behind `canImport`; CryptoKit for Ed25519/SHA-256). No third-party packages. Compiled only by
the `swift-core` CI job on a macOS runner; no iOS app build (B-02).

## CI (not shipped)

GitHub Actions: actions/checkout, actions/setup-python, actions/setup-java (Temurin 17),
gradle/actions/setup-gradle (Gradle 9.8.1), actions/upload-artifact; PyPI numpy,
opencv-python-headless, cryptography, pytest; kotlinc 2.4.21 and JUnit 4.13.2/Hamcrest 1.3
fetched from GitHub releases and Maven Central at run time.

## Local toolchain (not shipped, not committed)

Temurin JDK 17.0.20.1+1 (GPLv2 with Classpath Exception), Kotlin compiler 2.4.21 (Apache-2.0),
Gradle 9.8.1 (Apache-2.0; 8.14.3 also present, unused), Android command-line tools 22.0 with
`platforms;android-37.0`, `build-tools;37.0.0`, `platform-tools` (Android SDK License, accepted by the owner 2026-10-10).
