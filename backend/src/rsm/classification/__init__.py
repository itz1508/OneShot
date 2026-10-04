"""Work classification — independent of bucket lifecycle (spec §9).

Values:
    STORE            — passive archive; no outstanding work
    REVIEW           — someone must look at it
    REVIEW_TODO      — review turned up outstanding tasks
    READY_EXECUTION  — ready to be executed by downstream work
"""

from .model import WorkClassification, DEFAULT_CLASSIFICATION

__all__ = ["WorkClassification", "DEFAULT_CLASSIFICATION"]
