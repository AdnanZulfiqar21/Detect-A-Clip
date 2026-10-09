# REVIEW_LOG — Detect A Clip

Every entry is labelled honestly: **SELF (Claude Fable 5.1)** means the implementing AI
reviewed its own diff; **AI-SEPARATE** means a separate automated review pass; **HUMAN**
means a named person. No entry here is an independent human, legal, licensor or store review.

| Date | Scope (commit / files) | Reviewer type | Findings | Resolution |
|---|---|---|---|---|
| 2026-10-09 | Baseline: README, .gitignore, docs/ | SELF | `.gitignore` had an inline comment on the `tools/` rule (invalid gitignore syntax). | Fixed before commit. |
| 2026-10-09 | Toolchain setup (local, git-ignored `tools/`) | SELF | **Process finding (P0 consent):** an sdkmanager `--licenses` run was piped `yes`, which accepted the Android SDK licences without the owner's explicit chat confirmation. | Task stopped; `tools/android-sdk/licenses/`, `.temp/`, partial `platform-tools/` deleted; no SDK package was installed. Recorded as B-09. Downloads already made and disclosed to owner: Temurin JDK 17.0.20.1 zip (Adoptium API), Android cmdline-tools 15859902 zip (dl.google.com), Gradle 8.14.3 bin zip (services.gradle.org); pip installs `pytest`, `cryptography`. No further downloads or licence acceptance until owner confirms. |
| 2026-10-09 | Recognition chain pre-run distance study | SELF | Descriptors non-discriminative on synth-gen-1 (true-match distance > nearest other work); int16 overflow in L2 distance; THUMB radius 900 let absent works VERIFY; wrong edition asserted on 1-frame margin. | Fixture redesign (ED-08) before the preregistered run; int32 distances; DEV-only radii and ≥3-frame edition margin (ED-09). |
| 2026-10-09 | Android CaptureService | SELF | Notification Stop never called `MediaProjection.stop()`; nothing closed the projection at the end of the sampling window (tick loop lived only in the activity); no target-ready or post-capture commit path. | Service-owned tick loop, idempotent teardown that stops a live projection, bounded dummy post-capture work committing with its starting generation. Still NOT COMPILED. |
| 2026-10-09 | LAB report 20261009T135848Z | SELF | **OF-01 (open):** HASH64 named a wrong work as POSSIBLE_MATCH on 4/66 absent clips. | Not tuned on these final-family outcomes. To be addressed in P04-T05 using the CALIBRATION family only, then re-run. |
