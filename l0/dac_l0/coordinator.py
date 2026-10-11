"""Single-session, consent-aware scan coordinator (roadmap F03 coordinator event table).

Pure, deterministic, clock-injected state machine. It is the reference semantics that the
native Kotlin/Swift coordinators must reproduce and that the LIFE-01/02/03 and SEC-02
harnesses exercise.

Invariants (tested):
- One lease and one cancellation generation per scan; a new start never resumes acquisition.
- Any observed user/system abort, lock, revoke, in-app cancel, entitlement failure or
  deadline expiry *before commit* atomically invalidates the generation. Nothing
  uncommitted may publish later.
- A stop callback with unresolved cause fails closed unless the adapter contract proves
  the callback is the acknowledgment of our own normal-close request.
- A normal-close flag never overrides an observed abort.
- At most one result per scan, committed under the coordinator lock after rechecking
  generation, abort state, deadlines and local entitlement.
- Results are memory-only (D08 unapproved); process death loses them.
"""
from __future__ import annotations

import enum
import secrets
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .schemas import (
    CaptureClosedReason,
    CoordinatorState,
    PersistenceMode,
    RecognitionResult,
    ResultState,
    ScanSession,
)
from . import CALIBRATION_STATUS_DEFAULT, GENERATOR_VERSION, INDEX_FORMAT_VERSION

TERMINAL = {CoordinatorState.COMMITTED, CoordinatorState.CANCELLED, CoordinatorState.FAILED}


@dataclass(frozen=True)
class Budgets:
    """Proposed F05 research budgets (D05: proposals, never relaxed after outcomes)."""

    permission_ms: int = 60_000
    switch_ms: int = 30_000
    sampling_ms: int = 12_000
    total_ms: int = 45_000
    post_capture_ms: int = 8_000
    result_validity_ms: int = 15 * 60_000


class StopCause(str, enum.Enum):
    APP_REQUESTED_ACK = "APP_REQUESTED_ACK"  # adapter says: this is the ack of our own stop()
    USER_STOP = "USER_STOP"                  # observed user action (chip, notification, in-app)
    SYSTEM_STOP = "SYSTEM_STOP"              # OS stopped it (lock, policy, contention)
    UNKNOWN = "UNKNOWN"                      # adapter cannot attribute the cause


@dataclass(frozen=True)
class AdapterContract:
    """Measured adapter semantics (per OS/build). Documented, not assumed."""

    can_attribute_normal_close: bool = False  # True only after LIFE-03 device evidence


@dataclass
class Audit:
    accepted_frames: int = 0
    rejected_frames: int = 0
    stale_worker_results: int = 0
    commits: int = 0
    aborts: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)


