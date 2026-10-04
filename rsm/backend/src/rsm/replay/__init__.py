"""Replay readiness and envelope (spec §11, §14).

Replay readiness is a DERIVED property, NOT a lifecycle state.
"""

from .readiness import Replayability, derive_replayability
from .envelope import build_replay_envelope

__all__ = ["Replayability", "derive_replayability", "build_replay_envelope"]
