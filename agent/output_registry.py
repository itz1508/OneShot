"""OneShot Adaptive Output Schema Registry.

Selects the correct JSON output contract based on task context, workflow stage,
available material, and requested output. Serializes records to JSON without
repeating agent evaluations or executing tools.

Responsibilities:
    - Register and look up output schema descriptors
    - Auto-select applicable output(s) from selection context
    - Serialize data to JSON using the selected schema
    - Lightweight JSON Schema structural validation

Does NOT:
    - Duplicate contract or invariant validation
    - Execute tools or repeat agent evaluations
    - Replace the OneShotController or TaskManager
    - Create a second scanner or gap-fix service

Usage::

    from agent.output_registry import SchemaRegistry, SelectionContext

    registry = SchemaRegistry()
    ctx = SelectionContext(stage="research", available_material={"research_record": True})
    result = registry.select(ctx)
    for desc in result.selected:
        serialized = registry.serialize(desc.name, research_record_dict)
        print(serialized.json_str)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class OutputSchemaDescriptor:
    """Metadata for a registered output schema."""

    name: str  # e.g. "output_research"
    schema_file: str  # filename inside schemas dir
    stage: str  # "research" | "plan" | "build" | "any"
    contract_ref: str  # source contract file
    model_ref: str | None = None  # Pydantic model reference, if any
    description: str = ""
    priority: int = 0  # higher = preferred when ambiguous


@dataclass
class SelectionContext:
    """Context used by SchemaRegistry.select() to pick applicable outputs."""

    stage: str | None = None
    requested_output: str | None = None
    available_material: dict[str, bool] = field(default_factory=dict)
    task_id: str | None = None


@dataclass
class SelectionResult:
    """Result of schema selection."""

    selected: list[OutputSchemaDescriptor] = field(default_factory=list)
    ambiguous: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class SerializationResult:
    """Result of JSON serialization for a single output."""

    output_name: str
    data: dict | None = None
    json_str: str | None = None
    errors: list[str] = field(default_factory=list)
    schema: OutputSchemaDescriptor | None = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class SchemaRegistry:
    """Adaptive output schema registry.

    Selects output contracts and serializes to JSON.  Does not validate
    invariants, execute tools, or replace the ``OneShotController``.
    """

    # Maps output names to the ``available_material`` keys that must be True
    # for the output to be selectable when material filtering is active.
    _MATERIAL_KEYS: dict[str, str] = {
        "output_research": "research_record",
        "output_gap_analysis": "gap_analysis",
        "output_built": "build_record",
    }

    def __init__(self, schemas_dir: Path | None = None):
        self._schemas: dict[str, OutputSchemaDescriptor] = {}
        self._schemas_dir = schemas_dir or Path(__file__).resolve().parent / "schemas"
        self._register_defaults()

    # -- registration ------------------------------------------------------

    def _register_defaults(self) -> None:
        """Register the three built-in output schemas."""
        defaults = [
            OutputSchemaDescriptor(
                name="output_research",
                schema_file="output_research.json",
                stage="research",
                contract_ref="agent/contracts/research.yaml",
                model_ref="agent/contracts/models.py:ResearchRecord",
                description="Research findings, evidence, and review output",
                priority=10,
            ),
            OutputSchemaDescriptor(
                name="output_gap_analysis",
                schema_file="output_gap_analysis.json",
                stage="plan",
                contract_ref="agent/contracts/plan.yaml:gap_analysis",
                model_ref="agent/contracts/models.py:GapAnalysis",
                description="Gap analysis findings from Scanner comparison",
                priority=10,
            ),
            OutputSchemaDescriptor(
                name="output_built",
                schema_file="output_built.json",
                stage="build",
                contract_ref="agent/contracts/build.yaml",
                model_ref="agent/contracts/models.py:BuildRecord",
                description="Build execution results, E2E validation, and outcome",
                priority=10,
            ),
        ]
        for desc in defaults:
            self.register(desc)

    def register(self, desc: OutputSchemaDescriptor) -> None:
        """Register an output schema. Re-registering the same name is idempotent."""
        if desc.name in self._schemas:
            return  # idempotent re-registration
        self._schemas[desc.name] = desc

    # -- lookup ------------------------------------------------------------

    def get(self, name: str) -> OutputSchemaDescriptor | None:
        """Return a registered schema by name, or ``None``."""
        return self._schemas.get(name)

    def list_schemas(self) -> list[OutputSchemaDescriptor]:
        """List all registered schemas."""
        return list(self._schemas.values())

    # -- selection ---------------------------------------------------------

    def select(self, context: SelectionContext) -> SelectionResult:
        """Select applicable output schema(s) from context.

        Logic (in order):
          1. If ``requested_output`` is set, return only that schema.
          2. Filter by ``stage`` (``"any"`` schemas always match).
          3. Filter by ``available_material`` — only keep schemas whose
             required material key is ``True``.
          4. Sort by priority (higher first).  Flag ``ambiguous`` when
             multiple stage-specific schemas share the highest priority.
        """
        result = SelectionResult()

        # 1 — explicit request
        if context.requested_output:
            desc = self._schemas.get(context.requested_output)
            if desc is None:
                result.errors.append(f"Requested output '{context.requested_output}' not found")
                return result
            result.selected = [desc]
            return result

        # 2 — stage filter
        candidates = list(self._schemas.values())
        if context.stage:
            candidates = [c for c in candidates if c.stage == context.stage or c.stage == "any"]

        # 3 — material filter
        if context.available_material:
            filtered = []
            for c in candidates:
                material_key = self._MATERIAL_KEYS.get(c.name)
                if material_key is None or context.available_material.get(material_key, False):
                    filtered.append(c)
            candidates = filtered

        if not candidates:
            result.errors.append("No output schemas match the selection context")
            return result

        # 5 — ambiguity check (only within the same stage)
        stage_specific = [c for c in candidates if c.stage != "any"]
        if stage_specific:
            by_stage: dict[str, list[OutputSchemaDescriptor]] = {}
            for c in stage_specific:
                by_stage.setdefault(c.stage, []).append(c)
            for stage_name, schemas in by_stage.items():
                if len(schemas) > 1:
                    top_priority = max(c.priority for c in schemas)
                    top = [c for c in schemas if c.priority == top_priority]
                    if len(top) > 1:
                        result.ambiguous = True
                        result.errors.append(
                            f"Multiple schemas for stage '{stage_name}' "
                            f"with equal priority: {[c.name for c in top]}"
                        )

        candidates.sort(key=lambda c: c.priority, reverse=True)
        result.selected = candidates
        return result

    # -- serialization -----------------------------------------------------

    def serialize(self, output_name: str, data: Any) -> SerializationResult:
        """Serialize ``data`` to JSON under the named output schema.

        Accepts: dicts, dataclasses, Pydantic v2 models, objects with
        ``to_dict()``.  Does NOT validate invariants.
        """
        desc = self._schemas.get(output_name)
        if desc is None:
            return SerializationResult(
                output_name=output_name,
                errors=[f"Output schema '{output_name}' not found in registry"],
            )

        try:
            data_dict = self._to_dict(data)
            json_str = json.dumps(data_dict, indent=2, default=str)
            return SerializationResult(
                output_name=output_name,
                data=data_dict,
                json_str=json_str,
                schema=desc,
            )
        except (TypeError, ValueError) as exc:
            return SerializationResult(
                output_name=output_name,
                errors=[f"Serialization failed: {exc}"],
                schema=desc,
            )

    def serialize_multiple(
        self,
        selections: list[OutputSchemaDescriptor],
        data_map: dict[str, Any],
    ) -> list[SerializationResult]:
        """Serialize multiple outputs in one call."""
        results: list[SerializationResult] = []
        for desc in selections:
            data = data_map.get(desc.name)
            if data is None:
                results.append(
                    SerializationResult(
                        output_name=desc.name,
                        errors=[f"No data provided for output '{desc.name}'"],
                        schema=desc,
                    )
                )
            else:
                results.append(self.serialize(desc.name, data))
        return results

    # -- schema loading & structural validation -----------------------------

    def load_schema(self, name: str) -> dict | None:
        """Load a JSON schema definition from disk. Returns ``None`` on error."""
        desc = self._schemas.get(name)
        if desc is None:
            return None
        path = self._schemas_dir / desc.schema_file
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError):
            return None

    def validate_json(self, output_name: str, json_str: str) -> list[str]:
        """Lightweight structural validation of ``json_str`` against the
        registered JSON schema for ``output_name``.

        Checks required fields, ``const`` values, and ``enum`` membership.
        This is structural validation only — not cross-record invariant
        or evidence resolution validation.
        """
        desc = self._schemas.get(output_name)
        if desc is None:
            return [f"Output schema '{output_name}' not found in registry"]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            return [f"Malformed JSON: {exc}"]

        if not isinstance(data, dict):
            return ["JSON root must be an object"]

        schema = self.load_schema(output_name)
        if schema is None:
            return [f"Schema file for '{output_name}' could not be loaded"]

        errors: list[str] = []
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in data:
                errors.append(f"Missing required field: {field_name}")

        props = schema.get("properties", {})
        for field_name, field_schema in props.items():
            if field_name not in data:
                continue
            val = data[field_name]
            if "const" in field_schema and val != field_schema["const"]:
                errors.append(
                    f"Field '{field_name}' must be '{field_schema['const']}', got '{val}'"
                )
            if "enum" in field_schema and val is not None and val not in field_schema["enum"]:
                errors.append(
                    f"Field '{field_name}' value '{val}' not in enum: {field_schema['enum']}"
                )

        return errors

    # -- extractors --------------------------------------------------------

    @staticmethod
    def extract_gap_analysis(plan_record: dict) -> dict:
        """Extract the ``gap_analysis`` section from a Plan record dict.

        Also enriches with ``task_id`` and ``plan_record_id`` for the
        ``output_gap_analysis`` schema.
        """
        gap = dict(plan_record.get("gap_analysis", {}))
        gap.setdefault("task_id", plan_record.get("task_id"))
        gap.setdefault("plan_record_id", plan_record.get("record_id"))
        gap.setdefault("plan_revision", plan_record.get("revision"))
        return gap

    # -- internal helpers --------------------------------------------------

    @staticmethod
    def _to_dict(data: Any) -> dict:
        """Convert dataclass, Pydantic model, or dict-like to a plain dict."""
        if isinstance(data, dict):
            return data
        if hasattr(data, "__dataclass_fields__"):
            return asdict(data)
        if hasattr(data, "model_dump"):
            return dict(data.model_dump())
        if hasattr(data, "to_dict"):
            return dict(data.to_dict())
        return dict(data)
