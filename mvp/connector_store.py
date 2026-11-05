"""Host-owned connector settings, secret storage, and connection probes.

The frontend only receives non-sensitive connector status. API keys and bearer
secrets stay on the host in runtime state owned by the MVP process.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.runtime.providers.base import ProviderError

STATE_FILE = "connector_state.json"
SECRETS_FILE = "connector_secrets.json"


class ConnectorError(RuntimeError):
    """Raised when connector configuration or transport validation fails."""


class MCPAuthType(StrEnum):
    NONE = "none"
    BEARER = "bearer"


class MCPToolInfo(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""

    model_config = ConfigDict(extra="forbid")


class MCPConnectionState(BaseModel):
    url: str = ""
    auth_type: MCPAuthType = MCPAuthType.NONE
    transport: str = "http"
    status: str = "disconnected"
    error: str = ""
    connected_at: str = ""
    tools: list[MCPToolInfo] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ModelConnectionState(BaseModel):
    api_base_url: str = ""
    model_id: str = ""
    status: str = "disconnected"
    error: str = ""
    provider_response: str = ""
    connected_at: str = ""

    model_config = ConfigDict(extra="forbid")


class ConnectorState(BaseModel):
    mcp: MCPConnectionState = Field(default_factory=MCPConnectionState)
    model: ModelConnectionState = Field(default_factory=ModelConnectionState)

    model_config = ConfigDict(extra="forbid")


class MCPConnectionRequest(BaseModel):
    url: str = Field(min_length=1)
    auth_type: MCPAuthType = MCPAuthType.NONE
    bearer_token: str = ""

    model_config = ConfigDict(extra="forbid")


class ModelConnectionRequest(BaseModel):
    api_base_url: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    api_key: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _trim(self) -> ModelConnectionRequest:
        self.api_base_url = self.api_base_url.strip()
        self.model_id = self.model_id.strip()
        self.api_key = self.api_key.strip()
        return self


@dataclass(frozen=True)
class ConnectorSecrets:
    mcp_bearer_token: str = ""
    model_api_key: str = ""


class ConnectorStore:
    """Persist and retrieve host-owned connector settings."""

    def __init__(self, state_root: Path) -> None:
        self.root = state_root
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / STATE_FILE
        self.secrets_path = self.root / SECRETS_FILE

    def snapshot(self) -> dict[str, object]:
        state = self.load_state()
        secrets = self.load_secrets()
        return {
            "mcp": {
                **state.mcp.model_dump(mode="json"),
                "has_bearer_token": bool(secrets.mcp_bearer_token),
            },
            "model": {
                **state.model.model_dump(mode="json"),
                "has_api_key": bool(secrets.model_api_key),
            },
        }

    def load_state(self) -> ConnectorState:
        if not self.state_path.exists():
            return ConnectorState()
        raw = json.loads(self.state_path.read_text())
        return ConnectorState.model_validate(raw)

    def save_state(self, state: ConnectorState) -> None:
        self._write_json(self.state_path, state.model_dump(mode="json"), private=False)

    def load_secrets(self) -> ConnectorSecrets:
        if not self.secrets_path.exists():
            return ConnectorSecrets()
        raw = json.loads(self.secrets_path.read_text())
        return ConnectorSecrets(
            mcp_bearer_token=str(raw.get("mcp_bearer_token", "") or ""),
            model_api_key=str(raw.get("model_api_key", "") or ""),
        )

    def save_secrets(self, *, mcp_bearer_token: str | None = None, model_api_key: str | None = None) -> None:
        current = self.load_secrets()
        payload = {
            "mcp_bearer_token": current.mcp_bearer_token if mcp_bearer_token is None else mcp_bearer_token,
            "model_api_key": current.model_api_key if model_api_key is None else model_api_key,
        }
        self._write_json(self.secrets_path, payload, private=True)

    def clear_mcp(self) -> None:
        state = self.load_state()
        state.mcp = MCPConnectionState()
        self.save_state(state)
        self.save_secrets(mcp_bearer_token="")

    def clear_model(self) -> None:
        state = self.load_state()
        state.model = ModelConnectionState()
        self.save_state(state)
        self.save_secrets(model_api_key="")

    def set_mcp_state(self, state: MCPConnectionState, bearer_token: str | None = None) -> None:
        connector_state = self.load_state()
        connector_state.mcp = state
        self.save_state(connector_state)
        if bearer_token is not None:
            self.save_secrets(mcp_bearer_token=bearer_token)

    def set_model_state(self, state: ModelConnectionState, api_key: str | None = None) -> None:
        connector_state = self.load_state()
        connector_state.model = state
        self.save_state(connector_state)
        if api_key is not None:
            self.save_secrets(model_api_key=api_key)

    def export_model_environment(self) -> dict[str, str]:
        state = self.load_state().model
        secrets = self.load_secrets()
        env: dict[str, str] = {}
        if state.api_base_url:
            env["MODEL_API_BASE_URL"] = state.api_base_url
        if state.model_id:
            env["MODEL_API_MODEL"] = state.model_id
        if secrets.model_api_key:
            env["MODEL_API_KEY"] = secrets.model_api_key
        return env

    def mcp_transport_config(self) -> tuple[str, str, list[str], str | None]:
        state = self.load_state().mcp
        secrets = self.load_secrets()
        if state.url:
            return state.url, "", [], secrets.mcp_bearer_token or None
        command = os.environ.get("ONESHOT_MCP_COMMAND", "").strip()
        if not command:
            raise ProviderError("configure exactly one of ONESHOT_MCP_URL or ONESHOT_MCP_COMMAND")
        try:
            args = json.loads(os.environ.get("ONESHOT_MCP_ARGS_JSON", "[]"))
        except ValueError as exc:
            raise ProviderError("invalid ONESHOT_MCP_ARGS_JSON") from exc
        if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
            raise ProviderError("MCP stdio arguments must be a JSON array of strings")
        return "", command, args, None

    def _write_json(self, path: Path, payload: dict[str, object], *, private: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.replace(tmp, path)
        if private:
            with contextlib.suppress(OSError):
                path.chmod(0o600)


def connector_state_root(state_root: Path | None = None) -> Path:
    if state_root is not None:
        return Path(state_root)
    return Path(os.environ.get("ONESHOT_STATE_ROOT", "./.oneshot-state"))


def connector_store(state_root: Path | None = None) -> ConnectorStore:
    return ConnectorStore(connector_state_root(state_root))


def _validate_url_shape(url: str) -> tuple[str, str, int | None]:
    cleaned = url.strip()
    if not cleaned:
        raise ConnectorError("URL is required")
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"}:
        raise ConnectorError("URL must use http or https")
    if not parsed.hostname:
        raise ConnectorError("URL must include a hostname")
    if parsed.username or parsed.password:
        raise ConnectorError("URL must not contain embedded credentials")
    if parsed.fragment:
        raise ConnectorError("URL must not contain a fragment")
    if parsed.path and parsed.path != "/" and parsed.path.endswith("//"):
        raise ConnectorError("URL path is invalid")
    port = parsed.port
    return parsed.hostname, parsed.scheme, port


def _resolve_public_addresses(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        try:
            infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ConnectorError("unable to resolve host") from exc
        for info in infos:
            address = info[4][0]
            try:
                addresses.append(ipaddress.ip_address(address))
            except ValueError:
                continue
        if not addresses:
            raise ConnectorError("unable to resolve host") from None
        return addresses
    return [ip]


def validate_remote_url(url: str) -> str:
    hostname, scheme, port = _validate_url_shape(url)
    addresses = _resolve_public_addresses(hostname)
    for address in addresses:
        if address.is_loopback:
            continue
        if (
            address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ConnectorError("URL resolves to a private or unsupported network address")
    if port is not None and not (1 <= port <= 65535):
        raise ConnectorError("URL port is invalid")
    if scheme == "https" and hostname == "localhost":
        raise ConnectorError("localhost is not allowed for https MCP URLs")
    return url.strip()


def _normalize_tools(items: list[Any]) -> list[MCPToolInfo]:
    tools: list[MCPToolInfo] = []
    for item in items:
        if isinstance(item, MCPToolInfo):
            tools.append(item)
            continue
        if isinstance(item, dict):
            tools.append(MCPToolInfo.model_validate(item))
            continue
        tools.append(MCPToolInfo(name=getattr(item, "name", ""), description=getattr(item, "description", "") or ""))
    return tools


async def _mcp_session(url: str, bearer_token: str | None) -> Any:
    try:
        from mcp import Client  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProviderError("MCP Python SDK missing; sync the mvp extra") from exc

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
        transport = url
    try:
        return Client(transport, read_timeout_seconds=60)
    except TypeError:
        return Client(transport)


async def discover_mcp_tools(url: str, bearer_token: str | None = None) -> list[MCPToolInfo]:
    """Open a real MCP session and collect the advertised tools."""
    session_factory = await _mcp_session(url, bearer_token)
    tools: list[MCPToolInfo] = []
    async with session_factory as session:
        cursor: str | None = None
        for _ in range(16):
            page = await session.list_tools(cursor=cursor)
            for tool in page.tools:
                tools.append(MCPToolInfo(name=tool.name, description=getattr(tool, "description", "") or ""))
            cursor = page.next_cursor
            if cursor is None:
                break
        else:
            raise ProviderError("MCP tool pagination exceeded limit")
    return tools


def discover_mcp_tools_sync(url: str, bearer_token: str | None = None) -> list[MCPToolInfo]:
    return asyncio.run(discover_mcp_tools(url, bearer_token))


async def test_model_provider(
    api_base_url: str, model_id: str, api_key: str, *, prompt: str = "Return exactly: provider-ready"
) -> str:
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ProviderError("OpenAI SDK missing") from exc
    kwargs: dict[str, Any] = {"api_key": api_key, "timeout": 60, "max_retries": 0}
    if api_base_url:
        kwargs["base_url"] = api_base_url
    client = OpenAI(**kwargs)
    response = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16,
    )
    content = response.choices[0].message.content
    if not content:
        raise ProviderError("provider returned no response")
    return content


def test_model_provider_sync(api_base_url: str, model_id: str, api_key: str) -> str:
    return asyncio.run(test_model_provider(api_base_url, model_id, api_key))


def connect_mcp(
    *,
    state_root: Path | None,
    url: str,
    auth_type: MCPAuthType,
    bearer_token: str = "",
    persist: bool = True,
) -> dict[str, object]:
    cleaned_url = validate_remote_url(url)
    if auth_type is MCPAuthType.BEARER and not bearer_token.strip():
        raise ConnectorError("bearer token is required for bearer authentication")
    tools = _normalize_tools(discover_mcp_tools_sync(cleaned_url, bearer_token.strip() or None))
    state = MCPConnectionState(
        url=cleaned_url,
        auth_type=auth_type,
        transport="http",
        status="connected",
        error="",
        connected_at="",
        tools=tools,
    )
    if persist:
        connector_store(state_root).set_mcp_state(state, bearer_token.strip() or None)
    return {
        "status": state.status,
        "transport": state.transport,
        "url": state.url,
        "auth_type": state.auth_type.value,
        "error": state.error,
        "connected_at": state.connected_at,
        "tool_count": len(tools),
        "tools": [tool.model_dump(mode="json") for tool in tools],
    }


def disconnect_mcp(state_root: Path | None) -> dict[str, object]:
    connector_store(state_root).clear_mcp()
    return {"status": "disconnected"}


def test_mcp_connection(
    *,
    state_root: Path | None,
    url: str | None = None,
    auth_type: MCPAuthType | None = None,
    bearer_token: str | None = None,
) -> dict[str, object]:
    store = connector_store(state_root)
    state = store.load_state().mcp
    secrets = store.load_secrets()
    resolved_url = validate_remote_url(url or state.url)
    resolved_auth = auth_type or state.auth_type
    token = bearer_token if bearer_token is not None else secrets.mcp_bearer_token
    if resolved_auth is MCPAuthType.BEARER and not token.strip():
        raise ConnectorError("bearer token is required for bearer authentication")
    tools = _normalize_tools(discover_mcp_tools_sync(resolved_url, token.strip() or None))
    state.url = resolved_url
    state.auth_type = resolved_auth
    state.tools = tools
    state.status = "connected"
    state.error = ""
    store.save_state(ConnectorState(mcp=state, model=store.load_state().model))
    if resolved_auth is MCPAuthType.BEARER and bearer_token is not None:
        store.save_secrets(mcp_bearer_token=token.strip())
    return {
        "status": state.status,
        "transport": state.transport,
        "url": state.url,
        "auth_type": state.auth_type.value,
        "error": state.error,
        "tool_count": len(tools),
        "tools": [tool.model_dump(mode="json") for tool in tools],
    }


def save_model_connection(
    *,
    state_root: Path | None,
    api_base_url: str,
    model_id: str,
    api_key: str,
    persist: bool = True,
) -> dict[str, object]:
    base_url = api_base_url.strip()
    model = model_id.strip()
    if not model:
        raise ConnectorError("model id is required")
    if base_url:
        validate_remote_url(base_url)
    state = ModelConnectionState(
        api_base_url=base_url,
        model_id=model,
        status="saved",
        error="",
        provider_response="",
        connected_at="",
    )
    if persist:
        connector_store(state_root).set_model_state(state, api_key.strip())
    return {
        "status": state.status,
        "api_base_url": state.api_base_url,
        "model_id": state.model_id,
        "provider_response": state.provider_response,
        "error": state.error,
    }


def test_model_connection(
    *,
    state_root: Path | None,
    api_base_url: str | None = None,
    model_id: str | None = None,
    api_key: str | None = None,
) -> dict[str, object]:
    store = connector_store(state_root)
    state = store.load_state().model
    secrets = store.load_secrets()
    base_url = (api_base_url or state.api_base_url).strip()
    model = (model_id or state.model_id).strip()
    key = (api_key if api_key is not None else secrets.model_api_key).strip()
    if not model:
        raise ConnectorError("model id is required")
    if not key:
        raise ConnectorError("api key is required")
    if base_url:
        validate_remote_url(base_url)
    response = test_model_provider_sync(base_url, model, key)
    state.api_base_url = base_url
    state.model_id = model
    state.status = "connected"
    state.error = ""
    state.provider_response = response
    store.save_state(ConnectorState(mcp=store.load_state().mcp, model=state))
    if api_key is not None:
        store.save_secrets(model_api_key=key)
    return {
        "status": state.status,
        "api_base_url": state.api_base_url,
        "model_id": state.model_id,
        "provider_response": response,
        "error": state.error,
    }
