"""Work classification — independent of lifecycle (spec §9)."""

import pytest
from rsm.classification.model import WorkClassification, DEFAULT_CLASSIFICATION


def test_default_is_store():
    assert DEFAULT_CLASSIFICATION == WorkClassification.STORE


def test_four_values_exact():
    assert set(WorkClassification) == {
        WorkClassification.STORE,
        WorkClassification.REVIEW,
        WorkClassification.REVIEW_TODO,
        WorkClassification.READY_EXECUTION,
    }


def test_classification_is_strenum_cycle_safe():
    for v in WorkClassification:
        assert WorkClassification(v.value) == v
