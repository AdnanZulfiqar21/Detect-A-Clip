# RESUME_STATE — Detect A Clip

Updated at checkpoints. On continuation: verify live git state first, then resume here.

- **Updated:** 2026-10-09 (session 1)
- **Branch / commits:** `impl/l0-desktop` at the "Record LAB evidence" commit on top of `9ba8c6d`; `main` at `bbdbe06` (baseline). **Not pushed** (awaiting owner confirmation to publish to the public repo).
- **Uncommitted work:** none expected after the checkpoint commit.
- **Local toolchain (git-ignored `tools/`):** Temurin JDK 17.0.20.1, Gradle 8.14.3, Android cmdline-tools 22.0. No SDK platform/build-tools (B-09). Run sdkmanager via `java -cp "android-sdk/cmdline-tools/latest/lib/*" com.android.sdklib.tool.sdkmanager.SdkManagerCli`; the `.bat` breaks on the space in the path.
- **Done:** P00-T01, P00-T09 (TRACE-01), P03-T03, P03-T04, P04-T02 (LAB); harness LIFE-01/02/03, SEC-02, SEC-01 basic, AI-01/AI-07 LAB.
- **Open findings:** OF-01 HASH64 POSSIBLE_MATCH on 4/66 absent clips (fix only via CALIBRATION family, P04-T05).
- **Next eligible steps:** (1) P04-T05 calibration on CALIBRATION works only, then re-run LAB; (2) add montage/recap/shared-intro queries (P04-T03, AI-03/AI-05); (3) compare 1 s / 5 s sampling and a 528 B descriptor row (P04-T02c, IDX-01); (4) THREAT_MODEL + CTRL-G00 checklist + DPIA screening docs (P00-T06); (5) once B-09 is cleared: Android Gradle wrapper, compile, run JVM tests, merged-manifest INTERNET check.
- **Needs owner input:** B-09 SDK licence acceptance; permission to push to the public GitHub repo; B-01/B-02 devices.
- **Last commands/results:** `python -m pytest` (l0) → 81 passed; LAB run 9 m 36 s → `l0/evidence/lab/lab_report_20261009T135848Z.md`.
