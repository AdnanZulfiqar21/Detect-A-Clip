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
| Android framework APIs | compileSdk 37 (proposed) | Android SDK licence (**not accepted**, B-09) | platform |
| Kotlin stdlib | via Kotlin Gradle plugin 2.2.20 (proposed pin) | Apache-2.0 | yes |
| junit | 4.13.2 | EPL-1.0 | test only |
| hamcrest-core | 1.3 | BSD-3-Clause | test only |
| Analytics / crash / networking SDKs | none | — | — |

Merged-manifest and dependency-tree verification need a Gradle build (B-09).

## iOS research package

Swift standard library and Apple frameworks only (Foundation; ScreenCaptureKit/CoreMedia
behind `canImport`). No third-party packages. Not compiled (B-02).

## Local toolchain (not shipped, not committed)

Temurin JDK 17.0.20.1+1 (GPLv2 with Classpath Exception), Kotlin compiler 2.4.21 (Apache-2.0),
Gradle 8.14.3 (Apache-2.0), Android command-line tools 22.0 (no packages installed).
