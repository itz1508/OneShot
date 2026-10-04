"""Interaction records — V3 per-interaction authorization + source selection.

This package owns `InteractionRecord`, the per-interaction authorization gate
for RSM delivery. It is strictly a daemon-side auxiliary record (same discipline
as `rsm.classification` and `rsm.execution`): in-memory, keyed by an opaque
`interaction_id` supplied by the consuming runtime, and NOT persisted across
daemon restarts.

Design: ADR 0009 (interaction scope + ON/OFF), ADR 0010 (chunked-HTTP delivery).

Fail-closed defaults — an unknown or disabled interaction MUST NOT release any
Bucket content. Enforcement lives at the HTTP layer (`rsm.api.routers.interactions`
and the opt-in `interaction_id` parameter on `/replay` and `/snapshot`).

This module imports from stdlib + pydantic only. Boundary gate
(`tools/verification/check_boundaries.py`) must list `rsm.interaction` with a
forbidden set equivalent to the other domain packages — see that file.
"""

from .events import (
    TERMINAL_KINDS,
    InteractionEvent,
    InteractionEventKind,
    make_event,
)
from .model import InteractionRecord, DEFAULT_INTERACTION
from .store import InteractionStore, InteractionTerminated

__all__ = [
    "DEFAULT_INTERACTION",
    "InteractionEvent",
    "InteractionEventKind",
    "InteractionRecord",
    "InteractionStore",
    "InteractionTerminated",
    "TERMINAL_KINDS",
    "make_event",
]
