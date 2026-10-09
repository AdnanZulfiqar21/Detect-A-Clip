"""P04-T06b query/gallery leakage audit on fixtures-v3.1 (no rendering of sealed queries).

Checks identity and seed separation only; it does not render FINAL queries.
"""
from collections import Counter

from dac_l0.synth.fixtures import FAMILIES, build_family, make_queries


def _seeds(F):
    s = {w.seed for w in F.plain} | {w.seed for w in F.absent} | {n.seed for n in F.natural}
    for e in F.episodes:
        s |= {seg[0].seed for seg in e.segments} | {e.seed}
    for w in F.stock_pair:
        s |= {seg[0].seed for seg in w.segments} | {w.seed}
    return s


def test_family_seeds_and_ids_are_disjoint():
    fams = {f: build_family(f) for f in FAMILIES}
    seeds = {f: _seeds(F) for f, F in fams.items()}
    ids = {f: {w.work_id for w in F.gallery_works} | {w.work_id for w in F.absent} for f, F in fams.items()}
    for a in FAMILIES:
        for b in FAMILIES:
            if a < b:
                assert not seeds[a] & seeds[b], (a, b)
                assert not ids[a] & ids[b], (a, b)


def test_absent_works_never_indexed_and_never_share_a_seed_with_gallery():
    for f in FAMILIES:
        F = build_family(f)
        gallery_ids = {e.work.work_id for e in F.gallery_editions()}
        gallery_seeds = _seeds(F) - {w.seed for w in F.absent} - {n.seed for n in F.natural}
        for w in F.absent:
            assert w.work_id not in gallery_ids
            assert w.seed not in gallery_seeds


def test_query_truth_labels_refer_only_to_own_family_gallery():
    for f in FAMILIES:
        F = build_family(f)
        allowed = {w.work_id for w in F.gallery_works} | {e.series_id for e in F.episodes}
        for q in make_queries(f):
            if q.true_work and q.kind not in ("MONTAGE",):
                assert q.true_work in allowed, (f, q.label)
            for a in q.acceptable:
                if a.startswith("SW"):
                    assert a in allowed, (f, q.label)


def _identity(q):
    r = q.render
    owner = getattr(r, "__self__", None)
    key = getattr(owner, "channel_key", None)
    return (q.kind, q.label, key)


def test_every_query_has_a_unique_identity():
    """Labels round start times to 0.1 s and may collide; the full identity must not."""
    for f in FAMILIES:
        c = Counter(_identity(q) for q in make_queries(f))
        dup = [k for k, v in c.items() if v > 1]
        assert not dup, (f, dup[:3])


def near_duplicates(f, window_s=2.0):
    """Same work, same transform, starts closer than window_s: clustered, not independent.
    Known limitation of fixtures-v3.1 (no minimum start separation); fix planned for v4."""
    clips = []
    for q in make_queries(f):
        owner = getattr(q.render, "__self__", None)
        if owner is not None and hasattr(owner, "start_s"):
            clips.append((q.kind, owner.edition.asset_id, owner.transform, owner.start_s))
    n = 0
    for i, a in enumerate(clips):
        for b in clips[i + 1:]:
            if a[:3] == b[:3] and abs(a[3] - b[3]) < window_s:
                n += 1
    return n


def test_near_duplicate_counts_are_recorded_not_hidden():
    counts = {f: near_duplicates(f) for f in FAMILIES}
    assert all(v >= 0 for v in counts.values())
    print("near-duplicate query pairs (<2 s, same edition+transform):", counts)


def test_labels_are_unique_in_v4_families():
    for f in FAMILIES:
        c = Counter((q.kind, q.label) for q in make_queries(f))
        dup = [k for k, v in c.items() if v > 1]
        assert not dup, (f, dup[:3])


def test_v4_has_no_near_duplicate_queries():
    for f in FAMILIES:
        assert near_duplicates(f) == 0, f
