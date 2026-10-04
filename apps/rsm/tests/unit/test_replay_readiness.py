"""Replay readiness is DERIVED, not a lifecycle state (spec §11)."""

from rsm.classification.model import WorkClassification
from rsm.lifecycle.states import State
from rsm.replay.readiness import Replayability, derive_replayability


def test_retired_never_replayable():
    for c in WorkClassification:
        assert derive_replayability(State.RETIRED, c) == Replayability.NOT_REPLAYABLE


def test_released_ready_execution_is_replay_buildable():
    assert (
        derive_replayability(State.RELEASED, WorkClassification.READY_EXECUTION)
        == Replayability.REPLAY_BUILDABLE
    )


def test_released_plain_is_replayable():
    assert (
        derive_replayability(State.RELEASED, WorkClassification.STORE)
        == Replayability.REPLAYABLE
    )


def test_pre_stored_is_not_yet_replayable():
    for s in (State.RECEIVED, State.STAGED):
        assert derive_replayability(s, WorkClassification.STORE) == Replayability.NOT_YET_REPLAYABLE


def test_stored_and_activated_are_replayable():
    for s in (State.STORED, State.ACTIVATED, State.REPLAYED):
        assert derive_replayability(s, WorkClassification.STORE) == Replayability.REPLAYABLE
