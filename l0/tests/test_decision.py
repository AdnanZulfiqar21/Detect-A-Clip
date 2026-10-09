"""Decision-policy unit tests on hand-built evidence (P04-T04/T05, AI-05, OF-01)."""
import numpy as np
import pytest

from dac_l0.decision import DecisionThresholds, FrameSummary, decide
from dac_l0.index.builder import IndexBundle, WorkEntry
from dac_l0.index.descriptors import DescriptorFamily
from dac_l0.schemas import ResultState
from dac_l0.verify import Hypothesis

TH = DecisionThresholds()


def bundle():
    works = [
        WorkEntry(0, "SW001", "t", ["E0_THEATRICAL"], [60.0]),
        WorkEntry(1, "SW002", "t", ["E0_THEATRICAL"], [60.0]),
        WorkEntry(2, "SW100", "t", ["E0_THEATRICAL"], [60.0], "S-X", "E01"),
        WorkEntry(3, "SW101", "t", ["E0_THEATRICAL"], [60.0], "S-X", "E02"),
    ]
    return IndexBundle(DescriptorFamily.HASH64, 2.0, np.zeros((0, 8), np.uint8), np.zeros((0, 16), np.uint8), works)


def H(work, support, start=0, end=None, dist=3.0, edition=0):
    end = end if end is not None else start + 500 * (support - 1)
    return Hypothesis(work, edition, 1000, support, dist, start, end)


def frames(q=16):
    return FrameSummary(offered=80, selected=16, qualified=q)


def run(hyps, q=16, th=TH):
    return decide("s", 1, hyps, frames(q), bundle(), 0, th)


def test_strong_unique_evidence_verifies_work_and_edition():
    r = run([H(0, 14)])
    assert r.state == ResultState.VERIFIED_MATCH
    assert (r.candidate_work_id, r.candidate_edition_id) == ("SW001", "E0_THEATRICAL")
    assert r.segments[0].reference_offset_ms == 1000


def test_of01_pattern_short_span_at_radius_edge_is_not_named():
    """Three to four correlated frames inside ~1.5 s at the radius edge (the 4/66 OF-01 cases)."""
    r = run([H(1, 4, start=2500, end=4000, dist=8.9)])
    assert r.candidate_work_id is None
    assert r.state == ResultState.NO_CONFIDENT_MATCH


def test_competing_works_block_verified():
    r = run([H(0, 12), H(1, 11)])
    assert r.state == ResultState.NO_CONFIDENT_MATCH
    assert "COMPETING_WORKS" in r.ambiguity_flags


def test_competing_works_may_be_possible_only_if_policy_allows():
    from dataclasses import replace

    r = run([H(0, 12), H(1, 11)], th=replace(TH, possible_on_competition=True))
    assert r.state == ResultState.POSSIBLE_MATCH and r.candidate_work_id == "SW001"


def test_shared_intro_across_episodes_gives_series_level_only():
    r = run([H(2, 14), H(3, 14)])
    assert r.state == ResultState.VERIFIED_MATCH
    assert r.candidate_work_id == "S-X"
    assert r.candidate_episode_id is None and r.candidate_edition_id is None
    assert r.segments[0].reference_offset_ms is None  # no time without unique evidence
    assert "EPISODE_AMBIGUOUS" in r.ambiguity_flags


def test_unique_episode_evidence_names_the_episode():
    r = run([H(3, 14), H(2, 4)])
    assert (r.candidate_work_id, r.candidate_episode_id) == ("S-X", "E02")


def test_montage_names_best_supported_segment_and_stays_possible():
    r = run([H(0, 5, start=0, end=3500, dist=4), H(1, 8, start=4000, end=7500, dist=3)])
    assert r.state == ResultState.POSSIBLE_MATCH
    assert r.candidate_work_id == "SW002"
    assert [s.work_id for s in r.segments] == ["SW001", "SW002"]
    assert "MULTI_TITLE_SEGMENTS" in r.ambiguity_flags


def test_weak_but_valid_evidence_is_possible_and_flagged():
    r = run([H(0, 5, start=0, end=2000, dist=4)])
    assert r.state == ResultState.POSSIBLE_MATCH
    assert "WEAK_SUPPORT" in r.ambiguity_flags


@pytest.mark.parametrize("q,expected", [(2, ResultState.INSUFFICIENT_SIGNAL), (16, ResultState.NO_CONFIDENT_MATCH)])
def test_no_evidence_states(q, expected):
    assert run([], q=q).state == expected


def test_entitlement_recheck_failure_is_error_without_title():
    r = decide("s", 1, [H(0, 14)], frames(), bundle(), 0, TH, entitlement_recheck="FAIL")
    assert r.state == ResultState.ERROR and r.candidate_work_id is None


def test_thresholds_digest_changes_with_any_field():
    from dataclasses import replace

    assert TH.digest() != replace(TH, verified_min_span_ms=TH.verified_min_span_ms + 1).digest()


def test_support_fraction_counts_frames_excluded_by_quality_checks():
    """Montage half excluded as UI-like: 8 of 16 selected frames support one work."""
    f = FrameSummary(offered=80, selected=16, qualified=8)
    from dataclasses import replace

    th = replace(TH, verified_min_support_fraction=0.6)
    r = decide("s", 1, [H(0, 8, start=4000, end=7500)], f, bundle(), 0, th)
    assert r.state != ResultState.VERIFIED_MATCH
