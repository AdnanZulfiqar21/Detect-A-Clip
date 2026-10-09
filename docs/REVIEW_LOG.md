# REVIEW_LOG — Detect A Clip

Every entry is labelled honestly: **SELF (Claude Fable 5.1)** means the implementing AI
reviewed its own diff; **AI-SEPARATE** means a separate automated review pass; **HUMAN**
means a named person. No entry here is an independent human, legal, licensor or store review.

| Date | Scope (commit / files) | Reviewer type | Findings | Resolution |
|---|---|---|---|---|
| 2026-10-09 | Baseline: README, .gitignore, docs/ | SELF | `.gitignore` had an inline comment on the `tools/` rule (invalid gitignore syntax). | Fixed before commit. |
