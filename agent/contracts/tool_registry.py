"""Host-pinned tool catalog contract. No command execution in this module."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, model_validator

from agent.contracts.common import ContractModel, Sha256

ToolId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
StageId = Literal[
    "research",
    "audit_discovery",
    "planning",
    "fixture_validation",
    "build",
    "build_validation",
]
_PLACEHOLDER = re.compile(r"^\{([a-z][a-z0-9_-]*)\}$")
_DRIVE = re.compile(r"^[A-Za-z]:")


class ToolEffect(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"
    EXTERNAL = "external"


class ParamKind(StrEnum):
    LITERAL = "literal"
    CHOICE = "choice"
    PATH = "path"
    WORKSPACE_PATH = "workspace_path"


def safe_relative_path(value: str) -> str:
    """Reject ambiguous, absolute, traversal, and option-like path arguments."""
    if (
        not value
        or value.startswith(("-", "/", "\\"))
        or "\x00" in value
        or _DRIVE.match(value)
        or "\\" in value
        or any(ord(ch) < 32 for ch in value)
    ):
        raise ValueError("unsafe relative workspace path")
    parts = PurePosixPath(value).parts
    if not parts or any(part in ("..", ".") for part in value.split("/")):
        raise ValueError("unsafe relative workspace path")
    return str(PurePosixPath(*parts))


class ToolParam(ContractModel):
    name: ToolId
    kind: ParamKind
    choices: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_choices(self) -> ToolParam:
        if (self.kind == ParamKind.CHOICE) != bool(self.choices):
            raise ValueError("choices required only for choice params")
        if len(self.choices) != len(set(self.choices)):
            raise ValueError("duplicate choices")
        return self


class SandboxProfile(ContractModel):
    """Host-provisioned profile identity; image must be pinned by digest."""

    profile_id: ToolId
    image_ref: str = Field(pattern=r"^.+@sha256:[a-f0-9]{64}$")
    network_allowed: bool = False
    allowed_effects: tuple[ToolEffect, ...] = (ToolEffect.READ_ONLY,)


class ToolSpec(ContractModel):
    tool_id: ToolId
    version: str = Field(min_length=1)
    executable_digest: Sha256
    argv_template: tuple[str, ...] = Field(min_length=1)
    params: tuple[ToolParam, ...] = ()
    allowed_stages: tuple[StageId, ...] = Field(min_length=1)
    effect: ToolEffect
    network: bool = False
    timeout_seconds: int = Field(gt=0, le=3600)
    max_output_bytes: int = Field(gt=0, le=10_000_000)
    sandbox_profile_id: ToolId

    @model_validator(mode="after")
    def validate_template(self) -> ToolSpec:
        if not self.argv_template[0] or "{" in self.argv_template[0]:
            raise ValueError("executable must be a fixed token")
        names = [p.name for p in self.params]
        if len(set(names)) != len(names):
            raise ValueError("duplicate tool parameter")
        placeholders: list[str] = []
        for token in self.argv_template[1:]:
            if "\x00" in token or not token:
                raise ValueError("invalid argv token")
            if "{" in token or "}" in token:
                match = _PLACEHOLDER.fullmatch(token)
                if match is None:
                    raise ValueError("parameters must occupy a complete argv token")
                placeholders.append(match.group(1))
        if len(placeholders) != len(set(placeholders)) or set(placeholders) != set(names):
            raise ValueError("argv placeholders must match parameters exactly")
        if self.network and self.effect is not ToolEffect.EXTERNAL:
            raise ValueError("network requires external effect classification")
        if len(set(self.allowed_stages)) != len(self.allowed_stages):
            raise ValueError("duplicate allowed stage")
        return self


class ToolRegistrySnapshot(ContractModel):
    registry_version: str = Field(min_length=1)
    tools: tuple[ToolSpec, ...] = Field(min_length=1)
    sandbox_profiles: tuple[SandboxProfile, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> ToolRegistrySnapshot:
        ids = [spec.tool_id for spec in self.tools]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate tool id")
        profiles = {profile.profile_id: profile for profile in self.sandbox_profiles}
        if len(profiles) != len(self.sandbox_profiles):
            raise ValueError("duplicate sandbox profile id")
        for tool in self.tools:
            profile = profiles.get(tool.sandbox_profile_id)
            if profile is None:
                raise ValueError(f"unknown sandbox profile for {tool.tool_id}")
            if tool.effect not in profile.allowed_effects:
                raise ValueError(f"effect not permitted by sandbox profile: {tool.tool_id}")
            if tool.network and not profile.network_allowed:
                raise ValueError(f"network not permitted by sandbox profile: {tool.tool_id}")
        return self


class ToolInvocation(ContractModel):
    tool_id: ToolId
    args: dict[str, str] = Field(default_factory=dict)


class ResolvedCommand(ContractModel):
    tool_id: ToolId
    tool_version: str
    argv: tuple[str, ...] = Field(min_length=1)
    executable_digest: Sha256
    effect: ToolEffect
    network: bool
    timeout_seconds: int
    max_output_bytes: int
    sandbox_profile_id: ToolId
    image_ref: str


def resolve_invocation(
    snapshot: ToolRegistrySnapshot,
    invocation: ToolInvocation,
    stage: StageId,
    affected_paths: frozenset[str],
) -> ResolvedCommand:
    """Resolve only host-registered argv; NEVER execute here."""
    spec = next((tool for tool in snapshot.tools if tool.tool_id == invocation.tool_id), None)
    if spec is None:
        raise ValueError(f"unregistered tool: {invocation.tool_id}")
    if stage not in spec.allowed_stages:
        raise ValueError(f"tool not authorized for stage: {stage}")
    params = {p.name: p for p in spec.params}
    if set(invocation.args) != set(params):
        raise ValueError("invocation arguments do not match declared params")
    approved = {safe_relative_path(path) for path in affected_paths}
    for name, value in invocation.args.items():
        if not isinstance(value, str) or not value or "\x00" in value or len(value) > 1024:
            raise ValueError(f"invalid value for {name}")
        param = params[name]
        if param.kind == ParamKind.LITERAL:
            if value.startswith("-") or any(ord(ch) < 32 for ch in value):
                raise ValueError(f"option/control injection for {name}")
        elif param.kind == ParamKind.CHOICE:
            if value not in param.choices:
                raise ValueError(f"unregistered choice for {name}")
        elif param.kind == ParamKind.PATH:
            if safe_relative_path(value) not in approved:
                raise ValueError(f"path not admitted for {name}")
        elif param.kind == ParamKind.WORKSPACE_PATH:
            safe_relative_path(value)
    argv = tuple(
        invocation.args[token[1:-1]] if _PLACEHOLDER.fullmatch(token) else token for token in spec.argv_template
    )
    profile = next(p for p in snapshot.sandbox_profiles if p.profile_id == spec.sandbox_profile_id)
    return ResolvedCommand(
        tool_id=spec.tool_id,
        tool_version=spec.version,
        argv=argv,
        executable_digest=spec.executable_digest,
        effect=spec.effect,
        network=spec.network,
        timeout_seconds=spec.timeout_seconds,
        max_output_bytes=spec.max_output_bytes,
        sandbox_profile_id=profile.profile_id,
        image_ref=profile.image_ref,
    )
