"""LIFE-01 / LIFE-02 / LIFE-03 / SEC-02 / LIFE-04(default memory mode) harness tests.

These exercise the reference coordinator semantics on the desktop. They are harness
evidence only: device verification of the same orderings remains BLOCKED (B-01/B-02).
"""
import random

import pytest

from dac_l0.coordinator import AdapterContract, Budgets, Coordinator, StopCause
from dac_l0.schemas import (
    CaptureClosedReason,
    CoordinatorState,
    PersistenceMode,
    RecognitionResult,
    ResultState,
)


def _ids():
    n = [0]

    def f():
        n[0] += 1
        return f"scan{n[0]}"

    return f


def make(attributable=False):
    return Coordinator(Budgets(), AdapterContract(can_attribute_normal_close=attributable), _ids())


def match_builder(c: Coordinator):
    def build(gen, now):
        return RecognitionResult(
            scan_id=c.session.scan_id, cancellation_generation=gen, state=ResultState.VERIFIED_MATCH,
            candidate_work_id="SW001", candidate_edition_id=None, candidate_episode_id=None, segments=[],
            ambiguity_flags=[], generator_version="g", index_format_version="i", calibration_version="c",
            calibration_status="UNCALIBRATED", local_entitlement_recheck="PASS", created_at_monotonic_ms=now,
            expires_at_monotonic_ms=now + 15 * 60_000, validity_clock_basis="monotonic",
        )

    return build


def to_post_capture(c: Coordinator, t0=0):
    assert c.start(t0)
    assert c.permission_granted(t0 + 100)
    assert c.target_ready(t0 + 200)
    for i in range(16):
        assert c.frame(t0 + 300 + 500 * i)
    assert c.normal_close_requested(t0 + 8300)
    return c.generation


# ----------------------------------------------------------------------- happy path


def test_normal_scan_commits_exactly_one_result():
    c = make(attributable=True)
    gen = to_post_capture(c)
    c.capture_stopped(8350, StopCause.APP_REQUESTED_ACK)  # attributable ack: idempotent
    assert c.state == CoordinatorState.POST_CAPTURE
    assert c.worker_result(9000, gen, match_builder(c))
    assert c.state == CoordinatorState.COMMITTED
    assert c.audit.commits == 1
    assert not c.worker_result(9001, gen, match_builder(c))  # second commit rejected
    assert c.audit.commits == 1
    assert c.result.persistence_mode == PersistenceMode.MEMORY_ONLY


def test_start_never_reuses_generation_or_scan_id_and_clears_previous_result():
    c = make(attributable=True)
    gen1 = to_post_capture(c)
    c.worker_result(9000, gen1, match_builder(c))
    sid1 = c.session.scan_id
    assert c.result is not None
    assert c.start(20_000)
    assert c.result is None
    assert c.generation > gen1
    assert c.session.scan_id != sid1
    assert c.state == CoordinatorState.AWAITING_PERMISSION  # never resumes acquisition


# ------------------------------------------------------------------ LIFE-03 / CQ-02


def test_normal_close_flag_does_not_make_unattributable_stop_callback_safe():
    """Adapter cannot attribute the cause: our own normal-close flag must NOT be trusted."""
    c = make(attributable=False)
    gen = to_post_capture(c)
    c.capture_stopped(8350, StopCause.APP_REQUESTED_ACK)
    assert c.state == CoordinatorState.CANCELLED
    assert c.session.capture_closed_reason == CaptureClosedReason.AMBIGUOUS_FAIL_CLOSED
    assert not c.worker_result(9000, gen, match_builder(c))
    assert c.result.state == ResultState.CANCELLED


@pytest.mark.parametrize("cause", [StopCause.USER_STOP, StopCause.SYSTEM_STOP, StopCause.UNKNOWN])
def test_observed_or_unknown_stop_after_normal_close_cancels_even_when_attributable(cause):
    c = make(attributable=True)
    gen = to_post_capture(c)
    c.capture_stopped(8400, cause)
    assert c.state == CoordinatorState.CANCELLED
    assert not c.worker_result(9000, gen, match_builder(c))
    assert c.audit.commits == 0


