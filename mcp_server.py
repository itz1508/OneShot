"""Single MCP stdio transport exposing existing, authorized OneShot operations.

No scanner implementation, task store or agent execution loop lives here.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from build import BuildPolicy, run_build
from scanner import admit_file, inspect_text
from task import TaskStore


@dataclass(frozen=True, slots=True)
class HostConfig:
    state_database: Path
    task_scope: str
    source_root: Path | None = None
    allowed_sources: frozenset[str] = frozenset()
    build_policy: BuildPolicy | None = None

    @classmethod
    def from_env(cls) -> HostConfig:
        """Trusted launch configuration, never client-provided MCP tool arguments."""
        database = os.environ.get("ONESHOT_STATE_DB")
        scope = os.environ.get("ONESHOT_TASK_SCOPE")
        if not database or not scope:
            raise RuntimeError("ONESHOT_STATE_DB and ONESHOT_TASK_SCOPE are required")
        source = os.environ.get("ONESHOT_SOURCE_ROOT")
        build_root = os.environ.get("ONESHOT_BUILD_ROOT")
        grants = frozenset(x.strip() for x in os.environ.get("ONESHOT_APPROVED_BUILDS", "").split(",") if x.strip())
        return cls(
            state_database=Path(database), task_scope=scope,
            source_root=Path(source) if source else None,
            allowed_sources=frozenset(x.strip() for x in os.environ.get("ONESHOT_ALLOWED_SOURCES", "").split(",") if x.strip()),
            build_policy=BuildPolicy(Path(build_root), grants) if build_root else None,
        )


def make_server(config: HostConfig) -> Any:
    """Register one set of tools on the official Python MCP SDK."""
    from mcp.server.fastmcp import FastMCP

    store = TaskStore(config.state_database, scope=config.task_scope)
    server = FastMCP("OneShot")

    @server.tool()
    def create_task(request_id: str, objective: str) -> dict[str, Any]:
        """Create or retrieve one task under the server's trusted thread scope."""
        return store.create_task(request_id=request_id, objective=objective)

    @server.tool()
    def get_task(task_id: str) -> dict[str, Any]:
        """Retrieve a task in the current authorized scope."""
        return store.get_task(task_id)

    @server.tool()
    def get_events(task_id: str) -> list[dict[str, Any]]:
        """Read the durable operation outcomes for a task."""
        return store.events(task_id)

    @server.tool()
    def record_result(task_id: str, expected_revision: int, result: dict[str, Any]) -> dict[str, Any]:
        """Validate and commit a host-produced Research or Plan result; never Build."""
        return store.save_host_result(task_id=task_id, expected_revision=expected_revision, value=result)

    @server.tool()
    def finish_task(task_id: str, expected_revision: int, result_type: str, result_id: str) -> dict[str, Any]:
        """Commit an existing verified result reference as final."""
        return store.finish_task(task_id=task_id, expected_revision=expected_revision,
                                 result_type=result_type, result_id=result_id)

    @server.tool()
    def get_final(task_id: str) -> dict[str, Any]:
        """Retrieve the exact final committed Research, Plan or Build JSON."""
        return store.get_final(task_id)

    @server.tool()
    def scan_sources(relative_name: str, start_byte: int = 0, max_bytes: int = 64000) -> dict[str, Any]:
        """Inspect one operator-allowlisted local source without cloud export."""
        if config.source_root is None or relative_name not in config.allowed_sources:
            raise ValueError("Source is not explicitly admitted")
        identifier = hashlib.sha256(relative_name.encode("utf-8")).hexdigest()
        admitted = admit_file(trusted_root=config.source_root, relative_name=relative_name,
                              source_id=identifier)
        return inspect_text(admitted, start_byte=start_byte, max_bytes=max_bytes)

    @server.tool()
    def execute_build(task_id: str, expected_revision: int, plan_id: str,
                      writes: list[dict[str, Any]]) -> dict[str, Any]:
        """Write only operator-granted Plan artifacts in the trusted build sandbox."""
        if config.build_policy is None:
            raise ValueError("Builder is disabled by host configuration")
        return run_build(store=store, policy=config.build_policy, task_id=task_id,
                         expected_revision=expected_revision, plan_id=plan_id, writes=writes)

    return server


def main() -> int:
    server = make_server(HostConfig.from_env())
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
