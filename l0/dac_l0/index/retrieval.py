"""Flat candidate retrieval (F04: hash/flat lookup baseline)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .builder import IndexBundle
from .descriptors import DescriptorFamily, Locator, hamming64


@dataclass(frozen=True)
class Candidate:
    locator: Locator
    distance: float


class FlatRetriever:
    def __init__(self, bundle: IndexBundle):
        self.bundle = bundle
        if bundle.family.is_hash:
            self._hashes = bundle.hash_u64()
        else:
            self._vecs = bundle.descriptors.astype(np.int32)

    def search(self, descriptor: bytes, top_k: int = 10, max_distance: float | None = None) -> List[Candidate]:
        b = self.bundle
        if b.vector_count == 0:
            return []
        if b.family.is_hash:
            q = np.frombuffer(descriptor, dtype="<u8")[0]
            dist = hamming64(self._hashes, q).astype(np.float32)
        else:
            q = np.frombuffer(descriptor, dtype=np.uint8).astype(np.int32)
            diff = self._vecs - q
            dist = np.sqrt((diff * diff).sum(axis=1, dtype=np.int64)).astype(np.float32)
        k = min(top_k, dist.shape[0])
        # Deterministic, portable ranking: distance ascending, then vector index ascending.
        # (argpartition's order among equal distances is implementation-defined; ED-16.)
        idx = np.argsort(dist, kind="stable")[:k]
        out = []
        for i in idx:
            d = float(dist[i])
            if max_distance is not None and d > max_distance:
                continue
            out.append(Candidate(Locator.unpack(b.locators[i].tobytes()), d))
        return out
