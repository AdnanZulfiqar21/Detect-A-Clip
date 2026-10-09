"""CAP-A01 selector criteria (harness), result-enum contract (AI-07), rights default deny."""
import pytest

from dac_l0.sampler import FrameSelector, SelectorError
from dac_l0.schemas import (
    PermittedAct,
    RecognitionResult,
    ResultState,
    RightsGrant,
    SchemaError,
    assert_no_forbidden_keys,
)
from dac_l0.synth.manifest import l0_rights_grant


def test_selector_enforces_spacing_rate_and_buffer_under_60fps_delivery():
    sel = FrameSelector()
    owned = []
    for i in range(8000 // 16 + 1):  # 8 s at ~60 fps, consumer stalls after 2 frames
        ts = i * 16
        if sel.offer(ts):
            owned.append(ts)
            if len(owned) > 2:  # simulate a consumer that releases late
                sel.release()
                owned.pop(0)
    st = sel.stats
    assert st.min_gap_ms() >= 500
    assert st.selected <= 8000 // 500 + 1
    assert st.selected >= 12  # CAP-A01: ≥12 selected in an 8 s window
    assert st.peak_buffer <= 3
    assert st.dropped_spacing > 0
    assert sel.owned_bytes_upper_bound() <= 2_764_800


def test_selector_buffer_full_drops_instead_of_queueing():
    sel = FrameSelector()
    for i in range(10):
        sel.offer(i * 600)  # never released
    assert sel.owned == 3
    assert sel.stats.dropped_buffer_full == 7


def test_selector_rejects_non_monotonic_and_closed_intake():
    sel = FrameSelector()
    assert sel.offer(1000)
    assert not sel.offer(900)
    assert not sel.offer(1000)
    assert sel.stats.rejected_non_monotonic == 2
    sel.release()
    sel.close()
    assert not sel.offer(5000)
    with pytest.raises(SelectorError):
        sel.release()


def _res(state, work=None, **kw):
    base = dict(scan_id="s", cancellation_generation=1, state=state, candidate_work_id=work, candidate_edition_id=None,
                candidate_episode_id=None, segments=[], ambiguity_flags=[], generator_version="g", index_format_version="i",
                calibration_version="c", calibration_status="UNCALIBRATED", local_entitlement_recheck="PASS",
                created_at_monotonic_ms=0, expires_at_monotonic_ms=1000, validity_clock_basis="monotonic")
    base.update(kw)
    return RecognitionResult(**base)


@pytest.mark.parametrize("state", [ResultState.OUTSIDE_CATALOGUE, ResultState.REMOTE_UNAVAILABLE])
def test_reserved_states_unconstructible(state):
    with pytest.raises(SchemaError):
        _res(state)


def test_non_match_states_cannot_name_a_title_and_matches_must():
    with pytest.raises(SchemaError):
        _res(ResultState.NO_CONFIDENT_MATCH, "SW001")
    with pytest.raises(SchemaError):
        _res(ResultState.CANCELLED, "SW001")
    with pytest.raises(SchemaError):
        _res(ResultState.VERIFIED_MATCH, None)
    with pytest.raises(SchemaError):
        _res(ResultState.NO_CONFIDENT_MATCH, expires_at_monotonic_ms=0)


def test_result_records_have_no_pixel_or_descriptor_fields():
    import dataclasses

    names = {f.name for f in dataclasses.fields(RecognitionResult)}
    assert_no_forbidden_keys({n: None for n in names})
    with pytest.raises(SchemaError):
        assert_no_forbidden_keys({"query_descriptor": b"x"})


def test_l0_grant_default_deny_and_no_training_or_stills():
    g = l0_rights_grant()
    assert g.permits(PermittedAct.TRANSIENT_QUERY, "PK")
    assert not g.permits(PermittedAct.TRAINING, "PK")
    assert not g.permits(PermittedAct.DISPLAY_STILL, "PK")
    r = RightsGrant("x", "l", "e", [PermittedAct.DECISION], ["GB"], "2026", None, "o", "r", "APPROVED")
    assert r.permits(PermittedAct.DECISION, "GB")
    assert not r.permits(PermittedAct.DECISION, "PK")          # unknown territory denies
    assert not r.permits(PermittedAct.DISPLAY_METADATA, "GB")  # unknown act denies
    r.approval_status = "REVOKED"
    assert not r.permits(PermittedAct.DECISION, "GB")
