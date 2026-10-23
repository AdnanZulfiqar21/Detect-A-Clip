# TEST_EVIDENCE — Detect A Clip

Each PASS row cites the exact command, date, commit, host/device and configuration.
Desktop runs are **LAB** evidence on synthetic assets; they are not device, rights or
release evidence. Tests without a row are planned, not run.

| Test ID | Scope | Status | Run (command · date · commit · config) | Result summary |
|---|---|---|---|---|
| TRACE-01 | Roadmap parse | NOT_RUN | | |
| SEC-01 (basic, L0) | Pack tamper rejection | NOT_RUN | | |
| IDX-01 (desktop baseline) | Bytes/hour, build time | NOT_RUN | | |
| AI-01 (LAB) | Synthetic clean top-1 | NOT_RUN | | |
| AI-02 (LAB) | Synthetic absent works | NOT_RUN | | |
| AI-03 (LAB) | Synthetic edited | NOT_RUN | | |
| AI-07 (LAB) | Result enum distinctness | NOT_RUN | | |
| LIFE-01 / LIFE-03 (harness) | Coordinator orderings | NOT_RUN | | |
| IOS-BUILD-01 (compile, CI) | `ios/` core tests + simulator + unsigned arm64 iPhone build | PASS (compile/unit only) | `iOS build` workflow run 39888122632 · 2026-10-23 · commit 231674f · GitHub macos-latest runner, macOS 26.6.2, Xcode 26.6 (17F113), Swift 6.3.3, iphoneos SDK 26.5, deployment target iOS 16.0 | `swift test`: 24 tests, 0 failures (RecognitionTests 10, ScanCoordinatorTests 14). Simulator and Release iphoneos builds `BUILD SUCCEEDED`. Unsigned IPA sha256 0f4e023b…dc010. No device, signing or capture evidence. |
