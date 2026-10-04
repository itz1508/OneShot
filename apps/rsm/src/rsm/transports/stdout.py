"""stdout transport — print canonical JSON to stdout."""

from __future__ import annotations

import sys

from .canonical import CanonicalPayload
from .json_export import to_json_export


def to_stdout(payload: CanonicalPayload, *, newline: bool = True) -> None:
    sys.stdout.buffer.write(to_json_export(payload))
    if newline:
        sys.stdout.buffer.write(b"\n")
    sys.stdout.flush()
