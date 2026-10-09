# DECISIONS — Detect A Clip

One authoritative decision log. Owner decisions D01–D11 are defined in the roadmap v4.2.1
(F01). This file records (a) their current status and (b) engineering decisions made under
the limited development authorization.

## Limited development authorization (recorded once)

**Date:** 2026-10-09. **Source:** `CLAUDE_DETECT_A_CLIP_BUILD_PROMPT.md` §2, issued by the
project owner (GitHub account Adnan-Zulfiqar / AdnanZulfiqar21).

The owner authorizes routine implementation in this project: source and test changes,
project configuration, small refactors, local builds, dependency setup, synthetic fixtures,
debugging, automated reviews, documentation, local commits and publication of reviewed
source/documentation to `https://github.com/AdnanZulfiqar21/Detect-A-Clip`.

This supersedes the roadmap's "review-only / no implementation authorized" wording **for
development work only**. It does **not**: declare the software implemented; turn D05
proposed thresholds into approved release criteria; approve any D01–D11 option; supply any
licence, device evidence, counsel opinion or store approval; authorize a real-user beta,
spending, binding third-party commitments or a consumer launch.

## Owner decisions D01–D11 (status as of 2026-10-09)

| ID | Status | Default applied in code |
|---|---|---|
| D01 | PROPOSAL_REQUIRES_OWNER_DECISION | Strict public-only consumer scope stays BLOCKED; synthetic lab only. |
| D02 | PROPOSAL_REQUIRES_OWNER_DECISION | Only demonstrably compatible offline rights; no immediate-revocation promise. |
| D03 | PROPOSAL_REQUIRES_OWNER_DECISION | No unilateral platform-scope reduction; both OS tracks remain research. |
| D04 | PROPOSAL_REQUIRES_OWNER_DECISION | No real-user beta. |
| D05 | PROPOSAL_REQUIRES_OWNER_DECISION | F05 numbers are *experiment budgets* labelled PROPOSED; never relaxed after outcomes. |
| D06 | PROPOSAL_REQUIRES_OWNER_DECISION | No pivot to deferred features. |
| D07 | PROPOSAL_REQUIRES_OWNER_DECISION | Restricted packs disabled; `region_assurance_method` must be an explicitly accepted method; online activation is not territory proof. |
| D08 | PROPOSAL_REQUIRES_OWNER_DECISION | `persistence_mode = MEMORY_ONLY`. No frames/embeddings/descriptors/scan counters persisted. |
| D09 | PROPOSAL_REQUIRES_OWNER_DECISION | Notifications optional. Consumer cells without demonstrated Stop/Cancel controls are BLOCKED. |
| D10 | PROPOSAL_REQUIRES_OWNER_DECISION | One synthetic L0 pack; total active installed index ≤ 250,000,000 B regardless of pack count. |
| D11 | PROPOSAL_REQUIRES_OWNER_DECISION | No blanket iOS 27 minimum; no permanent ReplayKit exclusion; per-path evidence. |

## Engineering decisions (ED-nn)

| ID | Date | Decision | Reason | Reversible? |
|---|---|---|---|---|
| ED-01 | 2026-10-09 | Git initialized in place on `main`; substantive work on branch `impl/l0-desktop`. Remote verified empty (`gh repo view`: isEmpty=true, no refs). | Prompt §3; folder was a plain directory with two documents. | Yes |
| ED-02 | 2026-10-09 | Desktop L0 track implemented in **Python 3.13** (numpy, OpenCV, Pillow already installed) under `l0/`. | F04 says start with hash/flat lookup and a tiny permitted corpus and that no backend is required; Python is the only installed toolchain that can run image processing today. The mobile product remains native Kotlin/Swift; Python is the research/evaluation harness and reference implementation, not the shipped engine. | Yes |
| ED-03 | 2026-10-09 | Synthetic L0 assets are **generated deterministically from seeds**; only the generator, seed manifest and SHA-256 hashes are committed. Rendered media stays in `l0/assets/generated/` (git-ignored). | Keeps binaries out of the public repo (prompt §3.5) while keeping provenance reproducible (P03-T03a). | Yes |
| ED-04 | 2026-10-09 | Contributor/asset rights for L0: all synthetic works are created by this project's own code with no third-party footage, no fonts beyond OpenCV's built-in Hershey fonts, no trademarks; grant recorded in `l0/assets/RIGHTS_MANIFEST.json` as `SELF_CREATED_SYNTHETIC` permitting ingest/query/derivative/local-distribution/display for development. | G03-L0 requires an operation grant covering every intended act. This is a self-grant for synthetic material and is **not** a licence for any real work. | Yes |
| ED-05 | 2026-10-09 | Development integrity manifest for L0 packs is signed with an **Ed25519 development key generated locally and marked DEVELOPMENT_ONLY**; private key is git-ignored, public key committed. Status field is `UNCALIBRATED` until P04-T05. | P03-T04c / G03-L0. A development key never becomes a release key. | Yes |
| ED-06 | 2026-10-09 | Android/iOS native source is prepared on this host even though it cannot be compiled here (no JDK/Android SDK/Xcode). Compile status is recorded as **IMPLEMENTED_NOT_VERIFIED** until a build runs. | Prompt §6: prepare source/project/test specifications and record exactly which compilation and physical tests were not possible. | Yes |
| ED-07 | 2026-10-09 | `pytest` is installed into the user Python site-packages as a dev dependency. No other new runtime dependency is added to L0 without a reason recorded here. | Needed to run the L0 test suite. | Yes |
| ED-08 | 2026-10-09 | Synthetic generator bumped `synth-gen-1` → `synth-gen-2`: object motion reduced from up to ~480 px/s to ≤ ~70 px/s, slow background pan ≤ ~30 px/s, per-scene seeded multi-octave texture instead of one gradient style for every work. Preprocessing bumped to `prep-640x360-gray-crop-2` (uniform black-bar crop on both references and queries). | A pre-run distance study (DEV works only, no LAB metrics yet recorded) showed that with gen-1 the true-match distance exceeded the nearest *other-work* distance: frames moved too fast for 2 s reference sampling, and all works shared near-identical gradient backgrounds. That made the fixture unrealistic, not the matcher wrong. The change happened before the preregistered LAB run; no outcome was observed and then relaxed. | Yes |
| ED-09 | 2026-10-09 | Development decision thresholds (candidate radii) set from the DEV split only (`freeze_splits` seed 42): just below the 5th percentile of nearest other-work distance (HASH64 10, THUMB32 120, THUMB144 300). Edition asserted only with a ≥3-frame margin over other editions; offset tolerance = half the reference interval + 250 ms. Mirror-invariant query search on. LAB reports also show metrics restricted to non-DEV works. | P04-T05 requires calibration on a calibration family distinct from final queries; these are UNCALIBRATED development values and cannot pass a release gate. | Yes |
