"""Installed pack store with staged, atomic activation and lab leases (IDX-01, SEC-03 partial,
RIGHTS-02/04 lab scope, P03-T06 development fixtures).

Layout under `root/`:
  staging/<pack_id>.<nonce>/      payload + manifest being validated (bounded size)
  active/<pack_id>/               the activated payload + manifest
  state.json                      minimum rights epoch, installed bytes, active versions
  state.json.tmp                  written then renamed (atomic replace)

Guarantees (tested with injected failures):
- A pack becomes active only after the full fail-closed loader accepted it from staging.
- Interruption or I/O failure at any step leaves the previously active pack usable and the
  state file either old or new, never partial.
- The rights epoch never decreases, including after rollback to an older compatible pack or
  after restoring an old `state.json` copy alongside a newer epoch marker.
- Staging is bounded: payload + manifest must fit `staging_cap_bytes` and the total installed
  budget (D10) before anything is written.

Lab leases (RIGHTS-04 analogue): a lease is valid for a finite duration measured on a
trustworthy elapsed-time basis (boot ID + monotonic clock). A reboot, a different boot ID, a
monotonic value lower than the anchor or an untrusted wall clock makes the lease require
revalidation; nothing extends a lease through untrusted time. No instant offline revocation
is claimed.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

from ..index.builder import TOTAL_INSTALLED_INDEX_BUDGET_BYTES
from .loader import DeviceRightsState, LoadedPack, PackRejected, load_pack

STATE_FILE = "state.json"
EPOCH_MARKER = "epoch.min"  # second, monotonic-only record so an old state.json cannot lower it


class StoreError(RuntimeError):
    pass


@dataclass
class Io:
    """Injectable file operations (tests inject failures)."""

    write_bytes: Callable[[Path, bytes], None] = lambda p, b: p.write_bytes(b)
    replace: Callable[[Path, Path], None] = lambda a, b: os.replace(a, b)
    rmtree: Callable[[Path], None] = lambda p: shutil.rmtree(p, ignore_errors=True)


@dataclass
class StoreState:
    minimum_rights_epoch: int = 0
    installed_index_bytes: Dict[str, int] = field(default_factory=dict)
    active_versions: Dict[str, str] = field(default_factory=dict)

    def to_json(self) -> bytes:
        return json.dumps(self.__dict__, sort_keys=True).encode()

    @classmethod
    def from_json(cls, b: bytes) -> "StoreState":
        d = json.loads(b.decode())
        return cls(int(d["minimum_rights_epoch"]), {k: int(v) for k, v in d["installed_index_bytes"].items()},
                   {k: str(v) for k, v in d["active_versions"].items()})


class PackStore:
    def __init__(self, root: Path, rights: DeviceRightsState, io: Io = Io(),
                 budget_bytes: int = TOTAL_INSTALLED_INDEX_BUDGET_BYTES, staging_cap_bytes: Optional[int] = None):
        self.root = root
        self.rights = rights
        self.io = io
        self.budget = budget_bytes
        self.staging_cap = staging_cap_bytes if staging_cap_bytes is not None else budget_bytes
        (root / "staging").mkdir(parents=True, exist_ok=True)
        (root / "active").mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()
        # Device rights state is derived from persisted state, never the other way round.
        rights.minimum_rights_epoch = max(rights.minimum_rights_epoch, self.state.minimum_rights_epoch)
        rights.installed_index_bytes = dict(self.state.installed_index_bytes)
        self._cleanup_staging()

    # ------------------------------------------------------------------ state
    def _load_state(self) -> StoreState:
        p = self.root / STATE_FILE
        st = StoreState()
        if p.exists():
            try:
                st = StoreState.from_json(p.read_bytes())
            except (ValueError, KeyError, json.JSONDecodeError):
                raise StoreError("state file corrupt; refusing to guess (revalidation required)")
        m = self.root / EPOCH_MARKER
        if m.exists():
            try:
                st.minimum_rights_epoch = max(st.minimum_rights_epoch, int(m.read_text().strip()))
            except ValueError:
                raise StoreError("epoch marker corrupt")
        return st

    def _persist(self, st: StoreState) -> None:
        tmp = self.root / (STATE_FILE + ".tmp")
        self.io.write_bytes(tmp, st.to_json())
        self.io.replace(tmp, self.root / STATE_FILE)
        mtmp = self.root / (EPOCH_MARKER + ".tmp")
        self.io.write_bytes(mtmp, str(st.minimum_rights_epoch).encode())
        self.io.replace(mtmp, self.root / EPOCH_MARKER)

    def _cleanup_staging(self) -> None:
        for d in (self.root / "staging").iterdir():
            self.io.rmtree(d)

    # ------------------------------------------------------------------ install
    def install(self, manifest_json: bytes, payload: bytes, now_iso: Optional[str], time_trustworthy: bool,
                release_mode: bool = False) -> LoadedPack:
        if len(payload) + len(manifest_json) > self.staging_cap:
            raise PackRejected("staging cap exceeded")
        try:
            pack_id = json.loads(manifest_json.decode())["pack_id"]
        except Exception:
            raise PackRejected("manifest not readable")
        if not isinstance(pack_id, str) or not pack_id.replace("-", "").replace("_", "").isalnum() or len(pack_id) > 64:
            raise PackRejected("bad pack id")
        stage = self.root / "staging" / f"{pack_id}.{secrets.token_hex(4)}"
        stage.mkdir()
        try:
            self.io.write_bytes(stage / "payload.pack", payload)
            self.io.write_bytes(stage / "manifest.json", manifest_json)
            # Validate what was actually written to staging, with a scratch copy of rights state.
            scratch = DeviceRightsState(self.rights.minimum_rights_epoch, dict(self.rights.installed_index_bytes),
                                        set(self.rights.accepted_region_methods), dict(self.rights.trusted_keys),
                                        set(self.rights.revoked_key_ids))
            lp = load_pack((stage / "manifest.json").read_bytes(), (stage / "payload.pack").read_bytes(), scratch,
                           now_iso, time_trustworthy, release_mode, self.budget)
            # Activate: rename staged dir over the active slot (old slot moved aside first).
            active = self.root / "active" / pack_id
            old = self.root / "active" / f".{pack_id}.old"
            if old.exists():
                self.io.rmtree(old)
            if active.exists():
                self.io.replace(active, old)
            try:
                self.io.replace(stage, active)
            except Exception:
                if old.exists():
                    self.io.replace(old, active)  # put the previous pack back
                raise
            new_state = StoreState(max(self.state.minimum_rights_epoch, lp.manifest["rights_epoch"]),
                                   {**self.state.installed_index_bytes, pack_id: len(payload)},
                                   {**self.state.active_versions, pack_id: lp.manifest["pack_version"]})
            try:
                self._persist(new_state)
            except Exception:
                # State could not be recorded: undo activation so files and state agree.
                if active.exists():
                    self.io.rmtree(active)
                if old.exists():
                    self.io.replace(old, active)
                raise
            if old.exists():
                self.io.rmtree(old)
            self.state = new_state
            self.rights.minimum_rights_epoch = new_state.minimum_rights_epoch
            self.rights.installed_index_bytes = dict(new_state.installed_index_bytes)
            return lp
        finally:
            if stage.exists():
                self.io.rmtree(stage)

    def active(self, pack_id: str, now_iso: Optional[str], time_trustworthy: bool) -> LoadedPack:
        """Re-verify the active pack on every load (files are untrusted at rest)."""
        d = self.root / "active" / pack_id
        if not d.exists():
            raise StoreError("no active pack")
        scratch = DeviceRightsState(self.rights.minimum_rights_epoch, {k: v for k, v in self.rights.installed_index_bytes.items() if k != pack_id},
                                    set(self.rights.accepted_region_methods), dict(self.rights.trusted_keys), set(self.rights.revoked_key_ids))
        return load_pack((d / "manifest.json").read_bytes(), (d / "payload.pack").read_bytes(), scratch, now_iso, time_trustworthy, False, self.budget)


# ---------------------------------------------------------------------- lab leases


@dataclass(frozen=True)
class TrustedTime:
    boot_id: str
    monotonic_ms: int
    wall_trusted: bool


@dataclass
class LabLease:
    """Finite lease anchored to a boot session's monotonic clock."""

    pack_id: str
    duration_ms: int
    anchor_boot_id: str
    anchor_monotonic_ms: int

    @classmethod
    def grant(cls, pack_id: str, duration_ms: int, t: TrustedTime) -> "LabLease":
        if not t.wall_trusted:
            raise PackRejected("cannot grant a lease on untrusted time")
        return cls(pack_id, duration_ms, t.boot_id, t.monotonic_ms)

    def status(self, t: TrustedTime) -> str:
        """VALID, EXPIRED or REVALIDATE (reboot, clock went backwards, untrusted time)."""
        if t.boot_id != self.anchor_boot_id or not t.wall_trusted:
            return "REVALIDATE"
        if t.monotonic_ms < self.anchor_monotonic_ms:
            return "REVALIDATE"
        return "VALID" if t.monotonic_ms - self.anchor_monotonic_ms < self.duration_ms else "EXPIRED"
