"""Seven canonical lifecycle states."""

from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    RECEIVED = "RECEIVED"
    STAGED = "STAGED"
    STORED = "STORED"
    ACTIVATED = "ACTIVATED"
    REPLAYED = "REPLAYED"
    RELEASED = "RELEASED"
    RETIRED = "RETIRED"


STATES: tuple[State, ...] = (
    State.RECEIVED,
    State.STAGED,
    State.STORED,
    State.ACTIVATED,
    State.REPLAYED,
    State.RELEASED,
    State.RETIRED,
)
