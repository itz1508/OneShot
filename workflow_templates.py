"""Read-only access to the single declarative workflow-template catalog.

The caller chooses an explicit template ID. This module does not infer intent,
select a workflow, create tasks, authorize Build, advance stages or execute agents.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


class TemplateRejected(ValueError):
    """Unknown template or invalid quality input."""


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    document = json.loads(resources.files("templates").joinpath("catalog.json").read_text(encoding="utf-8"))
    if document.get("schema_version") != "1.0.0" or not isinstance(document.get("templates"), dict):
        raise TemplateRejected("Unsupported or invalid template catalog")
    return document


@lru_cache(maxsize=1)
def _input_validator() -> Draft202012Validator:
    path = resources.files("templates").joinpath(_catalog()["input_contract"])
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def list_templates() -> tuple[str, ...]:
    """List known IDs without applying any selection logic."""
    return tuple(_catalog()["templates"])


def load_template(template_id: str) -> dict[str, str]:
    """Resolve one *explicit* template ID to its packaged instructions."""
    if not isinstance(template_id, str) or template_id not in _catalog()["templates"]:
        raise TemplateRejected("Unknown template ID")
    entry = _catalog()["templates"][template_id]
    return {
        "id": template_id,
        "instructions": resources.files("templates").joinpath(entry["instructions"]).read_text(encoding="utf-8"),
        "output_contract": entry["output_contract"],
        "applicability": entry["applicability"],
    }


def validate_quality_input(template_id: str, value: Any) -> dict[str, Any]:
    """Validate declared fields only; no truth/authorization or readiness inference."""
    load_template(template_id)
    if not isinstance(value, dict) or value.get("template_id") != template_id:
        raise TemplateRejected("Template identity mismatch")
    try:
        _input_validator().validate(value)
    except ValidationError as exc:
        location = "/".join(map(str, exc.absolute_path)) or "<root>"
        raise TemplateRejected(f"Invalid quality input at {location}: {exc.message}") from exc
    return value
