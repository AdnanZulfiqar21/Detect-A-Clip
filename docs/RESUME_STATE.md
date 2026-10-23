# RESUME_STATE — Detect A Clip

Updated at checkpoints. On continuation: verify live git state first, then resume here.

- **Updated:** 2026-10-09 (session 1, bootstrap)
- **Branch / commit:** `main` — baseline being created; implementation branch `impl/l0-desktop` next
- **Uncommitted work:** README, .gitignore, docs/* (about to be committed)
- **Completed:** P00-T01 inventory
- **In progress:** bootstrap docs → P00-T07 synthetic asset generator
- **Pending next eligible steps (in order):** P00-T07 generator + rights manifest → P03-T01 schemas → P00-T08 protocol → P03-T03 builder → P03-T04 UNCALIBRATED manifest + SEC-01 basic → P04-T01/T02 quality + baselines → P04-T05 result enum/decision → coordinator harness (LIFE-01/03) → Android lab source prep → toolchain install attempt
- **Last commands/results:** `gh repo view` → isEmpty=true; toolchain inventory → no JDK/SDK
- **Open findings:** none
- **Blockers:** see docs/BLOCKERS.md B-01…B-08

## 2026-10-23 — iPhone lab build (session on Linux cloud host)

- **Branch:** `claude/hopeful-cerf-7qfyiz` (PR to `main`).
- **Added:** `ios/` (SwiftUI app, `DetectAClipCore` package with unit tests, XcodeGen spec), `.github/workflows/ios-build.yml` (macOS runner: `swift test`, simulator build, unsigned iPhone `.ipa` artifact).
- **Not run locally:** no Swift/Xcode on this host; first compile is the CI run.
- **Note:** `l0/` and `android/` listed in README do not exist in the repository yet.
- **Next:** record the CI result in TEST_EVIDENCE; physical iPhone run needs B-02.
