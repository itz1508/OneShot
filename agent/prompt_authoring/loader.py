"""Markdown prompt loader — frontmatter + body -> PromptSpec.

Reviewer directive (M2):
  - Markdown is AUTHORING SOURCE. It is NOT the runtime authority. The
    runtime authority is the accepted PromptDefinition snapshot (content
    digest + evaluation receipt + activation record).
  - Round-trip must be stable: `load_markdown_prompt(path)` applied twice
    to the same file produces PromptSpecs whose authored PromptDefinition
    carries an identical content_digest. The loader is therefore
    deterministic and digest-stability-preserving.
  - tool_permissions is a REQUEST, not a GRANT. The runner (M6) enforces
    the grant at the tool-invocation boundary.

File format (YAML frontmatter + Markdown body):

    ---
    prompt_id: <bare id>
    stage: <research | plan | build | discovery | handoff | provider_adapter>
    owner:
      kind: <authored owner kind>
      identifier: <free-form owner id>
    stage_specification: >
      <one line>
    task_class: <string>
    runtime_inputs:
      - name: USER_INTENT
        meaning: ...
        required: true
    required_capabilities:
      structured_outputs: true
    tool_permissions:
      - repository_read
    output_contract: <JSON Schema fragment>
    evaluation_rules:
      - ...
    recovery_behavior: ...
    stable_instructions:
      - (optional; if omitted the body becomes the sole stable instruction)
    ---

    <optional Markdown body — treated as a single stable_instructions
    entry when `stable_instructions` is not in the frontmatter.>

The loader REFUSES a file whose frontmatter is missing a required field or
declares a value outside the closed vocabulary (ToolPermission, Stage).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agent.prompt_authoring.types import (
    OwnerRef,
    PromptSpec,
    RuntimeInputSpec,
    Stage,
    ToolPermission,
)
from agent.providers.types import ProviderCapabilities


class MarkdownPromptError(RuntimeError):
    """A .md prompt source could not be loaded into a PromptSpec."""


_FRONTMATTER_DELIM = "---"


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Separate the YAML frontmatter from the body.

    Returns (frontmatter_dict, body_text). Raises MarkdownPromptError if
    the file does not open with ``---`` or the second delimiter is missing.
    """
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith(_FRONTMATTER_DELIM + "\n") and stripped != _FRONTMATTER_DELIM:
        raise MarkdownPromptError(
            "Markdown prompt source must open with a `---` YAML frontmatter block."
        )
    # Drop the opening delimiter line.
    rest = stripped[len(_FRONTMATTER_DELIM):].lstrip("\n")
    end = rest.find("\n" + _FRONTMATTER_DELIM)
    if end == -1:
        raise MarkdownPromptError(
            "Markdown prompt source must close its frontmatter with a `---` line."
        )
    front_text = rest[:end]
    body = rest[end + len(_FRONTMATTER_DELIM) + 1:].lstrip("\n")
    try:
        front = yaml.safe_load(front_text)
    except yaml.YAMLError as exc:
        raise MarkdownPromptError(f"YAML frontmatter parse error: {exc}") from exc
    if not isinstance(front, dict):
        raise MarkdownPromptError(
            "YAML frontmatter must deserialise to a mapping; "
            f"got {type(front).__name__}."
        )
    return front, body


def _require_key(d: dict[str, Any], name: str) -> Any:
    if name not in d:
        raise MarkdownPromptError(f"frontmatter is missing required key: {name!r}")
    return d[name]


def _parse_runtime_inputs(items: Any) -> list[RuntimeInputSpec]:
    if not isinstance(items, list):
        raise MarkdownPromptError(
            "runtime_inputs must be a YAML sequence of input specs."
        )
    out: list[RuntimeInputSpec] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise MarkdownPromptError(
                f"runtime_inputs[{i}] must be a mapping with name + meaning."
            )
        name = item.get("name")
        meaning = item.get("meaning")
        required = item.get("required", True)
        if not isinstance(name, str) or not name:
            raise MarkdownPromptError(f"runtime_inputs[{i}].name must be a non-empty string.")
        if not isinstance(meaning, str) or not meaning:
            raise MarkdownPromptError(
                f"runtime_inputs[{i}].meaning must be a non-empty string."
            )
        if not isinstance(required, bool):
            raise MarkdownPromptError(
                f"runtime_inputs[{i}].required must be a boolean."
            )
        out.append(RuntimeInputSpec(name=name, meaning=meaning, required=required))
    return out


