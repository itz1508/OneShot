"""Real MCP SDK client -> server stdio E2E. Requires installed 'mcp' dependency."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from task import TaskStore


def test_real_mcp_stdio_host_to_scanner_task_build(tmp_path: Path) -> None:
    pytest.importorskip("mcp", reason="Official MCP SDK unavailable in offline build environment")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    source = tmp_path / "sources"
    source.mkdir()
    (source / "rules.txt").write_text("limit=10 MB\nlimit=10 MB\n", encoding="utf-8")
    workspace = tmp_path / "sandbox"
    workspace.mkdir()
    db = tmp_path / "state.sqlite"
    store = TaskStore(db, scope="trusted-thread")
    task = store.create_task(request_id="mcp-e2e", objective="Review and create a safe synthetic artifact")
    plan = {"type": "plan", "id": "mcp-plan", "request_id": "mcp-e2e",
            "actions": [{"description": "Create inspected result", "target": "finding.txt"}]}
    task = store.save_host_result(task_id=task["id"], expected_revision=0, value=plan)
    env = {**os.environ,
           "ONESHOT_STATE_DB": str(db), "ONESHOT_TASK_SCOPE": "trusted-thread",
           "ONESHOT_SOURCE_ROOT": str(source), "ONESHOT_ALLOWED_SOURCES": "rules.txt",
           "ONESHOT_BUILD_ROOT": str(workspace),
           "ONESHOT_APPROVED_BUILDS": f"{task['id']}:mcp-plan"}

    async def main() -> None:
        server = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server"], env=env)
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                available = await session.list_tools()
                tools = {t.name for t in available.tools}
                assert {"create_task", "get_task", "record_result", "get_final", "scan_sources", "execute_build"} <= tools
                result = await session.call_tool("scan_sources", arguments={"relative_name": "rules.txt"})
                assert not result.isError
                assert "exact_repeated_line" in str(result.structuredContent or result.content)
                forbidden = await session.call_tool("scan_sources", arguments={"relative_name": "private.txt"})
                assert forbidden.isError
                executed = await session.call_tool("execute_build", arguments={
                    "task_id": task["id"], "expected_revision": task["revision"], "plan_id": "mcp-plan",
                    "writes": [{"name": "finding.txt", "content": "10 MB repeated rule\n"}],
                })
                assert not executed.isError, str(executed.content)
                assert "succeeded" in str(executed.structuredContent or executed.content)
    asyncio.run(main())
    assert (workspace / "artifacts" / "finding.txt").read_text() == "10 MB repeated rule\n"
    assert not store.pending_builds()
