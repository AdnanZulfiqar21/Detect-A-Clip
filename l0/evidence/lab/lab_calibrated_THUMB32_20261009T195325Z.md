# L0 LAB report `calibrated_THUMB32` — 2026-10-09T19:53:25.017489+00:00

**Purpose:** LAB. Synthetic L0 exploratory evidence only. Not device, rights, coverage or release evidence.

Host Windows 11 AMD64 python 3.13.15 · commit `09b83a2+dirty` · synth-gen-3 / prep-640x360-gray-uniformcrop-3 / idx-flat-2
Fixture manifest `c246a60a6cf43b6d` · thresholds `89b29a0e18dcbfcc` (CALIBRATED_L0_SYNTHETIC) · calibration file: C:\Projects\Detect A Clip\l0\evidence\calibration\calibration_THUMB32.json

## Safety totals and outcome counts

| Descriptor | Family | wrong title VERIFIED | wrong title POSSIBLE | recognition p50 ms (desktop) | p90 ms |
|---|---|---:|---:|---:|---:|
| THUMB32 | DEV | 0 | 1 | 1325 | 2597 |
| THUMB32 | CALIBRATION | 0 | 0 | 1335 | 2800 |

### THUMB32 · DEV

Index: 4100 vectors, 208,056 B, 91,342 B per reference hour, 58 titles.

| Kind | Outcomes |
|---|---|
| ABSENT | ABSTAIN=65, FALSE_POSSIBLE=1 |
| CLEAN | ABSTAIN=1, CORRECT_POSSIBLE=4, CORRECT_VERIFIED=115 |
| EDITED | ABSTAIN=45, CORRECT_POSSIBLE=7, CORRECT_VERIFIED=68 |
| MONTAGE | CORRECT_SEGMENTS=5, PARTIAL=1 |
| OVERLAY | ABSTAIN=3 |
| SERIES_INTRO | CORRECT_SERIES_LEVEL=4 |
| SERIES_RECAP | CORRECT_VERIFIED=4 |
| SERIES_UNIQUE | CORRECT_VERIFIED=4 |
| STOCK_SHARED | ABSTAIN=4 |
| TRAILER | CORRECT_POSSIBLE=4 |
| UNUSABLE | EXPECTED_STATE=9 |

| Metric | k/n | Wilson 95 % | cluster boot 95 % (clusters) |
|---|---:|---|---|
| ABSENT:correct_named | 0/66 | [0.000, 0.055] | [0.000, 0.000] (16) |
| ABSENT:wrong_title_possible | 1/66 | [0.003, 0.081] | [0.000, 0.049] (16) |
| ABSENT:wrong_title_verified | 0/66 | [0.000, 0.055] | [0.000, 0.000] (16) |
| CLEAN:correct_named | 119/120 | [0.954, 0.999] | [0.975, 1.000] (20) |
| CLEAN:wrong_title_possible | 0/120 | [0.000, 0.031] | [0.000, 0.000] (20) |
| CLEAN:wrong_title_verified | 0/120 | [0.000, 0.031] | [0.000, 0.000] (20) |
| EDITED:correct_named | 75/120 | [0.536, 0.706] | [0.583, 0.667] (20) |
| EDITED:wrong_title_possible | 0/120 | [0.000, 0.031] | [0.000, 0.000] (20) |
| EDITED:wrong_title_verified | 0/120 | [0.000, 0.031] | [0.000, 0.000] (20) |
| MONTAGE:correct_named | 5/6 | [0.436, 0.970] | [0.500, 1.000] (6) |
| MONTAGE:wrong_title_possible | 0/6 | [0.000, 0.390] | [0.000, 0.000] (6) |
| MONTAGE:wrong_title_verified | 0/6 | [0.000, 0.390] | [0.000, 0.000] (6) |
| OVERLAY:correct_named | 0/3 | [0.000, 0.561] | [0.000, 0.000] (1) |
| OVERLAY:wrong_title_possible | 0/3 | [0.000, 0.561] | [0.000, 0.000] (1) |
| OVERLAY:wrong_title_verified | 0/3 | [0.000, 0.561] | [0.000, 0.000] (1) |
| SERIES_INTRO:correct_named | 4/4 | [0.510, 1.000] | [1.000, 1.000] (4) |
| SERIES_INTRO:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_INTRO:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_RECAP:correct_named | 4/4 | [0.510, 1.000] | [1.000, 1.000] (4) |
| SERIES_RECAP:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_RECAP:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_UNIQUE:correct_named | 4/4 | [0.510, 1.000] | [1.000, 1.000] (4) |
| SERIES_UNIQUE:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_UNIQUE:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| STOCK_SHARED:correct_named | 0/4 | [0.000, 0.490] | [0.000, 0.000] (2) |
| STOCK_SHARED:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (2) |
| STOCK_SHARED:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (2) |
| TRAILER:correct_named | 4/4 | [0.510, 1.000] | [1.000, 1.000] (4) |
| TRAILER:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| TRAILER:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| UNUSABLE:correct_named | 0/9 | [0.000, 0.299] | [0.000, 0.000] (3) |
| UNUSABLE:wrong_title_possible | 0/9 | [0.000, 0.299] | [0.000, 0.000] (3) |
| UNUSABLE:wrong_title_verified | 0/9 | [0.000, 0.299] | [0.000, 0.000] (3) |

