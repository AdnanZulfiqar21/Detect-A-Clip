# CTRL-G00 checklist and DATA-L00 Part A record (roadmap F06)

**Status: checklist prepared; no item is signed.** A witness and a named reviewer are
required (P00-T04). Desktop L0 and each mobile track are scoped separately.

## Desktop L0 track (no phone needed)

| # | Control | State on 2026-10-09 | Evidence |
|---|---|---|---|
| D1 | Only self-created synthetic assets; rights manifest present | Implemented | `l0/assets/ASSET_MANIFEST.json`, `RIGHTS_MANIFEST.json` (grant PENDING_REVIEW) |
| D2 | No network code, no analytics or crash SDK | Implemented | `l0/requirements.txt` (numpy, opencv, Pillow, cryptography, pytest) |
| D3 | No rendered media or packs committed | Implemented | `.gitignore`; history audit in REVIEW_LOG |
| D4 | Frozen protocol before outcomes | Implemented | `fixtures-v3.1` + scoring rules committed before CAL/FINAL runs |
| D5 | Named reviewer signs G00 (desktop) | **Open** | Needs P00-T04 |

## Android track — DATA-L00 Part A (no frames)

| # | Control | State | How to check |
|---|---|---|---|
| A1 | Lab build has no INTERNET (incl. merged dependencies) | Source done; **merged manifest not inspected** | `./gradlew :app:processDebugManifest` then read `build/intermediates/merged_manifests/...` (needs SDK, B-09) |
| A2 | Capture disabled in the Part A build | Source done | `dac.captureEnabled=false` in `android/gradle.properties`; `BuildConfig.CAPTURE_ENABLED` |
| A3 | No file output from capture code | Code review done | grep for `FileOutputStream`, `openFileOutput`, `MediaStore` in `android/` → none |
| A4 | Backups disabled | Source done | `allowBackup=false`, `no_backup.xml` |
| A5 | Coordinator Stop/timeout rehearsal without capture | JVM tests pass | `ScanCoordinatorTest`, `CaptureLifecycleTest` (17 tests) |
| A6 | Dedicated non-personal device and account | **Open** | B-01 |
| A7 | Isolated test network: cellular off, external egress blocked, IPv4/IPv6 deny rules verified with a synthetic canary | **Open** | Needs device + network setup |
| A8 | OS termination fallback identified (Task Manager on 13+) | Documented | roadmap Q02; live check in Part B |
| A9 | Witness signs Part A | **Open** | — |

Part B (first supervised capture) may start only after A1–A9 are signed and G00 (Android)
is recorded.

## iPhone track — DATA-L00 Part A

| # | Control | State |
|---|---|---|
| I1 | Minimal visual-only target, capture disabled, no camera/mic/Photos/file output | Not started (B-02) |
| I2 | Independent network isolation (ATS is not an egress control) | Not started |
| I3 | Background task requested early and ended on completion or expiry | Coordinator `backgroundTaskExpired` path written; untested |
| I4 | Witness signs Part A | Open |