def _parse_tool_permissions(items: Any) -> list[ToolPermission]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise MarkdownPromptError("tool_permissions must be a YAML sequence of strings.")
    out: list[ToolPermission] = []
    seen: set[str] = set()
    for i, raw in enumerate(items):
        if not isinstance(raw, str):
            raise MarkdownPromptError(
                f"tool_permissions[{i}] must be a string, got {type(raw).__name__}."
            )
        if raw in seen:
            raise MarkdownPromptError(
                f"tool_permissions[{i}] duplicates earlier entry {raw!r}."
            )
        seen.add(raw)
        try:
            out.append(ToolPermission(raw))
        except ValueError as exc:
            allowed = ", ".join(sorted(t.value for t in ToolPermission))
            raise MarkdownPromptError(
                f"tool_permissions[{i}] = {raw!r} is not in the closed vocabulary. "
                f"Allowed: {allowed}."
            ) from exc
    return out


def _parse_capabilities(d: Any) -> ProviderCapabilities:
    if d is None:
        return ProviderCapabilities()
    if not isinstance(d, dict):
        raise MarkdownPromptError(
            "required_capabilities must be a mapping of capability flags."
        )
    try:
        return ProviderCapabilities.model_validate(d)
    except Exception as exc:
        raise MarkdownPromptError(
            f"required_capabilities failed validation: {exc}"
        ) from exc


def load_markdown_prompt(path: str | Path) -> PromptSpec:
    """Load a .md prompt source into a validated PromptSpec.

    The returned PromptSpec is strictly validated by Pydantic; any error is
    wrapped in MarkdownPromptError so callers can distinguish source-level
    problems from downstream validation errors.
    """
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise MarkdownPromptError(f"cannot read {p}: {exc}") from exc

    front, body = _split_frontmatter(text)

    # Extract and build the PromptSpec fields one at a time so the error
    # messages name the offending key.
    prompt_id = _require_key(front, "prompt_id")
    stage_raw = _require_key(front, "stage")
    try:
        stage = Stage(stage_raw)
    except ValueError as exc:
        allowed = ", ".join(s.value for s in Stage)
        raise MarkdownPromptError(
            f"stage={stage_raw!r} is not a known Stage. Allowed: {allowed}."
        ) from exc

    owner_raw = _require_key(front, "owner")
    if not isinstance(owner_raw, dict):
        raise MarkdownPromptError("owner must be a mapping with kind + identifier.")
    try:
        owner = OwnerRef.model_validate(owner_raw)
    except Exception as exc:
        raise MarkdownPromptError(f"owner failed validation: {exc}") from exc

    stage_specification = _require_key(front, "stage_specification")
    task_class = _require_key(front, "task_class")
    runtime_inputs = _parse_runtime_inputs(_require_key(front, "runtime_inputs"))
    required_capabilities = _parse_capabilities(front.get("required_capabilities"))
    tool_permissions = _parse_tool_permissions(front.get("tool_permissions"))
    output_contract = _require_key(front, "output_contract")
    if not isinstance(output_contract, dict):
        raise MarkdownPromptError("output_contract must be a mapping (JSON Schema).")
    evaluation_rules = front.get("evaluation_rules") or []
    recovery_behavior = _require_key(front, "recovery_behavior")

    # stable_instructions: either declared in frontmatter OR taken from body.
    stable_instructions_raw = front.get("stable_instructions")
    if stable_instructions_raw is None:
        if not body.strip():
            raise MarkdownPromptError(
                "No stable_instructions provided: declare them in the frontmatter "
                "or write them in the Markdown body."
            )
        stable_instructions: list[str] = [body.strip()]
    else:
        if not isinstance(stable_instructions_raw, list):
            raise MarkdownPromptError(
                "stable_instructions in frontmatter must be a YAML sequence of strings."
            )
        if not all(isinstance(s, str) and s.strip() for s in stable_instructions_raw):
            raise MarkdownPromptError(
                "stable_instructions entries must be non-empty strings."
            )
        stable_instructions = list(stable_instructions_raw)

    fixture_refs = front.get("fixture_refs") or []

    try:
        return PromptSpec(
            prompt_id=prompt_id,
            stage=stage,
            owner=owner,
            stage_specification=stage_specification,
            task_class=task_class,
            runtime_inputs=runtime_inputs,
            output_contract=output_contract,
            required_capabilities=required_capabilities,
            stable_instructions=stable_instructions,
            evaluation_rules=list(evaluation_rules),
            recovery_behavior=recovery_behavior,
            fixture_refs=list(fixture_refs),
            tool_permissions=tool_permissions,
        )
    except Exception as exc:
        raise MarkdownPromptError(f"PromptSpec validation failed: {exc}") from exc


__all__ = [
    "MarkdownPromptError",
    "load_markdown_prompt",
]
