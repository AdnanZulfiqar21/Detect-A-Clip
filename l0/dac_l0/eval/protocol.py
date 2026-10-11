"""Preregistered evaluation protocol primitives (F05 evaluation protocol, CQ-07).

- Wilson score intervals with z = 1.959963984540054 for *independent* examples.
- Per-work clustered percentile bootstrap, reported separately and labelled EXPLORATORY.
- Explicit zero/small-event handling: a zero-error result does not establish a rare-event
  upper bound at small n; the report says INCONCLUSIVE for that bound.
- Frozen split families with a manifest hash so queries cannot tune the gallery.

Nothing here converts an L0 synthetic run into release evidence (G04 purpose LAB only).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np

Z95 = 1.959963984540054


def wilson_interval(k: int, n: int, z: float = Z95) -> Tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    if not (0 <= k <= n):
        raise ValueError("k out of range")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def cluster_bootstrap_interval(
    successes_by_cluster: Dict[str, Tuple[int, int]], n_boot: int = 2000, seed: int = 0, alpha: float = 0.05
) -> Tuple[float, float, int]:
    """Percentile bootstrap over clusters (works). successes_by_cluster: id → (k, n).
    Returns (lo, hi, n_clusters). EXPLORATORY: a percentile bootstrap over a handful of
    clusters is a planning aid, not a defensible release bound."""
    ids = list(successes_by_cluster)
    m = len(ids)
    if m == 0:
        return (0.0, 1.0, 0)
    ks = np.array([successes_by_cluster[i][0] for i in ids], dtype=np.float64)
    ns = np.array([successes_by_cluster[i][1] for i in ids], dtype=np.float64)
    rng = np.random.default_rng(seed)
    rates = []
    for _ in range(n_boot):
        idx = rng.integers(0, m, size=m)
        tot_n = ns[idx].sum()
        rates.append(ks[idx].sum() / tot_n if tot_n > 0 else 0.0)
    lo, hi = np.quantile(rates, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi), m)


@dataclass
class Metric:
    name: str
    k: int
    n: int
    denominator_definition: str
    wilson_lo: float = 0.0
    wilson_hi: float = 0.0
    cluster_lo: float = 0.0
    cluster_hi: float = 0.0
    n_clusters: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.k / self.n if self.n else float("nan")

    def finalize(self, by_cluster: Dict[str, Tuple[int, int]]) -> "Metric":
        self.wilson_lo, self.wilson_hi = wilson_interval(self.k, self.n)
        self.cluster_lo, self.cluster_hi, self.n_clusters = cluster_bootstrap_interval(by_cluster)
        if self.n < 100:
            self.notes.append("n<100: exploratory only")
        if self.k == 0 or self.k == self.n:
            self.notes.append("zero/all events: rare-event bound INCONCLUSIVE at this n (rule-of-three ≈ %.3f)" % (3.0 / max(1, self.n)))
        if self.n_clusters and self.n_clusters < 30:
            self.notes.append(f"{self.n_clusters} clusters: cluster bootstrap is a planning aid only")
        return self

    def to_dict(self) -> Dict:
        return {
            "name": self.name, "k": self.k, "n": self.n, "rate": self.rate,
            "wilson95": [self.wilson_lo, self.wilson_hi], "cluster_boot95": [self.cluster_lo, self.cluster_hi],
            "n_clusters": self.n_clusters, "denominator": self.denominator_definition, "notes": self.notes,
        }


@dataclass(frozen=True)
class SplitFamilies:
    """Frozen split of synthetic works into DEV / CALIBRATION / FINAL families.
    Clean, edited and unknown denominators are kept distinct downstream."""

    dev_works: Tuple[str, ...]
    calibration_works: Tuple[str, ...]
    final_works: Tuple[str, ...]
    absent_works: Tuple[str, ...]
    seed: int

    def manifest_hash(self) -> str:
        body = json.dumps(self.__dict__, sort_keys=True).encode()
        return hashlib.sha256(body).hexdigest()


def freeze_splits(gallery_ids: Sequence[str], absent_ids: Sequence[str], seed: int = 42) -> SplitFamilies:
    rng = np.random.default_rng(seed)
    ids = list(gallery_ids)
    perm = [ids[i] for i in rng.permutation(len(ids))]
    n = len(perm)
    a, b = int(0.5 * n), int(0.75 * n)
    return SplitFamilies(tuple(sorted(perm[:a])), tuple(sorted(perm[a:b])), tuple(sorted(perm[b:])), tuple(absent_ids), seed)


PROTOCOL_TEXT = """\
L0 EXPLORATORY PROTOCOL (preregistered before outcomes; purpose LAB)
- Denominators: CLEAN = untransformed 8 s clips of indexed editions; EDITED = the same clip
  family with one query transform; ABSENT = clips of never-indexed works and natural scenes;
  UNUSABLE = blank/static/synthetic UI feeds. Never merged.
- Success (CLEAN/EDITED top-1): result names the true work in VERIFIED_MATCH or POSSIBLE_MATCH.
  Verified-only accuracy is reported separately. Abstentions count as failures.
- False verified (ABSENT): VERIFIED_MATCH on an absent-work clip. POSSIBLE_MATCH on absent
  is reported separately as a weak false alarm.
- Intervals: Wilson 95 % for independent examples; per-work cluster percentile bootstrap
  reported separately. Several clips per work ⇒ examples are clustered; the Wilson figure is
  an independence approximation, not a clustered bound.
- Zero/small events: no rare-event upper bound is claimed below n=1,000 absent queries.
- These runs are synthetic L0 dry runs and cannot satisfy the F05 release counts
  (≥1,000/≥1,000/≥1,000 over ≥200/≥200/≥300 works) or any D05 release threshold.
"""
