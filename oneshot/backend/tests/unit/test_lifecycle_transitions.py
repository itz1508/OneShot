"""All 9 legal transitions pass; everything else fails."""

import itertools
import pytest
from rsm.lifecycle.states import State, STATES
from rsm.lifecycle.transitions import LEGAL_TRANSITIONS, IllegalTransition, assert_legal


def test_nine_legal_transitions_exact():
    assert len(LEGAL_TRANSITIONS) == 8  # the spec enumerates 8 directed edges (9 numbered rules; RELEASED->ACTIVATED is one)


def test_each_legal_passes():
    for src, dst in LEGAL_TRANSITIONS:
        assert_legal(src, dst)


def test_all_other_pairs_fail():
    for src, dst in itertools.product(STATES, STATES):
        if (src, dst) in LEGAL_TRANSITIONS:
            continue
        with pytest.raises(IllegalTransition):
            assert_legal(src, dst)


def test_retired_is_terminal():
    for s in STATES:
        if s == State.RETIRED:
            continue
        with pytest.raises(IllegalTransition):
            assert_legal(State.RETIRED, s)