<details><summary>Errors (1)</summary>

- ABSENT SW904-E0_THEATRICAL@30.2:CROPPED → FALSE_POSSIBLE (POSSIBLE_MATCH SW018 None flags=['EDITION_AMBIGUOUS', 'WEAK_SUPPORT'])

</details>

### THUMB32 · CALIBRATION

Index: 4100 vectors, 208,056 B, 91,342 B per reference hour, 58 titles.

| Kind | Outcomes |
|---|---|
| ABSENT | ABSTAIN=66 |
| CLEAN | ABSTAIN=1, CORRECT_POSSIBLE=1, CORRECT_VERIFIED=58 |
| EDITED | ABSTAIN=20, CORRECT_POSSIBLE=4, CORRECT_VERIFIED=36 |
| MONTAGE | CORRECT_SEGMENTS=6 |
| OVERLAY | ABSTAIN=3 |
| SERIES_INTRO | CORRECT_SERIES_LEVEL=4 |
| SERIES_RECAP | CORRECT_VERIFIED=4 |
| SERIES_UNIQUE | CORRECT_VERIFIED=4 |
| STOCK_SHARED | ABSTAIN=4 |
| TRAILER | CORRECT_POSSIBLE=2, CORRECT_VERIFIED=2 |
| UNUSABLE | EXPECTED_STATE=9 |

| Metric | k/n | Wilson 95 % | cluster boot 95 % (clusters) |
|---|---:|---|---|
| ABSENT:correct_named | 0/66 | [0.000, 0.055] | [0.000, 0.000] (16) |
| ABSENT:wrong_title_possible | 0/66 | [0.000, 0.055] | [0.000, 0.000] (16) |
| ABSENT:wrong_title_verified | 0/66 | [0.000, 0.055] | [0.000, 0.000] (16) |
| CLEAN:correct_named | 59/60 | [0.911, 0.997] | [0.950, 1.000] (10) |
| CLEAN:wrong_title_possible | 0/60 | [0.000, 0.060] | [0.000, 0.000] (10) |
| CLEAN:wrong_title_verified | 0/60 | [0.000, 0.060] | [0.000, 0.000] (10) |
| EDITED:correct_named | 40/60 | [0.541, 0.773] | [0.583, 0.750] (10) |
| EDITED:wrong_title_possible | 0/60 | [0.000, 0.060] | [0.000, 0.000] (10) |
| EDITED:wrong_title_verified | 0/60 | [0.000, 0.060] | [0.000, 0.000] (10) |
| MONTAGE:correct_named | 6/6 | [0.610, 1.000] | [1.000, 1.000] (5) |
| MONTAGE:wrong_title_possible | 0/6 | [0.000, 0.390] | [0.000, 0.000] (5) |
| MONTAGE:wrong_title_verified | 0/6 | [0.000, 0.390] | [0.000, 0.000] (5) |
| OVERLAY:correct_named | 0/3 | [0.000, 0.561] | [0.000, 0.000] (1) |
| OVERLAY:wrong_title_possible | 0/3 | [0.000, 0.561] | [0.000, 0.000] (1) |
| OVERLAY:wrong_title_verified | 0/3 | [0.000, 0.561] | [0.000, 0.000] (1) |
| SERIES_INTRO:correct_named | 4/4 | [0.510, 1.000] | [1.000, 1.000] (4) |
| SERIES_INTRO:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_INTRO:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_RECAP:correct_named | 4/4 | [0.510, 1.000] | [1.000, 1.000] (4) |
| SERIES_RECAP:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_RECAP:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_UNIQUE:correct_named | 4/4 | [0.510, 1.000] | [1.000, 1.000] (4) |
| SERIES_UNIQUE:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| SERIES_UNIQUE:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (4) |
| STOCK_SHARED:correct_named | 0/4 | [0.000, 0.490] | [0.000, 0.000] (2) |
| STOCK_SHARED:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (2) |
| STOCK_SHARED:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (2) |
| TRAILER:correct_named | 4/4 | [0.510, 1.000] | [1.000, 1.000] (3) |
| TRAILER:wrong_title_possible | 0/4 | [0.000, 0.490] | [0.000, 0.000] (3) |
| TRAILER:wrong_title_verified | 0/4 | [0.000, 0.490] | [0.000, 0.000] (3) |
| UNUSABLE:correct_named | 0/9 | [0.000, 0.299] | [0.000, 0.000] (3) |
| UNUSABLE:wrong_title_possible | 0/9 | [0.000, 0.299] | [0.000, 0.000] (3) |
| UNUSABLE:wrong_title_verified | 0/9 | [0.000, 0.299] | [0.000, 0.000] (3) |

