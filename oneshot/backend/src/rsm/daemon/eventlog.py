"""Append-only lifecycle event log."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class EventLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def append(self, event: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True, separators=(",", ":")))
            f.write("\n")

    def read(self, bucket_id: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.path.exists():
            return out
        for line in self.path.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            ev = json.loads(line)
            if bucket_id is None or ev.get("bucket_id") == bucket_id:
                out.append(ev)
        return out
