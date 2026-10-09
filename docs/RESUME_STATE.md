# RESUME_STATE — Detect A Clip

On continuation: verify live git state (`git status`, `git log -1`, `git ls-remote origin`)
first, then resume here.

- **Updated:** 2026-10-10 (session 3 checkpoint)
- **Branches:** `main` = `bbdbe06` (baseline). Work on `impl/l0-desktop` (pushed; `git log -1`).
  Draft PR: https://github.com/AdnanZulfiqar21/Detect-A-Clip/pull/1.
- **Uncommitted work:** none expected after the checkpoint commit.
- **Local toolchain (git-ignored `tools/`):** Temurin JDK 17.0.20.1, kotlinc 2.4.21, JUnit 4.13.2 +
  Hamcrest 1.3, Gradle 8.14.3, Android cmdline-tools 22.0 with **no SDK packages**. Android SDK
  licence **not accepted** (B-09); never run `sdkmanager --licenses`.
- **Verified:** `cd l0 && python -m pytest -o addopts=""` → 127 passed; `bash android/run-jvm-tests.sh`
  → OK (34 tests, pure-Kotlin only).
- **Evaluation state:** fixtures-v4 is current. DEV, CAL4 and FINAL4 are all SEEN (FINAL4 run once
  on 2026-10-10). A further held-out evaluation needs fresh seeds (v5). v3.1 results are historical.
- **Device engine:** DACDHASH (DAC-CROP-v1 + DAC-QUAL-v1 + DAC-DHASH-v1) is the recommended device
  path (ED-18). Python, Kotlin (JVM-verified) and Swift (uncompiled) implement it; packs for devices
  should be built with `--family DACDHASH`.
- **Open findings:** DACDHASH partial montage segmentation (5/12 on FINAL4); POSSIBLE allowed under
  competition for DACDHASH; UI_LIKE has no exact-path counterpart; synthetic content is an upper
  bound on real-footage accuracy.
- **Next eligible steps:** none that avoid owner input or a deliberate new method cycle. Device
  experiments (P01/P02, P04-T08) need B-01/B-02/B-09.
- **Needs owner input:** see docs/BLOCKERS.md (B-01…B-09).
