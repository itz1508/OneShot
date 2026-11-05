"""Data validation at the sandbox boundary. This does not replace host admission."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath

from .contracts import SandboxExecutionRequest

_FORBIDDEN = {".git", ".env", ".ssh", ".aws", ".modal", ".oneshot-state", ".state", "node_modules", "__pycache__"}
_DRIVE = re.compile(r"^[a-zA-Z]:")


def normalize_path(p: str, *, allow_root: bool = False) -> str:
    if p == "." and allow_root:
        return p
    if not isinstance(p, str) or not p or "\\" in p or "\x00" in p or _DRIVE.match(p) or p.startswith("/"):
        raise ValueError("unsafe path")
    parts = p.split("/")
    if any(not x or x in {".", ".."} or x.casefold() in _FORBIDDEN or x.casefold().startswith(".env.") for x in parts):
        raise ValueError("unsafe path segment")
    if len(p) > 4096 or PurePosixPath(p).as_posix() != p:
        raise ValueError("noncanonical path")
    return p


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def commands_digest(request: SandboxExecutionRequest) -> str:
    return canonical_digest(
        {
            "baseline": [c.model_dump(mode="json") for c in request.baseline_checks],
            "focused": [c.model_dump(mode="json") for c in request.focused_checks],
            "broader": [c.model_dump(mode="json") for c in request.broader_checks],
            "expectation": request.baseline_expectation,
        }
    )


def check_commands(request: SandboxExecutionRequest) -> None:
    if commands_digest(request) != request.command_plan_sha256:
        raise ValueError("command plan digest mismatch")
    for c in request.baseline_checks + request.focused_checks + request.broader_checks:
        normalize_path(c.working_directory, allow_root=True)
        # Host-owned fixed templates; no arbitrary shell or free-form Python code.
        argv = c.argv
        if argv[0] != "python" or len(argv) < 4 or argv[1] != "-m":
            raise ValueError("unadmitted command executable")
        if argv[2] == "pytest":
            if argv[3:6] != ("-q", "-p", "no:cacheprovider") or len(argv) != 7:
                raise ValueError("unsupported pytest template")
            normalize_path(argv[6])
            if not argv[6].endswith(".py"):
                raise ValueError("pytest path must name a file")
        elif argv[2] == "compileall":
            if argv[3:] != ("-q", "-f", "."):
                raise ValueError("unsupported compileall template")
        else:
            raise ValueError("unsupported command template")
