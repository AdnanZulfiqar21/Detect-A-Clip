"""Canonical, versioned, locally minimised records (roadmap F04 table).

Design rules enforced here:
- RecognitionResult can never carry a captured image or a query descriptor.
- OUTSIDE_CATALOGUE and REMOTE_UNAVAILABLE are reserved and unreachable in L0/L1.
- persistence_mode defaults to MEMORY_ONLY (D08 unapproved).
- Rights are default-deny: an operation or territory not explicitly granted is denied.
- No field stores a reusable OS projection handle or permission token.
"""
from __future__ import annotations

import dataclasses
import enum
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "l0-schema-1"


class ResultState(str, enum.Enum):
    VERIFIED_MATCH = "VERIFIED_MATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    NO_CONFIDENT_MATCH = "NO_CONFIDENT_MATCH"
    OUTSIDE_CATALOGUE = "OUTSIDE_CATALOGUE"  # reserved; unreachable in L0/L1 (F03, F-12)
    INSUFFICIENT_SIGNAL = "INSUFFICIENT_SIGNAL"
    UNSUPPORTED_CAPTURE = "UNSUPPORTED_CAPTURE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    REMOTE_UNAVAILABLE = "REMOTE_UNAVAILABLE"  # reserved; unreachable in Mode L


# States that the L0/L1 local pipeline may actually emit.
REACHABLE_RESULT_STATES = frozenset(
    {
        ResultState.VERIFIED_MATCH,
        ResultState.POSSIBLE_MATCH,
        ResultState.NO_CONFIDENT_MATCH,
        ResultState.INSUFFICIENT_SIGNAL,
        ResultState.UNSUPPORTED_CAPTURE,
        ResultState.PERMISSION_DENIED,
        ResultState.CANCELLED,
        ResultState.ERROR,
    }
)


class PersistenceMode(str, enum.Enum):
    MEMORY_ONLY = "MEMORY_ONLY"  # default (D08 unapproved)
    COMMITTED_RESULT_ONLY = "COMMITTED_RESULT_ONLY"  # only if D08 approved; never descriptors


class EvidenceStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    DESIGN_UPDATED = "DESIGN_UPDATED"
    IMPLEMENTED_NOT_VERIFIED = "IMPLEMENTED_NOT_VERIFIED"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"
    DEFERRED = "DEFERRED"
    UNVERIFIED = "UNVERIFIED"


class PermittedAct(str, enum.Enum):
    """Distinct acts; a grant lists exactly the acts it permits (default deny)."""

    INGEST_REFERENCE = "INGEST_REFERENCE"
    BUILD_INDEX = "BUILD_INDEX"
    LOCAL_DISTRIBUTION = "LOCAL_DISTRIBUTION"
    TRANSIENT_QUERY = "TRANSIENT_QUERY"
    DECISION = "DECISION"
    DISPLAY_METADATA = "DISPLAY_METADATA"
    DISPLAY_STILL = "DISPLAY_STILL"
    DERIVATIVE_DESCRIPTOR = "DERIVATIVE_DESCRIPTOR"
    EVALUATION = "EVALUATION"
    # Never granted for user screens; listed so that it can be explicitly absent.
    TRAINING = "TRAINING"


class RegionAssuranceMethod(str, enum.Enum):
    """D07 candidates. NONE is the only method a synthetic pack needs; every other
    method is UNACCEPTED until the owner and licensor accept it (see pack loader)."""

    NONE = "NONE"
    STORE_COUNTRY_ATTESTATION = "STORE_COUNTRY_ATTESTATION"
    ONLINE_ACTIVATION = "ONLINE_ACTIVATION"
    COARSE_LOCATION = "COARSE_LOCATION"


class CoordinatorState(str, enum.Enum):
    IDLE = "IDLE"
    AWAITING_PERMISSION = "AWAITING_PERMISSION"
    AWAITING_TARGET = "AWAITING_TARGET"
    ACQUIRING = "ACQUIRING"
    POST_CAPTURE = "POST_CAPTURE"
    COMMITTED = "COMMITTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class CaptureClosedReason(str, enum.Enum):
    NOT_CLOSED = "NOT_CLOSED"
    APP_REQUESTED_NORMAL_CLOSE = "APP_REQUESTED_NORMAL_CLOSE"
    USER_STOP_OBSERVED = "USER_STOP_OBSERVED"
    SYSTEM_STOP_OBSERVED = "SYSTEM_STOP_OBSERVED"
    LOCK = "LOCK"
    PERMISSION_REVOKED = "PERMISSION_REVOKED"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
    AMBIGUOUS_FAIL_CLOSED = "AMBIGUOUS_FAIL_CLOSED"
    IN_APP_CANCEL = "IN_APP_CANCEL"
    PROCESS_DEATH_ASSUMED = "PROCESS_DEATH_ASSUMED"


