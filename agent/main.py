"""Compatibility shim for legacy imports and CLI invocations.

The runnable package entry point and workflow implementation live in
`agent.__main__`.  New callers should use `python -m agent`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_impl = importlib.import_module("agent.__main__")
if __name__ == "__main__":
    raise SystemExit(_impl.main())
sys.modules[__name__] = _impl