class Coordinator:
    def __init__(
        self,
        budgets: Budgets = Budgets(),
        adapter: AdapterContract = AdapterContract(),
        id_source: Callable[[], str] = lambda: secrets.token_hex(8),
    ):
        self.budgets = budgets
        self.adapter = adapter
        self._id_source = id_source
        self.state = CoordinatorState.IDLE
        self.generation = 0
        self.lease_active = False
        self.session: Optional[ScanSession] = None
        self.result: Optional[RecognitionResult] = None  # MEMORY ONLY
        self.audit = Audit()
        self._normal_close_requested = False
        self._abort_observed = False
        self._frames_in_window = 0

    # ------------------------------------------------------------------ helpers
    def _log(self, s: str) -> None:
        self.audit.events.append(s)

    def _active(self) -> bool:
        return self.state not in TERMINAL and self.state != CoordinatorState.IDLE

    def _abort(self, now: int, reason: CaptureClosedReason, terminal_reason: str, result_state: ResultState) -> None:
        """Atomically invalidate the generation and close everything. Idempotent after commit."""
        if self.state == CoordinatorState.COMMITTED:
            self._log(f"{now}: {terminal_reason} after commit — committed result stands; capture resources released")
            self.lease_active = False
            return
        if self.state in TERMINAL:
            return
        self._abort_observed = True
        self.generation += 1  # any in-flight worker now carries a stale generation
        self.lease_active = False
        self.state = CoordinatorState.CANCELLED if result_state == ResultState.CANCELLED else CoordinatorState.FAILED
        if self.session:
            self.session.coordinator_state = self.state
            if self.session.capture_closed_reason == CaptureClosedReason.NOT_CLOSED or reason != CaptureClosedReason.APP_REQUESTED_NORMAL_CLOSE:
                self.session.capture_closed_reason = reason
            self.session.terminal_reason = terminal_reason
        self.audit.aborts.append(terminal_reason)
        self._log(f"{now}: ABORT {terminal_reason} gen→{self.generation}")
        # The user-visible outcome of an aborted scan is itself a minimal result.
        self.result = self._plain_result(now, result_state, [terminal_reason])

    def _plain_result(self, now: int, state: ResultState, flags: List[str]) -> RecognitionResult:
        return RecognitionResult(
            scan_id=self.session.scan_id if self.session else "none",
            cancellation_generation=self.generation,
            state=state, candidate_work_id=None, candidate_edition_id=None, candidate_episode_id=None,
            segments=[], ambiguity_flags=flags, generator_version=GENERATOR_VERSION,
            index_format_version=INDEX_FORMAT_VERSION, calibration_version="n/a",
            calibration_status=CALIBRATION_STATUS_DEFAULT, local_entitlement_recheck="NOT_REQUIRED",
            created_at_monotonic_ms=now, expires_at_monotonic_ms=now + self.budgets.result_validity_ms,
            validity_clock_basis="monotonic", persistence_mode=PersistenceMode.MEMORY_ONLY,
        )

    # ------------------------------------------------------------------- events
    def start(self, now: int, capability_cell_id: str = "LAB", rights_snapshot_id: str = "L0") -> bool:
        """New user start. Rejected while a scan is active (single session)."""
        if self._active():
            self._log(f"{now}: start rejected — session active")
            return False
        self.generation += 1
        self.lease_active = True
        self._normal_close_requested = False
        self._abort_observed = False
        self._frames_in_window = 0
        self.result = None  # clear previous result (and any approved persisted copy — none in D08 default)
        self.state = CoordinatorState.AWAITING_PERMISSION
        self.session = ScanSession(
            scan_id=self._id_source(), cancellation_generation=self.generation, coordinator_state=self.state,
            capture_closed_reason=CaptureClosedReason.NOT_CLOSED,
            deadline_permission_ms=now + self.budgets.permission_ms, deadline_switch_ms=0, deadline_sampling_ms=0,
            deadline_total_ms=0, deadline_post_capture_ms=0, capability_cell_id=capability_cell_id,
            rights_snapshot_id=rights_snapshot_id, started_at_monotonic_ms=now,
        )
        self._log(f"{now}: START scan={self.session.scan_id} gen={self.generation}")
        return True

    def permission_granted(self, now: int) -> bool:
        if self.state != CoordinatorState.AWAITING_PERMISSION or not self.lease_active:
            self._log(f"{now}: late/unsolicited permission callback rejected")
            return False
        if now > self.session.deadline_permission_ms:
            self._abort(now, CaptureClosedReason.DEADLINE_EXPIRED, "PERMISSION_TIMEOUT_LATE_CALLBACK", ResultState.ERROR)
            return False
        self.state = CoordinatorState.AWAITING_TARGET
        self.session.coordinator_state = self.state
        self.session.deadline_switch_ms = now + self.budgets.switch_ms
        self.session.deadline_total_ms = now + self.budgets.total_ms
        self._log(f"{now}: PERMISSION_GRANTED")
        return True

    def permission_denied(self, now: int) -> None:
        if self.state != CoordinatorState.AWAITING_PERMISSION:
            return
        self._abort(now, CaptureClosedReason.PERMISSION_REVOKED, "PERMISSION_DENIED", ResultState.PERMISSION_DENIED)

    def target_ready(self, now: int) -> bool:
        if self.state != CoordinatorState.AWAITING_TARGET:
            return False
        if now > self.session.deadline_switch_ms or now > self.session.deadline_total_ms:
            self._abort(now, CaptureClosedReason.DEADLINE_EXPIRED, "TARGET_WAIT_TIMEOUT", ResultState.INSUFFICIENT_SIGNAL)
            return False
        self.state = CoordinatorState.ACQUIRING
        self.session.coordinator_state = self.state
        self.session.deadline_sampling_ms = min(now + self.budgets.sampling_ms, self.session.deadline_total_ms)
        self._log(f"{now}: TARGET_READY")
        return True

    def frame(self, now: int) -> bool:
        """Adapter asks whether a delivered frame may be processed."""
        ok = (
            self.state == CoordinatorState.ACQUIRING and self.lease_active and not self._abort_observed
            and now <= self.session.deadline_sampling_ms and now <= self.session.deadline_total_ms
        )
        if ok:
            self.audit.accepted_frames += 1
            self._frames_in_window += 1
        else:
            self.audit.rejected_frames += 1
        return ok

    def normal_close_requested(self, now: int, remaining_background_ms: Optional[int] = None) -> bool:
        """Sampling complete: stop intake, release capture via the measured API path, start the
        post-capture timer (bounded by actual remaining background time when known)."""
        if self.state != CoordinatorState.ACQUIRING:
            return False
        self._normal_close_requested = True
        self.state = CoordinatorState.POST_CAPTURE
        self.session.coordinator_state = self.state
        self.session.capture_closed_reason = CaptureClosedReason.APP_REQUESTED_NORMAL_CLOSE
        budget = self.budgets.post_capture_ms
        if remaining_background_ms is not None:
            budget = min(budget, max(0, remaining_background_ms))
        self.session.deadline_post_capture_ms = now + budget
        self._log(f"{now}: NORMAL_CLOSE_REQUESTED post_capture_deadline={self.session.deadline_post_capture_ms}")
        return True

    def capture_stopped(self, now: int, cause: StopCause) -> None:
        """OS stop callback. Cause attribution comes from the adapter contract, not a flag."""
        if self.state in TERMINAL or self.state == CoordinatorState.IDLE:
            self._log(f"{now}: stop callback ignored in {self.state.value}")
            return
        if cause == StopCause.USER_STOP:
            self._abort(now, CaptureClosedReason.USER_STOP_OBSERVED, "USER_STOP_OBSERVED", ResultState.CANCELLED)
        elif cause == StopCause.SYSTEM_STOP:
            self._abort(now, CaptureClosedReason.SYSTEM_STOP_OBSERVED, "SYSTEM_STOP_OBSERVED", ResultState.CANCELLED)
        elif cause == StopCause.APP_REQUESTED_ACK:
            if self._normal_close_requested and self.adapter.can_attribute_normal_close:
                self._log(f"{now}: normal-close acknowledgment (attributable) — idempotent")
            elif self._normal_close_requested:
                # Our flag alone cannot establish the callback cause (CQ-02). Fail closed.
                self._abort(now, CaptureClosedReason.AMBIGUOUS_FAIL_CLOSED, "STOP_CAUSE_UNATTRIBUTABLE", ResultState.CANCELLED)
            else:
                self._abort(now, CaptureClosedReason.AMBIGUOUS_FAIL_CLOSED, "UNEXPECTED_STOP_ACK", ResultState.CANCELLED)
        else:  # UNKNOWN
            self._abort(now, CaptureClosedReason.AMBIGUOUS_FAIL_CLOSED, "STOP_CAUSE_UNKNOWN", ResultState.CANCELLED)

    def lock(self, now: int) -> None:
        self._abort(now, CaptureClosedReason.LOCK, "DEVICE_LOCKED", ResultState.CANCELLED)

    def permission_revoked(self, now: int) -> None:
        self._abort(now, CaptureClosedReason.PERMISSION_REVOKED, "PERMISSION_REVOKED", ResultState.PERMISSION_DENIED)

    def cancel(self, now: int) -> None:
        """In-app Cancel: capture Stop *and* cancellation of unfinished computation."""
        self._abort(now, CaptureClosedReason.IN_APP_CANCEL, "IN_APP_CANCEL", ResultState.CANCELLED)

    def unsafe_context(self, now: int) -> None:
        self._abort(now, CaptureClosedReason.SYSTEM_STOP_OBSERVED, "UNSAFE_CONTEXT", ResultState.CANCELLED)

    def entitlement_failed(self, now: int) -> None:
        self._abort(now, CaptureClosedReason.SYSTEM_STOP_OBSERVED, "ENTITLEMENT_FAILED", ResultState.ERROR)

    def tick(self, now: int) -> None:
        """Deadline evaluation on the monotonic clock."""
        s = self.session
        if s is None or self.state in TERMINAL or self.state == CoordinatorState.IDLE:
            return
        if self.state == CoordinatorState.AWAITING_PERMISSION and now > s.deadline_permission_ms:
            self._abort(now, CaptureClosedReason.DEADLINE_EXPIRED, "PERMISSION_TIMEOUT", ResultState.ERROR)
        elif self.state == CoordinatorState.AWAITING_TARGET and (now > s.deadline_switch_ms or now > s.deadline_total_ms):
            self._abort(now, CaptureClosedReason.DEADLINE_EXPIRED, "TARGET_WAIT_TIMEOUT", ResultState.INSUFFICIENT_SIGNAL)
        elif self.state == CoordinatorState.ACQUIRING and (now > s.deadline_sampling_ms or now > s.deadline_total_ms):
            # Sampling window finished: this is the app's own normal close, not an abort.
            self.normal_close_requested(now)
        elif self.state == CoordinatorState.POST_CAPTURE and now > s.deadline_post_capture_ms:
            self._abort(now, CaptureClosedReason.DEADLINE_EXPIRED, "POST_CAPTURE_DEADLINE_EXPIRED", ResultState.ERROR)

    def worker_result(self, now: int, generation: int, build: Callable[[int, int], RecognitionResult], entitlement_ok: bool = True) -> bool:
        """Commit path. `build(scan_generation, now)` constructs the result under the lock.
        Returns True iff committed."""
        if generation != self.generation or self.state != CoordinatorState.POST_CAPTURE or self._abort_observed or not self.lease_active:
            self.audit.stale_worker_results += 1
            self._log(f"{now}: stale worker result rejected (gen {generation} vs {self.generation}, state {self.state.value})")
            return False
        if now > self.session.deadline_post_capture_ms:
            self._abort(now, CaptureClosedReason.DEADLINE_EXPIRED, "POST_CAPTURE_DEADLINE_EXPIRED", ResultState.ERROR)
            return False
        if not entitlement_ok:
            self.entitlement_failed(now)
            return False
        result = build(self.generation, now)
        if result.cancellation_generation != self.generation or result.scan_id != self.session.scan_id:
            self.audit.stale_worker_results += 1
            return False
        self.result = result
        self.state = CoordinatorState.COMMITTED
        self.session.coordinator_state = self.state
        self.session.terminal_reason = "COMMITTED"
        self.lease_active = False
        self.audit.commits += 1
        self._log(f"{now}: COMMIT {result.state.value}")
        return True

    def process_death(self) -> None:
        """Model process death / Task Manager kill: no cleanup callback; nothing restored."""
        self.__init__(self.budgets, self.adapter, self._id_source)  # memory gone; lease not restored

    def return_to_app(self, now: int, entitlement_ok: bool = True, clock_trustworthy: bool = True) -> Optional[RecognitionResult]:
        """Result-on-return: recheck validity and entitlement; discard invalid results."""
        r = self.result
        if r is None:
            return None
        if not r.is_valid_at(now, clock_trustworthy) or not entitlement_ok:
            self._log(f"{now}: result expired/invalid on return — discarded")
            self.result = None
            return None
        return r

    def discard(self) -> None:
        self.result = None
