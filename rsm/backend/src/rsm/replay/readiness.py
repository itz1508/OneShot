"""Replay readiness — derived from lifecycle + classification.

NOT a lifecycle state. Spec §11:
    REPLAY_BUILDABLE is a readiness property, not a bucket lifecycle state.

Rules (as derived here):
    - CLOSED (==RETIRED in the current enum)  -> NOT_REPLAYABLE  (spec §19)
    - RELEASED                                 -> REPLAY_BUILDABLE if classification is
                                                   READY_EXECUTION; otherwise REPLAYABLE
    - ACTIVATED / REPLAYED                     -> REPLAYABLE
    - STORED                                   -> REPLAYABLE (read-only)
    - earlier states                           -> NOT_YET_REPLAYABLE
"""

from __future__ import annotations

from enum import StrEnum

from ..classification.model import WorkClassification
from ..lifecycle.states import State


class Replayability(StrEnum):
    NOT_YET_REPLAYABLE = "NOT_YET_REPLAYABLE"
    REPLAYABLE = "REPLAYABLE"
    REPLAY_BUILDABLE = "REPLAY_BUILDABLE"
    NOT_REPLAYABLE = "NOT_REPLAYABLE"


def derive_replayability(
    state: State | str,
    classification: WorkClassification | str = WorkClassification.STORE,
) -> Replayability:
    s = State(state) if not isinstance(state, State) else state
    c = (
        WorkClassification(classification)
        if not isinstance(classification, WorkClassification)
        else classification
    )

    if s == State.RETIRED:
        # RETIRED is the "CLOSED" terminal — not replayable (§19).
        return Replayability.NOT_REPLAYABLE

    if s in {State.RECEIVED, State.STAGED}:
        return Replayability.NOT_YET_REPLAYABLE

    if s == State.RELEASED and c == WorkClassification.READY_EXECUTION:
        return Replayability.REPLAY_BUILDABLE

    # STORED, ACTIVATED, REPLAYED, and plain RELEASED are read-only replayable.
    return Replayability.REPLAYABLE