## Scoring rules

```
fixtures-v3 scoring rules (preregistered 2026-10-09 before any CALIBRATION/FINAL outcome)
Every query yields exactly one outcome category. "named" = candidate_work_id of a
VERIFIED or POSSIBLE result; for episodes candidate_work_id is the series ID and
candidate_episode_id the episode (None = series level).
- CLEAN / EDITED: CORRECT_VERIFIED, CORRECT_POSSIBLE, ABSTAIN, WRONG_VERIFIED, WRONG_POSSIBLE.
- SERIES_UNIQUE: CORRECT_VERIFIED / CORRECT_POSSIBLE (right series and right episode);
  SERIES_LEVEL (right series, no episode: granularity loss, not wrong); ABSTAIN;
  WRONG_EPISODE_VERIFIED / WRONG_EPISODE_POSSIBLE; WRONG_VERIFIED / WRONG_POSSIBLE (outside series).
- SERIES_INTRO (shared intro): CORRECT = series level or ABSTAIN; any named episode is
  UNSUPPORTED_SPECIFICITY_VERIFIED / _POSSIBLE; outside series is WRONG_*.
- SERIES_RECAP (previous episode's footage + 2 s own): CORRECT = series level, own episode,
  or ABSTAIN; another episode VERIFIED = WRONG_EPISODE_VERIFIED; POSSIBLE = WRONG_EPISODE_POSSIBLE.
- STOCK_SHARED (same stock scene in two works): CORRECT = ABSTAIN, or POSSIBLE naming either
  work; VERIFIED naming either work = OVERCONFIDENT_SHARED; outside the pair = WRONG_*.
- MONTAGE (two works): CORRECT_SEGMENTS = POSSIBLE whose segments name both works and nothing
  else; PARTIAL = names a subset; ABSTAIN; OVERCONFIDENT_VERIFIED = VERIFIED; WRONG_* = any
  named work or segment outside the pair.
- TRAILER (rapid cuts of one work): CORRECT_* names it; ABSTAIN; WRONG_* other work.
- ABSENT: ABSTAIN; FALSE_VERIFIED; FALSE_POSSIBLE (a wrong title shown as uncertain). Both
  are errors and are reported separately; FALSE_POSSIBLE is never merged into ABSTAIN.
- UNUSABLE: EXPECTED_STATE if the state is in the case's acceptable list, else UNEXPECTED_STATE
  (WRONG_* if a title is named).
- OVERLAY (overlay over the underlying video): CORRECT_* names the video's work; ABSTAIN;
  WRONG_* names another work.
Safety totals: WRONG_TITLE_VERIFIED = every *_VERIFIED error category; WRONG_TITLE_POSSIBLE =
every *_POSSIBLE error category (incl. FALSE_POSSIBLE).

```
