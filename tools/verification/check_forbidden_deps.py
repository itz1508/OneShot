#!/usr/bin/env python3
"""Forbidden-dependency gate (Spec §6, gate 2 + §5.2).

FAILS the build if any file under oneshot/backend/src/rsm/ or oneshot/frontend/web/src/
imports or references any of the forbidden AI/model/provider libraries.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN = [
    "openai", "anthropic", "@google", "google.generativeai",
    "cohere", "mistralai", "together", "fireworks", "nebius", "ollama",
    "langchain", "langgraph", "llama_index", "llamaindex", "haystack",
    "dspy", "crewai", "autogen", "pydantic_ai", "pydanticai",
]

SCAN_DIRS = [
    ROOT / "oneshot" / "backend" / "src" / "rsm",
    ROOT / "oneshot" / "frontend" / "web" / "src",
    ROOT / "oneshot" / "frontend" / "packages" / "rsm-client" / "src",
]

EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs"}

PATTERNS = [re.compile(r"\b" + re.escape(name).replace(r"\@", "@") + r"\b") for name in FORBIDDEN]


def main() -> int:
    violations: list[str] = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if not p.is_file() or p.suffix not in EXTS:
                continue
            text = p.read_text("utf-8", errors="replace")
            for name, pat in zip(FORBIDDEN, PATTERNS):
                if pat.search(text):
                    violations.append(f"{p.relative_to(ROOT)}: references {name!r}")
    if violations:
        print("FORBIDDEN DEPENDENCY REFERENCES:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("forbidden-dep gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
