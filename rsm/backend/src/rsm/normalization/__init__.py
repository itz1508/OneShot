"""Deterministic structural normalization of a Bucket's content (spec §11).

RSM's extraction already produces deterministic canonical content inside the
Bucket. This module exposes a stable "normalized" projection used by Snapshot
derivation — nothing new is invented; nothing is summarised; nothing is
reinterpreted. The projection is a pure function of the frozen A1 fields.
"""

from .model import NormalizedSource, normalize

__all__ = ["NormalizedSource", "normalize"]
