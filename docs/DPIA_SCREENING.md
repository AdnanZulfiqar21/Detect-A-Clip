# DPIA screening (P00-T06c) — engineering input only

**Status: DRAFT screening prepared by the implementing AI. This is not a DPIA, not legal
advice and not an approval.** PRIV-01 requires counsel and a privacy reviewer for the actual
entity, audience and regions (B-04). Legal approval is tracked separately from this draft.

## Screening questions

| Question | Engineering answer for the current design | Points to counsel |
|---|---|---|
| Is personal data processed? | Potentially yes. Screen frames can show personal content of the user or third parties (messages, notifications, faces, names) | Classification of incidental third-party content |
| Is it special-category or sensitive? | Possibly, incidentally (health, finance, private messages visible on screen) | Whether incidental exposure triggers special-category rules |
| Systematic monitoring? | No. Capture runs only per explicit Start, bounded to ≤45 s, never on launch, no background scanning | Confirm |
| Innovative technology? | On-device visual matching of screen content | Likely a DPIA trigger in some jurisdictions |
| Data leaves the device? | No screen-derived data in local Mode L (no network permission in the lab build; no telemetry) | Store privacy labels still need the full binary/SDK inventory (REL-01) |
| Retention | Frames and descriptors: only for the duration of one scan in memory. Result: memory only, ≤15 min, lost on process death (D08 default) | D08 persistence proposal unapproved |
| Children | Audience undecided (D04, S20). A consumer product likely to be accessed by children needs an age-appropriate design assessment | Required before any beta |
| Consent model | Per-scan native OS consent + in-app disclosure; Terms receipt planned (P05-T02) | Lawful basis per region |
| Third parties | None in L0. L1 adds licensors (rights, not personal data) | Contracts |
| Cross-border transfer | None in Mode L | — |

## Screening outcome (engineering view)

A full DPIA is **likely required** before any external beta, because the product processes
screen content that may incidentally include third-party personal data, and because the
public/private boundary inside a chosen app is not technically enforced (T-10). This is an
engineering flag for counsel, not a legal conclusion.