class SchemaError(ValueError):
    pass


def _as_dict(obj: Any) -> Dict[str, Any]:
    d = dataclasses.asdict(obj)
    d["schema_version"] = SCHEMA_VERSION
    d["record_type"] = type(obj).__name__
    return d


def to_json(obj: Any) -> str:
    return json.dumps(_as_dict(obj), sort_keys=True, separators=(",", ":"), default=str)


# --------------------------------------------------------------------------- records


@dataclass(frozen=True)
class TermsReceipt:
    terms_version: str
    terms_hash: str
    locale: str
    rendered_text_hash: str
    governing_language_version: str
    accepted_at: str  # ISO-8601 UTC
    disclosure_version: str
    # Separate purpose choices; never an OS permission token.
    purpose_choices: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for k in ("terms_version", "terms_hash", "locale", "rendered_text_hash", "accepted_at"):
            if not getattr(self, k):
                raise SchemaError(f"TermsReceipt.{k} is required")


@dataclass
class ScanSession:
    scan_id: str
    cancellation_generation: int
    coordinator_state: CoordinatorState
    capture_closed_reason: CaptureClosedReason
    # Monotonic deadlines in milliseconds on the session's monotonic clock.
    deadline_permission_ms: int
    deadline_switch_ms: int
    deadline_sampling_ms: int
    deadline_total_ms: int
    deadline_post_capture_ms: int
    capability_cell_id: str
    rights_snapshot_id: str
    started_at_monotonic_ms: int
    terminal_reason: Optional[str] = None
    # Explicitly NOT present: projection handle, media token, intent, OS permission token.


@dataclass
class CapabilityCell:
    cell_id: str
    source: str
    os: str
    os_build: str
    patch_level: str
    device: str
    region: str
    picker_mode: str
    source_identity_method: str
    source_identity_confidence: str
    api_path: str
    scope_guarantee: str
    scope_limits: str
    stop_path: str
    lab_status: EvidenceStatus = EvidenceStatus.NOT_STARTED
    consumer_status: EvidenceStatus = EvidenceStatus.BLOCKED
    policy_status: EvidenceStatus = EvidenceStatus.BLOCKED
    store_status: EvidenceStatus = EvidenceStatus.BLOCKED
    tested_at: Optional[str] = None
    retest_by: Optional[str] = None
    expires_at: Optional[str] = None
    reviewer: Optional[str] = None
    build_hash: Optional[str] = None
    evidence_hashes: List[str] = field(default_factory=list)


@dataclass
class RightsGrant:
    grant_id: str
    licensor: str
    chain_of_title_evidence: str
    permitted_acts: List[PermittedAct]
    territories: List[str]  # ["*"] only for synthetic self-created material
    valid_from: str
    valid_until: Optional[str]
    offline_conditions: str
    revocation_conditions: str
    approval_status: str  # e.g. SELF_GRANT_SYNTHETIC_PENDING_REVIEW, APPROVED, REVOKED
    region_assurance_method: RegionAssuranceMethod = RegionAssuranceMethod.NONE

    def permits(self, act: PermittedAct, territory: str) -> bool:
        """Default deny: unknown act or territory denies."""
        if self.approval_status.startswith("REVOKED"):
            return False
        if act not in self.permitted_acts:
            return False
        return "*" in self.territories or territory in self.territories


@dataclass
class ReferenceAsset:
    asset_id: str
    work_id: str
    series_id: Optional[str]
    episode_id: Optional[str]
    edition_id: str
    segment_ids: List[str]
    source: str
    content_hash: str
    is_query_only: bool  # query/reference distinction
    grant_id: str
    created_at: str
    derivative_rights: bool
    local_distribution_rights: bool
    training_rights: bool  # must be False for anything derived from user screens
    display_rights: bool


