"""Installed pack store: staged validation, single-commit-point activation, restart recovery,
and lab leases (IDX-01, SEC-03 partial, RIGHTS-02/04 lab scope, P03-T06 development fixtures).

Layout under `root/`:
  staging/<pack_id>.<nonce>/          payload + manifest being validated (bounded size)
  packs/<pack_id>/<slot>/             immutable slot: payload.pack + manifest.json
  state.json                          COMMIT POINT: per pack {slot, version, bytes}, epoch, floors
  state.json.tmp                      written, then atomically renamed over state.json
  floors.json                         second record of epoch and version floors (never lowered)

Crash-consistency argument (verified by abrupt-termination tests that kill a child process
with os._exit at every I/O step, not only by exception handlers):
- A new slot directory is written next to the old one; nothing that state.json references is
  ever modified or deleted before the commit.
- The only commit point is the atomic replace of state.json. Before it, state.json names the
  old slot (still intact); after it, the new one (already fully written and validated).
- On every start, recovery deletes staging leftovers, temp files and every slot that
  state.json does not reference. It then re-verifies nothing implicitly: active() re-runs the
  full loader on the referenced slot each time it is used.
- floors.json is written after the commit. Startup takes the maximum of state.json and
  floors.json, so restoring an old state.json cannot lower the rights epoch or version floors.
  If floors.json is ahead of state.json (restored old state), the referenced older pack may then
  fail re-verification: that is fail-closed and intended.
Limits: os.replace is atomic on the same volume; durability across power loss also needs
fsync, which this desktop harness performs on the state file and slot files (best effort on
directories, platform dependent). Device storage semantics must be re-checked on Android/iOS.

Lab leases (RIGHTS-04 analogue): a lease is valid for a finite duration measured on a
trustworthy elapsed-time basis (boot ID + monotonic clock). A reboot, a different boot ID, a
monotonic value lower than the anchor or an untrusted wall clock makes the lease require
revalidation; nothing extends a lease through untrusted time. No instant offline revocation
is claimed.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple, Union

from ..index.builder import TOTAL_INSTALLED_INDEX_BUDGET_BYTES
from .loader import DeviceRightsState, LoadedPack, PackRejected, load_pack

STATE_FILE = "state.json"
FLOORS_FILE = "floors.json"
_SLOT = re.compile(r"^[0-9a-f]{16}$")
_PACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class StoreError(RuntimeError):
    pass


def _write_durable(p: Path, b: bytes) -> None:
    with open(p, "wb") as f:
        f.write(b)
        f.flush()
        os.fsync(f.fileno())


@dataclass
class Io:
    """Injectable file operations (tests inject failures and abrupt termination)."""

    write_bytes: Callable[[Path, bytes], None] = _write_durable
    replace: Callable[[Path, Path], None] = lambda a, b: os.replace(a, b)
    rmtree: Callable[[Path], None] = lambda p: shutil.rmtree(p, ignore_errors=True)
    mkdir: Callable[[Path], None] = lambda p: p.mkdir(parents=True)


@dataclass
class StoreState:
    minimum_rights_epoch: int = 0
    packs: Dict[str, Dict] = field(default_factory=dict)  # pack_id -> {"slot", "version", "bytes"}
    minimum_pack_versions: Dict[str, Tuple[int, int, int]] = field(default_factory=dict)

    @property
    def installed_index_bytes(self) -> Dict[str, int]:
        return {k: int(v["bytes"]) for k, v in self.packs.items()}

    @property
    def active_versions(self) -> Dict[str, str]:
        return {k: str(v["version"]) for k, v in self.packs.items()}

    def to_json(self) -> bytes:
        return json.dumps({"format": "store-v2", "minimum_rights_epoch": self.minimum_rights_epoch, "packs": self.packs,
                           "minimum_pack_versions": {k: list(v) for k, v in self.minimum_pack_versions.items()}},
                          sort_keys=True).encode()

    @classmethod
    def from_json(cls, b: bytes) -> "StoreState":
        d = json.loads(b.decode())
        if d.get("format") != "store-v2":
            raise ValueError("unknown store format")
        packs = {}
        for k, v in d["packs"].items():
            if not _PACK_ID.fullmatch(k) or not _SLOT.fullmatch(v["slot"]) or int(v["bytes"]) < 0:
                raise ValueError("bad pack entry")
            packs[k] = {"slot": v["slot"], "version": str(v["version"]), "bytes": int(v["bytes"])}
        floors = {k: tuple(int(x) for x in v) for k, v in d["minimum_pack_versions"].items()}
        if any(len(v) != 3 for v in floors.values()):
            raise ValueError("bad version floor")
        return cls(int(d["minimum_rights_epoch"]), packs, floors)


class PackStore:
    def __init__(self, root: Path, rights: DeviceRightsState, io: Io = Io(),
                 budget_bytes: int = TOTAL_INSTALLED_INDEX_BUDGET_BYTES, staging_cap_bytes: Optional[int] = None):
        self.root = root
        self.rights = rights
        self.io = io
        self.budget = budget_bytes
        self.staging_cap = staging_cap_bytes if staging_cap_bytes is not None else budget_bytes
        for d in ("staging", "packs"):
            (root / d).mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()
        self.recovery_actions = self._recover()
        self._sync_rights()

    # ------------------------------------------------------------------ state
    def _load_state(self) -> StoreState:
        p = self.root / STATE_FILE
        st = StoreState()
        if p.exists():
            try:
                st = StoreState.from_json(p.read_bytes())
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                raise StoreError("state file corrupt; refusing to guess (revalidation required)")
        f = self.root / FLOORS_FILE
        if f.exists():
            try:
                fl = json.loads(f.read_bytes().decode())
                st.minimum_rights_epoch = max(st.minimum_rights_epoch, int(fl["minimum_rights_epoch"]))
                for k, v in fl["minimum_pack_versions"].items():
                    t = tuple(int(x) for x in v)
                    if len(t) != 3:
                        raise ValueError
                    st.minimum_pack_versions[k] = max(st.minimum_pack_versions.get(k, (0, 0, 0)), t)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                raise StoreError("floors file corrupt")
        return st

    def _recover(self) -> list:
        """Delete everything state.json does not reference. Returns the actions taken."""
        actions = []
        for d in (self.root / "staging").iterdir():
            self.io.rmtree(d)
            actions.append(f"removed staging {d.name}")
        for tmp in (self.root / (STATE_FILE + ".tmp"), self.root / (FLOORS_FILE + ".tmp")):
            if tmp.exists():
                tmp.unlink()
                actions.append(f"removed {tmp.name}")
        for pack_dir in (self.root / "packs").iterdir():
            ref = self.state.packs.get(pack_dir.name, {}).get("slot")
            for slot in pack_dir.iterdir():
                if slot.name != ref:
                    self.io.rmtree(slot)
                    actions.append(f"removed unreferenced slot {pack_dir.name}/{slot.name}")
            if ref is None and not any(pack_dir.iterdir()):
                pack_dir.rmdir()
        for pid, entry in self.state.packs.items():
            slot = self.root / "packs" / pid / entry["slot"]
            if not (slot / "payload.pack").exists() or not (slot / "manifest.json").exists():
                raise StoreError(f"state references a missing slot for {pid}; revalidation required")
        return actions

    def _sync_rights(self) -> None:
        # Device rights state is derived from persisted state, never the other way round.
        self.rights.minimum_rights_epoch = max(self.rights.minimum_rights_epoch, self.state.minimum_rights_epoch)
        self.rights.installed_index_bytes = dict(self.state.installed_index_bytes)
        for k, v in self.state.minimum_pack_versions.items():
            self.rights.minimum_pack_versions[k] = max(self.rights.minimum_pack_versions.get(k, (0, 0, 0)), v)

    def _scratch_rights(self, exclude_pack: Optional[str] = None) -> DeviceRightsState:
        r = self.rights
        return DeviceRightsState(
            minimum_rights_epoch=r.minimum_rights_epoch,
            installed_index_bytes={k: v for k, v in r.installed_index_bytes.items() if k != exclude_pack},
            minimum_pack_versions=dict(r.minimum_pack_versions),
            accepted_region_methods=set(r.accepted_region_methods),
            trusted_keys=dict(r.trusted_keys),
            revoked_key_ids=set(r.revoked_key_ids),
        )

    def _commit(self, st: StoreState) -> None:
        tmp = self.root / (STATE_FILE + ".tmp")
        self.io.write_bytes(tmp, st.to_json())
        self.io.replace(tmp, self.root / STATE_FILE)          # <- the commit point
        ftmp = self.root / (FLOORS_FILE + ".tmp")
        self.io.write_bytes(ftmp, json.dumps({"minimum_rights_epoch": st.minimum_rights_epoch,
                                              "minimum_pack_versions": {k: list(v) for k, v in st.minimum_pack_versions.items()}},
                                             sort_keys=True).encode())
        self.io.replace(ftmp, self.root / FLOORS_FILE)

    # ------------------------------------------------------------------ install
    def install(self, manifest_json: bytes, payload: bytes, now: Union[None, str, datetime], time_trustworthy: bool,
                release_mode: bool = False) -> LoadedPack:
        if len(payload) + len(manifest_json) > self.staging_cap:
            raise PackRejected("staging cap exceeded")
        try:
            pack_id = json.loads(manifest_json.decode())["pack_id"]
        except Exception:
            raise PackRejected("manifest not readable")
        if not isinstance(pack_id, str) or not _PACK_ID.fullmatch(pack_id):
            raise PackRejected("bad pack_id")
        stage = self.root / "staging" / f"{pack_id}.{secrets.token_hex(4)}"
        self.io.mkdir(stage)
        try:
            self.io.write_bytes(stage / "payload.pack", payload)
            self.io.write_bytes(stage / "manifest.json", manifest_json)
            # Validate exactly what was written, against a scratch copy of the rights state.
            lp = load_pack((stage / "manifest.json").read_bytes(), (stage / "payload.pack").read_bytes(),
                           self._scratch_rights(exclude_pack=pack_id), now, time_trustworthy, release_mode, self.budget)
            slot = secrets.token_hex(8)
            (self.root / "packs" / pack_id).mkdir(exist_ok=True)
            self.io.replace(stage, self.root / "packs" / pack_id / slot)   # new immutable slot
            from .loader import parse_version
            declared_min = parse_version(lp.manifest["minimum_allowed_version"], "minimum_allowed_version")
            new_state = StoreState(
                max(self.state.minimum_rights_epoch, lp.manifest["rights_epoch"]),
                {**self.state.packs, pack_id: {"slot": slot, "version": lp.manifest["pack_version"], "bytes": len(payload)}},
                {**self.state.minimum_pack_versions,
                 pack_id: max(self.state.minimum_pack_versions.get(pack_id, (0, 0, 0)), declared_min)},
            )
            try:
                self._commit(new_state)
            except Exception:
                # Not committed (or committed but floors not written): recovery on this or the
                # next start resolves it from state.json alone.
                self.state = self._load_state()
                self._recover()
                self._sync_rights()
                raise
            self.state = new_state
            self._recover()       # drop the previous slot now that state.json no longer names it
            self._sync_rights()
            return lp
        finally:
            if stage.exists():
                self.io.rmtree(stage)

    def active(self, pack_id: str, now: Union[None, str, datetime], time_trustworthy: bool) -> LoadedPack:
        """Re-verify the referenced slot on every load (files are untrusted at rest)."""
        entry = self.state.packs.get(pack_id)
        if entry is None:
            raise StoreError("no active pack")
        d = self.root / "packs" / pack_id / entry["slot"]
        return load_pack((d / "manifest.json").read_bytes(), (d / "payload.pack").read_bytes(),
                         self._scratch_rights(exclude_pack=pack_id), now, time_trustworthy, False, self.budget)


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
