"""Seven-state lifecycle machine and the nine legal transitions (Spec §7)."""

from .states import State, STATES
from .transitions import (
    LEGAL_TRANSITIONS,
    IllegalTransition,
    is_legal,
    assert_legal,
)
from .events import LifecycleEvent, event_log_entry

__all__ = [
    "State",
    "STATES",
    "LEGAL_TRANSITIONS",
    "IllegalTransition",
    "is_legal",
    "assert_legal",
    "LifecycleEvent",
    "event_log_entry",
]
