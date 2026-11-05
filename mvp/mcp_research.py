"""Validated MCP Research bridge. MCP computes; OneShot host persists and authorizes.

MCP is an optional MVP integration dependency. Only a configured, host-owned
transport can run. Neither tool metadata nor a claimed digest confers authority.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.contracts.research import ResearchRecord
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, digest_dict, digest_model
from agent.runtime.providers.base import (
    CapabilityDescriptor,
    ProviderError,
    ProviderRequest,
    ProviderResult,
)
from agent.runtime.providers.registry import ProviderRegistry
from mvp.connector_store import connector_store

_TASK_ID = re.compile(r"^[a-f0-9]{32}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_MCP_CHILD_ENV = frozenset(
    {
        "PATH",
        "HOME",
        "USERPROFILE",
        "SYSTEMROOT",
        "WINDIR",
        "APPDATA",
        "LOCALAPPDATA",
        "TMP",
        "TEMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "PYTHONPATH",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "MODEL_API_BASE_URL",
        "MODEL_API_MODEL",
        "MODEL_API_KEY",
        "MCP_WORKSPACE_ROOT",
        "MCP_TRUSTED_ANCESTRY",
    }
)


def mcp_child_environment(state_root: Path | None = None) -> dict[str, str]:
    """Pass only process essentials and the configured MCP model/workspace inputs."""
    child_env = {name: value for name, value in os.environ.items() if name.upper() in _MCP_CHILD_ENV}
    child_env["MCP_SERVER_MODE"] = "oneshot"
    child_env.update(connector_store(state_root).export_model_environment())
    return child_env


def research_artifact_id(task_id: str, run_id: str) -> str:
    """Derive the artifact identity required by the Research MCP contract."""
    identity = digest_dict({"run_id": run_id, "stage": "research", "task_id": task_id})
    return f"research-{identity[:32]}"


def mcp_transport_config(state_root: Path | None = None) -> tuple[str, str, list[str], str | None]:
    """Resolve the active MCP transport from env or connector state."""
    url = os.environ.get("ONESHOT_MCP_URL", "").strip()
    command = os.environ.get("ONESHOT_MCP_COMMAND", "").strip()
    if bool(url) == bool(command):
        resolved = connector_store(state_root).mcp_transport_config()
        return resolved
    if url:
        return url, "", [], connector_store(state_root).load_secrets().mcp_bearer_token or None
    try:
        args = json.loads(os.environ.get("ONESHOT_MCP_ARGS_JSON", "[]"))
    except ValueError as exc:
        raise ProviderError("invalid ONESHOT_MCP_ARGS_JSON") from exc
    if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
        raise ProviderError("MCP stdio arguments must be a JSON array of strings")
    return "", command, args, None


class ResearchMCPOutput(BaseModel):
    """Research MCP envelope; artifact bytes are authoritative only after validation."""

    stage: str
    run_id: str
    task_id: str
    status: str
    artifact_id: str = Field(min_length=1)
    artifact_revision: int = Field(ge=1)
    artifact_digest: str
    artifact: dict[str, Any]
    contract_id: str
    contract_version: str
    serializer_profile: str
    finish_reason: str = "stop"
    usage: dict[str, Any] = Field(default_factory=dict)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def check_protocol(self) -> ResearchMCPOutput:
        if (
            self.stage != "research"
            or self.status != "completed"
            or self.contract_id != "research_record"
            or self.contract_version != "1.0"
            or self.serializer_profile != SERIALIZER_PROFILE
            or self.finish_reason != "stop"
            or _DIGEST.fullmatch(self.artifact_digest) is None
        ):
            raise ValueError("invalid Research MCP envelope")
        return self


def _tool_json(response: Any) -> dict[str, Any]:
    """Accept exactly one JSON text content result; fail closed on tool errors."""
    if response.is_error:
        detail = response.structured_content
        code = detail.get("error_class") if isinstance(detail, dict) else None
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,80}", code):
            code = "MCP_TOOL_ERROR"
        raise ProviderError(f"MCP Research tool failed: {code}")
    if len(response.content) != 1 or getattr(response.content[0], "type", None) != "text":
        raise ProviderError("MCP Research must return one JSON text block")
    try:
        parsed = json.loads(response.content[0].text)
    except (ValueError, TypeError) as exc:
        raise ProviderError("MCP Research returned invalid JSON") from exc
    structured = response.structured_content
    if not isinstance(parsed, dict) or not isinstance(structured, dict) or structured != parsed:
        raise ProviderError("MCP Research text/structured response mismatch")
    return structured


async def _invoke_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    """One negotiated MCP session over trusted local stdio or configured HTTP."""
    try:
        from mcp import Client, StdioServerParameters  # type: ignore[import-not-found]  # optional MVP SDK
    except ImportError as exc:
        raise ProviderError("MCP Python SDK missing; sync the mvp extra") from exc

    url, command, args, bearer_token = mcp_transport_config()
    if url:
        transport: Any = url
        if bearer_token:
            for module_name, class_name in (
                ("mcp.client.streamable_http", "StreamableHTTPTransport"),
                ("mcp.client.http", "HTTPTransport"),
                ("mcp.client.sse", "SSEClientTransport"),
            ):
                try:
                    module = __import__(module_name, fromlist=[class_name])
                    transport_cls = getattr(module, class_name)
                except Exception:
                    continue
                for kwargs in (
                    {"url": url, "headers": {"Authorization": f"Bearer {bearer_token}"}},
                    {"url": url, "authorization": bearer_token},
                    {"url": url},
                ):
                    try:
                        transport = transport_cls(**kwargs)
                        break
                    except TypeError:
                        continue
                else:
                    continue
                break
    else:
        transport = StdioServerParameters(command=command, args=args, env=mcp_child_environment())
    try:
        async with Client(transport, read_timeout_seconds=60) as session:
            names: list[str] = []
            cursor: str | None = None
            for _ in range(16):
                page = await session.list_tools(cursor=cursor)
                names.extend(tool.name for tool in page.tools)
                cursor = page.next_cursor
                if cursor is None:
                    break
            else:
                raise ProviderError("MCP tool pagination exceeded limit")
            if names != ["oneshot_research"]:
                raise ProviderError("MCP server must advertise only oneshot_research in OneShot mode")
            response = await session.call_tool("oneshot_research", arguments)
            return _tool_json(response)
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"MCP Research connection or call failed: {type(exc).__name__}") from exc


class MCPResearchAdapter:
    """Class-based ProviderRegistry adapter; no host-state or receipt writes."""

    def declared_capabilities(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            structured_outputs=True,
            streaming=False,
            batch=False,
            prompt_caching=False,
            strict_tool_schemas=True,
        )

    def generate(self, request: ProviderRequest) -> ProviderResult:
        try:
            prompt = json.loads(request.prompt)
            if not isinstance(prompt, dict) or set(prompt) != {"task_id", "stage_payload"}:
                raise ValueError("Research prompt must contain task_id and stage_payload")
            task_id = prompt["task_id"]
            if not isinstance(task_id, str) or _TASK_ID.fullmatch(task_id) is None:
                raise ValueError("invalid Research task identity")
            if not isinstance(prompt["stage_payload"], dict) or not prompt["stage_payload"]:
                raise ValueError("Research stage_payload must be a nonempty object")
            if request.run_id != f"run-{task_id}":
                raise ValueError("Research run identity mismatch")
        except (TypeError, ValueError) as exc:
            raise ProviderError("invalid host Research request") from exc

        args = {
            "run_id": request.run_id,
            "prompt": request.prompt,
            "system_prompt": request.system_prompt,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        try:
            reply = asyncio.run(_invoke_tool(args))
            envelope = ResearchMCPOutput.model_validate(reply)
            if envelope.task_id != task_id or envelope.run_id != request.run_id:
                raise ProviderError("MCP Research identity mismatch")
            if envelope.artifact_id != research_artifact_id(task_id, request.run_id) or envelope.artifact_revision != 1:
                raise ProviderError("MCP Research artifact ID/revision mismatch")
            artifact = ResearchRecord.model_validate(envelope.artifact)
            if artifact.task_id != task_id or artifact.run_id != request.run_id or artifact.stage_revision != 1:
                raise ProviderError("MCP Research artifact identity mismatch")
            if digest_model(artifact) != envelope.artifact_digest:
                raise ProviderError("MCP Research artifact digest mismatch")
        except ProviderError:
            raise
        except (ValueError, TypeError) as exc:
            raise ProviderError("MCP Research response contract invalid") from exc
        return ProviderResult(
            content=envelope.model_dump_json(),
            tool_calls=(),
            finish_reason=envelope.finish_reason,
            usage=envelope.usage,
            provider=envelope.provider,
            model=envelope.model,
        )


def register_mcp_research(registry: ProviderRegistry) -> None:
    """Register only the implemented Research adapter; do not change the default."""
    registry.register("mcp_research", MCPResearchAdapter)