@dataclass
class PackManifest:
    pack_id: str
    pack_version: str
    payload_sha256: str
    payload_size_bytes: int
    generator_version: str
    preprocessing_version: str
    index_format_version: str
    calibration_version: str
    calibration_status: str  # UNCALIBRATED until P04-T05
    rights_epoch: int
    valid_from: str
    valid_until: Optional[str]
    signed_time_basis: str
    key_id: str
    tombstones: List[str]
    minimum_allowed_version: str
    region_grants: List[str]
    operation_grants: List[PermittedAct]
    region_assurance_method: RegionAssuranceMethod
    indexed_hours: float
    title_count: int
    descriptor_bytes: int
    sampling_interval_s: float
    descriptor_family: str
    vector_count: int
    grant_id: str


@dataclass
class EntitlementLease:
    lease_id: str
    pack_id: str
    valid_from: str
    valid_until: str
    signed_time_basis: str
    key_id: str
    region_grants: List[str]
    operation_grants: List[PermittedAct]
    region_assurance_method: RegionAssuranceMethod
    rights_epoch: int


@dataclass
class SegmentEvidence:
    work_id: str
    edition_id: Optional[str]
    query_start_ms: int
    query_end_ms: int
    reference_offset_ms: Optional[int]
    supporting_frames: int


@dataclass
class RecognitionResult:
    scan_id: str
    cancellation_generation: int
    state: ResultState
    candidate_work_id: Optional[str]
    candidate_edition_id: Optional[str]
    candidate_episode_id: Optional[str]
    segments: List[SegmentEvidence]
    ambiguity_flags: List[str]
    generator_version: str
    index_format_version: str
    calibration_version: str
    calibration_status: str
    local_entitlement_recheck: str  # PASS / FAIL / NOT_REQUIRED
    created_at_monotonic_ms: int
    expires_at_monotonic_ms: int
    validity_clock_basis: str
    persistence_mode: PersistenceMode = PersistenceMode.MEMORY_ONLY
    synthetic_label: bool = True  # L0 results are visibly synthetic

    FORBIDDEN_FIELDS = ("image", "frame", "descriptor", "embedding", "thumbnail", "pixels")

    def __post_init__(self) -> None:
        if self.state in (ResultState.OUTSIDE_CATALOGUE, ResultState.REMOTE_UNAVAILABLE):
            raise SchemaError(f"{self.state.value} is reserved and unreachable in L0/L1")
        if self.state not in REACHABLE_RESULT_STATES:
            raise SchemaError(f"unreachable state {self.state}")
        if self.expires_at_monotonic_ms <= self.created_at_monotonic_ms:
            raise SchemaError("result must have a positive validity window")
        if self.state in (ResultState.VERIFIED_MATCH, ResultState.POSSIBLE_MATCH):
            if not self.candidate_work_id:
                raise SchemaError("match states require a candidate work")
        else:
            if self.candidate_work_id or self.candidate_edition_id or self.candidate_episode_id:
                raise SchemaError("non-match states must not name a candidate")
        if self.persistence_mode != PersistenceMode.MEMORY_ONLY:
            # D08 is unapproved; constructing a persistable result is an explicit opt-in that
            # the caller must have justified through DECISIONS.md. We allow the enum value so
            # LIFE-04 tests can model it, but never set it by default.
            pass

    def is_valid_at(self, now_monotonic_ms: int, clock_trustworthy: bool = True) -> bool:
        """Expiry check before every display/read. Untrustworthy time fails closed."""
        if not clock_trustworthy:
            return False
        if now_monotonic_ms < self.created_at_monotonic_ms:  # rollback
            return False
        return now_monotonic_ms < self.expires_at_monotonic_ms


@dataclass
class GateEvidence:
    gate_or_test_id: str
    run_id: str
    build_or_source_hash: str
    device_os_source_build: str
    lawful_asset_manifest_hash: str
    setup: str
    expected: str
    observed: str
    limitations: str
    artifact_hash: str
    author: str
    independent_reviewer: Optional[str]
    purpose: str  # LAB or RELEASE
    status: EvidenceStatus
    recorded_at: str


def assert_no_forbidden_keys(d: Dict[str, Any]) -> None:
    """Guard used when serialising results to any sink: no pixel/descriptor data."""
    for k in d:
        lk = k.lower()
        for bad in RecognitionResult.FORBIDDEN_FIELDS:
            if bad in lk:
                raise SchemaError(f"forbidden field in result sink: {k}")