@pytest.mark.parametrize("event", ["lock", "permission_revoked", "cancel", "unsafe_context", "entitlement_failed"])
def test_abort_after_capture_closed_but_before_commit_wins(event):
    """Lock-after-close must not silently become a normal completion (F-09 / CQ-02)."""
    c = make(attributable=True)
    gen = to_post_capture(c)
    getattr(c, event)(8500)
    assert c.state in (CoordinatorState.CANCELLED, CoordinatorState.FAILED)
    assert not c.worker_result(8600, gen, match_builder(c))
    assert c.result.state in (ResultState.CANCELLED, ResultState.PERMISSION_DENIED, ResultState.ERROR)
    assert c.result.candidate_work_id is None


def test_user_stop_within_100ms_either_side_of_close():
    for delta in range(-100, 101, 10):
        c = make(attributable=True)
        c.start(0)
        c.permission_granted(100)
        c.target_ready(200)
        close_t = 8300
        if delta < 0:
            c.capture_stopped(close_t + delta, StopCause.USER_STOP)
            assert not c.normal_close_requested(close_t)
        else:
            c.normal_close_requested(close_t)
            c.capture_stopped(close_t + delta, StopCause.USER_STOP)
        assert not c.worker_result(close_t + 500, c.generation, match_builder(c)), delta
        assert c.state == CoordinatorState.CANCELLED, delta


def test_abort_after_commit_does_not_retract_but_releases():
    c = make(attributable=True)
    gen = to_post_capture(c)
    c.worker_result(9000, gen, match_builder(c))
    c.lock(9100)
    assert c.state == CoordinatorState.COMMITTED
    assert c.result.state == ResultState.VERIFIED_MATCH
    assert not c.lease_active


def test_post_capture_deadline_respects_remaining_background_time():
    c = make(attributable=True)
    c.start(0)
    c.permission_granted(100)
    c.target_ready(200)
    c.normal_close_requested(8300, remaining_background_ms=2_000)
    assert c.session.deadline_post_capture_ms == 10_300
    gen = c.generation
    c.tick(10_301)
    assert c.state == CoordinatorState.FAILED
    assert not c.worker_result(10_400, gen, match_builder(c))


def test_post_capture_hard_cap_is_8s():
    c = make(attributable=True)
    gen = to_post_capture(c)
    assert c.session.deadline_post_capture_ms - 8300 == 8000
    assert not c.worker_result(8300 + 8001, gen, match_builder(c))
    assert c.state == CoordinatorState.FAILED


# ----------------------------------------------------------------- deadlines / F05


def test_late_permission_callback_after_timeout_cannot_start_capture():
    c = make()
    c.start(0)
    c.tick(60_001)
    assert c.state == CoordinatorState.FAILED
    assert not c.permission_granted(60_500)
    assert not c.frame(61_000)


def test_target_wait_timeout_and_frames_rejected_outside_window():
    c = make()
    c.start(0)
    c.permission_granted(100)
    assert not c.frame(150)  # not acquiring yet
    c.tick(30_101)
    assert c.state == CoordinatorState.FAILED
    assert c.result.state == ResultState.INSUFFICIENT_SIGNAL


def test_sampling_window_closes_normally_on_tick():
    c = make()
    c.start(0)
    c.permission_granted(100)
    c.target_ready(200)
    assert c.frame(12_200)
    c.tick(12_201)
    assert c.state == CoordinatorState.POST_CAPTURE
    assert not c.frame(12_300)


def test_permission_denied_yields_permission_denied_result():
    c = make()
    c.start(0)
    c.permission_denied(500)
    assert c.result.state == ResultState.PERMISSION_DENIED
    assert not c.lease_active


# ------------------------------------------------------------------ LIFE-02 / SEC-02


def test_double_start_rejected_single_lease():
    c = make()
    assert c.start(0)
    g = c.generation
    for t in range(1, 50):
        assert not c.start(t)
    assert c.generation == g
    assert c.lease_active


