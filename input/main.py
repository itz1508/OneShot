"""OneShot Phase 1 input boundary: parse transport data; never execute an action."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any

_ALLOWED_ACTIONS = frozenset({"research", "plan", "build"})
_ALLOWED_FIELDS = frozenset({"request_id", "action", "payload"})


class InputRejected(ValueError):
    """The request cannot be accepted at the input boundary."""


def accept_input(value: Any) -> dict[str, Any]:
    """Accept one declared request envelope; authorization belongs to System."""
    if not isinstance(value, Mapping) or not all(isinstance(k, str) for k in value):
        raise InputRejected("Input must be a JSON object")
    if set(value) != _ALLOWED_FIELDS:
        raise InputRejected("Input requires exactly request_id, action, and payload")
    request_id = value["request_id"]
    action = value["action"]
    payload = value["payload"]
    if not isinstance(request_id, str) or not request_id.strip():
        raise InputRejected("request_id must be a nonempty string")
    if not isinstance(action, str) or action not in _ALLOWED_ACTIONS:
        raise InputRejected("Unknown action")
    if not isinstance(payload, dict):
        raise InputRejected("payload must be a JSON object")
    # Preserve user data. No implicit authorization, task creation, or transitions.
    return {"request_id": request_id, "action": action, "payload": payload}


def main() -> int:
    try:
        raw = sys.stdin.read()
        request = json.loads(raw)
        accepted = accept_input(request)
    except (json.JSONDecodeError, InputRejected, TypeError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "accepted": False}), file=sys.stderr)
        return 2
    print(json.dumps(accepted, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
