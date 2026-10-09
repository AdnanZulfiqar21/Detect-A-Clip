# RESUME_STATE — Detect A Clip

On continuation: verify live git state (`git status`, `git log -1`, `git ls-remote origin`)
first, then resume here.

- **Updated:** 2026-10-09 (session 2 checkpoint)
- **Branches:** `main` = `bbdbe06` (baseline, pushed). Work on `impl/l0-desktop` (pushed; see
  `git log -1` for the tip). Draft PR: https://github.com/AdnanZulfiqar21/Detect-A-Clip/pull/1.
- **Uncommitted work:** none expected after the checkpoint commit.
- **Local toolchain (git-ignored `tools/`):** Temurin JDK 17.0.20.1, kotlinc 2.4.21, JUnit 4.13.2 +
  Hamcrest 1.3 (SHA-1 verified), Gradle 8.14.3, Android cmdline-tools 22.0 with **no SDK packages**.
  The Android SDK licence is **not accepted** (B-09); do not run `sdkmanager --licenses`.
- **Verified this session:**
  - `cd l0 && python -m pytest -o addopts=""`: 123 passed.
  - `bash android/run-jvm-tests.sh`: OK (29 tests), pure-Kotlin files only, incl. bit-exact
    recognition (400 golden cases) and DAC-DHASH-v1 (42 golden frames) against Python.
  - Sealed FINAL LAB run (fixtures-v3.1, frozen calibration): wrong-title VERIFIED 0 for all four
    descriptors; THUMB32 1 FALSE_POSSIBLE. FINAL is now **seen**.
- **Index format:** idx-flat-3 (display names) was introduced *after* the FINAL run, which used
  idx-flat-2. Recognition logic is unchanged; reruns rebuild caches.
- **Open findings:** THUMB32 FALSE_POSSIBLE limitation; fixtures-v3.1 near-duplicate queries and
  small families (EVAL_PROTOCOL §7); UI_LIKE heuristic false positives on synthetic scenes
  (conservative: causes abstention only).
- **Next eligible steps (no external input needed):**
  1. fixtures-v4 with minimum start separation, unique labels and larger CALIBRATION/FINAL families,
     only if a method change needs a new sealed evaluation.
  2. Done this session: Kotlin/Swift ports of verification + decision and the DAC-DHASH-v1
     descriptor with golden vectors. Remaining device-independent step: a Kotlin flat retriever
     over a DAC-DHASH-v1 pack plus an end-to-end JVM test, then (with a method change) a new
     calibration and sealed family for DAC-DHASH-v1.
- **Needs owner input:** see docs/BLOCKERS.md (B-01…B-09).
