# EVAL_PROTOCOL — L0 synthetic evaluation (P00-T08, P04-T05/T06)

**Purpose LAB only.** No result here can satisfy F05 release counts, a D05 threshold or any
release gate. An independent evaluator (AI-06) is not available (B-06).

## 1. Fixture history and what each family may be used for

| Fixture | Families | Status | Use |
|---|---|---|---|
| synth-gen-1 | 20 works | Superseded before any run (ED-08) | none |
| synth-gen-2 LAB report 2026-10-09T13:58Z | 20 gallery works (seeds 1000–1019), 10 absent (5000–5009) | **SEEN.** Its outcomes guided OF-01 work and generator v3 | Historical record only |
| fixtures-v3 → **v3.1** | DEV = the gen-2 seeds above (+ series/stock 3100–3212, natural 7000–7005) | **SEEN; tuning allowed** | Development, radius rule, fixture repairs |
| v3.1 | CALIBRATION = fresh seeds 11000–11009, 13100–13212, 15000–15009, 17000–17005 | Calibration only | Threshold selection (`eval/calibrate.py`) |
| v3.1 | FINAL = fresh seeds 21000–21009, 23100–23212, 25000–25009, 27000–27005 | **SEALED** until one preregistered run | Single held-out LAB estimate |

Rules: DEV results are never presented as untouched evaluation. CALIBRATION results are
reported as calibration outcomes. FINAL is run once with the frozen calibration file; any
method change after that makes FINAL "seen" and a new sealed family (new seeds, v4) is
needed. v3.1 changed the fixtures after a DEV run and before any CALIBRATION or FINAL
outcome existed (commit history shows the order).

## 2. Generator audit (synth-gen-3)

| Finding | Risk | Action |
|---|---|---|
| Every frame carried "SYNTH SWnnn", a per-work text label | Label leakage: identity readable from pixels, matching artificially easy | Replaced with constant "SYNTHETIC" on every work |
| Title card showed the work number for 2 s | Same, for clips touching t<2 s | Constant "SYNTHETIC WORK" card |
| Queries were pixel-identical renders of reference frames | Overly easy CLEAN matching | Simulated capture channel on every query (scale 0.6–0.9, blur, JPEG q55–85, gamma 0.92–1.1) |
| gen-1 motion up to ~480 px/s and identical gradient backgrounds | Unrealistic, non-discriminative | Fixed in gen-2 (ED-08) |
| Content RNG keyed by rendering version | Rendering-only fixes silently re-randomised content | Content RNG key `synth-content-2` decoupled from the rendering version |
| Absent works drawn from the same generator | Intended hard negatives (same distribution) | Kept |
| Inserted EXTENDED scene is an inverted replay | Can produce chance clusters (seen on DEV) | Kept as a challenge; evidence policy must handle it |
| Remaining easy cues | Shapes are crisp, synthetic textures are distinctive, no real camera noise, no real cuts or grading | Documented limitation: synthetic L0 accuracy is an upper bound, not a forecast for real footage |

## 3. Query kinds (per family)

CLEAN and EDITED clips (all 13 transforms cycled, incl. CROPPED_20, CAPTIONED_HEAVY,
PIP_SCALED, SPEED_90/110, GAMMA_NOISE), SERIES_UNIQUE, SERIES_INTRO (8 s wholly inside a
10 s intro shared by all episodes), SERIES_RECAP (previous episode's footage), STOCK_SHARED
(8 s wholly inside 10 s stock footage used by two works), MONTAGE (4 s + 4 s from two works),
TRAILER (five 1.6 s cuts of one work), ABSENT (never-indexed works and natural scenes),
UNUSABLE (blank, static, synthetic private screens), OVERLAY (notification, keyboard, PiP
over playing video). Scoring rules are in `l0/dac_l0/eval/run_lab.py` (`SCORING_RULES`)
and are copied into every report.

## 4. Statistics

Wilson 95 % intervals assume independence and are shown for orientation only. Several
clips per work make examples clustered; the per-work cluster bootstrap is reported
separately and labelled a planning aid. With zero observed errors no rare-event bound is
claimed. Families have 10–20 works, far below F05 release counts.

## 5. Calibration rule (preregistered)

See the module docstring of `l0/dac_l0/eval/calibrate.py`: zero wrong-title VERIFIED on
CALIBRATION as a hard constraint, then fewest wrong-title POSSIBLE, then most correct named,
then most correct VERIFIED, then the most conservative setting. The frozen file records the
fixture-manifest hash, evidence digest, grid and outcomes, and has status
`CALIBRATED_L0_SYNTHETIC`, which release mode still rejects.

## 6. Presentation of uncertain results (OF-01)

POSSIBLE_MATCH is shown as "Possible match, not confirmed", never with a numeric confidence,
and is counted in every report. A wrong title shown as POSSIBLE is an error
(`WRONG_*_POSSIBLE` / `FALSE_POSSIBLE`); it is never merged into abstention and never
relabelled as a false VERIFIED.

## 7. Known limitations of fixtures-v3.1 (found after FINAL; not fixed in v3.1)

- **Near-duplicate queries.** Random clip starts have no minimum separation, so some pairs of
  queries come from the same edition and transform less than 2 s apart (DEV 5, CALIBRATION 6,
  FINAL 5 pairs; `tests/test_leakage_audit.py`). They are clustered evidence, not independent
  samples; the per-work cluster bootstrap already treats works as clusters. v4 will enforce
  a minimum separation and unique labels.
- **Small families.** 10 CALIBRATION works could not separate grid settings on safety: every
  setting met the zero-wrong-VERIFIED constraint. Tie-breaks, not evidence, chose among them.
- **Single FINAL run.** FINAL is now seen. Re-evaluation after any method change needs a new
  sealed family with fresh seeds.

## 8. fixtures-v4 (preregistered 2026-10-09, before any CAL4/FINAL4 outcome)

| Family | Seeds | Size | Status |
|---|---|---|---|
| DEV | v3.1 DEV (1000+, 3100+, 5000+, 7000+) | 20 works, 10 absent | SEEN, tuning allowed |
| CAL4 | 31000+, 33100+, 33200+, 35000+, 37000+ | 20 works, 20 absent, 10 natural, 418 queries | calibration only |
| FINAL4 | 41000+, 43100+, 43200+, 45000+, 47000+ | 20 works, 20 absent, 10 natural, 418 queries | SEALED; one run per descriptor with the frozen CAL4 calibration |

Changes from v3.1: separated clip starts (≥ 3 s within an edition; 0 near-duplicate pairs),
unique labels, 12 montages and 8 trailers per family. v3.1 CALIBRATION/FINAL are no longer in
the gallery. Descriptors evaluated: HASH64 (LAB reference) and DACDHASH (integer-exact device
path, ED-17). Scoring rules and the calibration selection rule are unchanged from v3.1.
Calibration files: `l0/evidence/calibration/v4/`.