def test_rapid_restarts_and_interleaved_callbacks_1000():
    rng = random.Random(1234)
    c = make(attributable=True)
    for _ in range(1000):
        t = rng.randint(0, 10_000_000)
        ev = rng.choice(["start", "grant", "target", "frame", "close", "ack", "user", "lock", "cancel", "tick", "worker_old", "worker_cur"])
        before_gen = c.generation
        if ev == "start":
            c.start(t)
        elif ev == "grant":
            c.permission_granted(t)
        elif ev == "target":
            c.target_ready(t)
        elif ev == "frame":
            c.frame(t)
        elif ev == "close":
            c.normal_close_requested(t)
        elif ev == "ack":
            c.capture_stopped(t, StopCause.APP_REQUESTED_ACK)
        elif ev == "user":
            c.capture_stopped(t, StopCause.USER_STOP)
        elif ev == "lock":
            c.lock(t)
        elif ev == "cancel":
            c.cancel(t)
        elif ev == "tick":
            c.tick(t)
        elif ev == "worker_old" and c.session:
            assert not c.worker_result(t, c.generation - 1, match_builder(c))
        elif ev == "worker_cur" and c.session:
            c.worker_result(t, c.generation, match_builder(c))
        # invariants
        assert c.generation >= before_gen
        if c.state in (CoordinatorState.COMMITTED, CoordinatorState.CANCELLED, CoordinatorState.FAILED, CoordinatorState.IDLE):
            assert not c.lease_active
        if c.result is not None:
            assert c.result.cancellation_generation <= c.generation


# --------------------------------------------------------------------------- LIFE-01


def test_life01_1000_orderings_no_stale_publication():
    """Delay worker results past user/OS abort in 1,000 random orderings."""
    rng = random.Random(42)
    published_after_abort = 0
    for i in range(1000):
        c = make(attributable=rng.random() < 0.5)
        gen = to_post_capture(c, t0=0)
        abort_t = 8300 + rng.randint(0, 7000)
        worker_t = abort_t + rng.randint(1, 3000)
        abort = rng.choice(["user", "system", "unknown", "lock", "revoke", "cancel"])
        {
            "user": lambda: c.capture_stopped(abort_t, StopCause.USER_STOP),
            "system": lambda: c.capture_stopped(abort_t, StopCause.SYSTEM_STOP),
            "unknown": lambda: c.capture_stopped(abort_t, StopCause.UNKNOWN),
            "lock": lambda: c.lock(abort_t),
            "revoke": lambda: c.permission_revoked(abort_t),
            "cancel": lambda: c.cancel(abort_t),
        }[abort]()
        if c.worker_result(worker_t, gen, match_builder(c)):
            published_after_abort += 1
        assert c.result is None or c.result.candidate_work_id is None
    assert published_after_abort == 0


# --------------------------------------------------------- LIFE-04 default (memory only)


def test_process_death_loses_result_and_restores_nothing():
    c = make(attributable=True)
    gen = to_post_capture(c)
    c.worker_result(9000, gen, match_builder(c))
    c.process_death()
    assert c.result is None
    assert c.state == CoordinatorState.IDLE
    assert not c.lease_active
    assert c.session is None


def test_uncommitted_job_not_restored_after_process_death():
    c = make(attributable=True)
    to_post_capture(c)
    c.process_death()
    assert c.state == CoordinatorState.IDLE
    assert not c.worker_result(9000, 1, match_builder(c))


def test_result_on_return_expiry_and_clock_rollback_fail_closed():
    c = make(attributable=True)
    gen = to_post_capture(c)
    c.worker_result(9000, gen, match_builder(c))
    assert c.return_to_app(9000 + 60_000) is not None            # +1 min
    assert c.return_to_app(9000 + 16 * 60_000) is None           # +16 min → expired & discarded
    c2 = make(attributable=True)
    gen2 = to_post_capture(c2)
    c2.worker_result(9000, gen2, match_builder(c2))
    assert c2.return_to_app(8000) is None                        # clock went backwards
    c3 = make(attributable=True)
    gen3 = to_post_capture(c3)
    c3.worker_result(9000, gen3, match_builder(c3))
    assert c3.return_to_app(9500, clock_trustworthy=False) is None
    c4 = make(attributable=True)
    gen4 = to_post_capture(c4)
    c4.worker_result(9000, gen4, match_builder(c4))
    assert c4.return_to_app(9500, entitlement_ok=False) is None


def test_session_record_holds_no_projection_handle_or_token():
    c = make()
    c.start(0)
    fields = set(vars(c.session))
    for bad in ("token", "intent", "projection", "handle", "permission_data"):
        assert not any(bad in f for f in fields), f
