"""Deterministic stdio MCP server for connected Research transport tests."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from agent.contracts.research import Requirement, ResearchRecord
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, digest_model
from mvp.mcp_research import research_artifact_id

server = MCPServer("oneshot-research-test")


@server.tool(structured_output=True)
def oneshot_research(
    run_id: str,
    prompt: str,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, object]:
    """Return valid source-independent fixture evidence for the requested task."""
    del system_prompt, max_tokens, temperature
    task_id = json.loads(prompt)["task_id"]
    artifact = ResearchRecord(
        task_id=task_id,
        run_id=run_id,
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="submitted-request",
                original_wording="Investigate the repository",
                statement="Investigate the repository before implementation",
            ),
        ),
    )
    return {
        "stage": "research",
        "run_id": run_id,
        "task_id": task_id,
        "status": "completed",
        "artifact_id": research_artifact_id(task_id, run_id),
        "artifact_revision": 1,
        "artifact_digest": digest_model(artifact),
        "artifact": artifact.model_dump(mode="json"),
        "contract_id": "research_record",
        "contract_version": "1.0",
        "serializer_profile": SERIALIZER_PROFILE,
        "finish_reason": "stop",
        "usage": {"total_tokens": 0},
        "provider": "fixture",
        "model": "deterministic",
    }


if __name__ == "__main__":
    server.run("stdio")
