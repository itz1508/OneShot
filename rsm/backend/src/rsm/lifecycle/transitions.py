"""Nine legal transitions from Spec §7.2.

LEGAL:
  RECEIVED  -> STAGED
  STAGED    -> STORED
  STORED    -> ACTIVATED
  ACTIVATED -> REPLAYED
  ACTIVATED -> RELEASED
  REPLAYED  -> RELEASED
  RELEASED  -> ACTIVATED   (re-activate; increments release_count)
  RELEASED  -> RETIRED
  RETIRED   -> (terminal; no outgoing transitions)

Any other (from, to) pair is illegal.
"""

from __future__ import annotations

from .states import State


LEGAL_TRANSITIONS: frozenset[tuple[State, State]] = frozenset(
    {
        (State.RECEIVED, State.STAGED),
        (State.STAGED, State.STORED),
        (State.STORED, State.ACTIVATED),
        (State.ACTIVATED, State.REPLAYED),
        (State.ACTIVATED, State.RELEASED),
        (State.REPLAYED, State.RELEASED),
        (State.RELEASED, State.ACTIVATED),
        (State.RELEASED, State.RETIRED),
    }
)


class IllegalTransition(Exception):
    """Raised when a lifecycle transition is not in LEGAL_TRANSITIONS."""


def is_legal(src: State, dst: State) -> bool:
    return (src, dst) in LEGAL_TRANSITIONS


def assert_legal(src: State, dst: State) -> None:
    if not is_legal(src, dst):
        raise IllegalTransition(f"Illegal lifecycle transition: {src} -> {dst}")
