"""Work classification model."""

from __future__ import annotations

from enum import StrEnum


class WorkClassification(StrEnum):
    STORE = "STORE"
    REVIEW = "REVIEW"
    REVIEW_TODO = "REVIEW_TODO"
    READY_EXECUTION = "READY_EXECUTION"


DEFAULT_CLASSIFICATION: WorkClassification = WorkClassification.STORE


# Independence rules (spec §9):
#   - Classification is INDEPENDENT of bucket lifecycle.
#   - Classification is INDEPENDENT of execution state.
#   - Classification does not advance automatically when the lifecycle advances.
#   - Changing classification MUST NOT touch frozen bucket fields (A1).
