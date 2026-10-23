# REVIEW_LOG — Detect A Clip

Every entry is labelled honestly: **SELF (Claude Fable 5.1)** means the implementing AI
reviewed its own diff; **AI-SEPARATE** means a separate automated review pass; **HUMAN**
means a named person. No entry here is an independent human, legal, licensor or store review.

| Date | Scope (commit / files) | Reviewer type | Findings | Resolution |
|---|---|---|---|---|
| 2026-10-09 | Baseline: README, .gitignore, docs/ | SELF | `.gitignore` had an inline comment on the `tools/` rule (invalid gitignore syntax). | Fixed before commit. |
| 2026-10-23 | `ios/`, `.github/workflows/ios-build.yml` | SELF | Consent sheet used the picker's current source instead of the one captured at Start; frame-delivery constant read from a MainActor static inside a detached task. | Source now read from `awaitingConsent(source)`; constant copied to a local before the task. |
