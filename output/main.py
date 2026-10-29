"""OneShot Phase 1 output boundary: select and validate one declared result contract.

This component does not run Research, Plan, Build, authorization, or cleanup.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

_SCHEMA_DIR = Path(__file__).resolve().parent / "schema"
_CONTRACT_FILES = {"research": "research.json", "plan": "plan.json", "build": "build.json"}


class OutputRejected(ValueError):
    """Result does not satisfy its declared output contract."""


@lru_cache(maxsize=3)
def _validator(contract: str) -> Draft202012Validator:
    filename = _CONTRACT_FILES[contract]
    document = json.loads((_SCHEMA_DIR / filename).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document)


def validate_output(value: Any) -> dict[str, Any]:
    """Validate, but never reinterpret, repair or advance a result."""
    if not isinstance(value, dict):
        raise OutputRejected("Output must be a JSON object")
    contract = value.get("type")
    if not isinstance(contract, str) or contract not in _CONTRACT_FILES:
        raise OutputRejected("Unknown output type")
    try:
        _validator(contract).validate(value)
    except ValidationError as exc:
        location = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise OutputRejected(f"Invalid {contract} output at {location}: {exc.message}") from exc
    return value


def main() -> int:
    try:
        raw = sys.stdin.read()
        result = validate_output(json.loads(raw))
    except (json.JSONDecodeError, OutputRejected, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "valid": False}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
