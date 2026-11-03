"""Semantic validators for Research records.

Extended with parent-child lifecycle validators: admission,
output binding, review gating, and fixture validity checks.
"""

from __future__ import annotations

from agent.contracts.research import (
    AdmissionDisposition,
    InputRequest,
    OutputResult,
    ResearchRecord,
    ResearchRequest,
    ReviewDisposition,
)

# ---------------------------------------------------------------------------
# Existing validators (preserved)
# ---------------------------------------------------------------------------


def validate_research_ids(record: ResearchRecord) -> list[str]:
    """Check for duplicate requirement and criterion IDs."""
    errors: list[str] = []
    req_ids = [r.requirement_id for r in record.requirements]
    if len(req_ids) != len(set(req_ids)):
        errors.append("duplicate requirement IDs")
    crit_ids = [c.criterion_id for c in record.acceptance_criteria]
    if len(crit_ids) != len(set(crit_ids)):
        errors.append("duplicate criterion IDs")
    return errors


def validate_criterion_binding(record: ResearchRecord) -> list[str]:
    """Every criterion must reference an existing requirement."""
    req_ids = {r.requirement_id for r in record.requirements}
    errors: list[str] = []
    for crit in record.acceptance_criteria:
        if crit.requirement_id not in req_ids:
            errors.append(f"criterion {crit.criterion_id} references unknown requirement {crit.requirement_id}")
    return errors


# ---------------------------------------------------------------------------
# New lifecycle validators
# ---------------------------------------------------------------------------


def validate_research_request(request: ResearchRequest) -> list[str]:
    """Validate a ResearchRequest parent case."""
    errors: list[str] = []
    child_ids = [c.split("@")[0] for c in request.child_refs]
    if len(child_ids) != len(set(child_ids)):
        errors.append("duplicate child references in request")
    if request.status not in ("active", "completed", "cancelled"):
        errors.append(f"invalid request status: {request.status}")
    return errors


def validate_input_admission(
    input_request: InputRequest,
    request: ResearchRequest,
) -> list[str]:
    """Validate that an InputRequest is properly admitted and bound."""
    errors: list[str] = []
    if input_request.parent_request_id != request.request_id:
        errors.append(
            f"input {input_request.input_id} parent mismatch: {input_request.parent_request_id} != {request.request_id}"
        )
    if (
        input_request.admission.disposition == AdmissionDisposition.ACCEPTED
        and not input_request.admission.validation_receipt_ref
    ):
        errors.append(f"accepted input {input_request.input_id} missing validation receipt")
    if input_request.admission.disposition == AdmissionDisposition.REJECTED and input_request.research_plan is not None:
        errors.append(f"rejected input {input_request.input_id} has a research plan")
    return errors


def validate_output_binding(
    output: OutputResult,
    input_request: InputRequest,
) -> list[str]:
    """Validate that OutputResult binds to the exact admitted input revision."""
    errors: list[str] = []
    expected_bind = f"{input_request.input_id}@{input_request.revision}"
    if output.responds_to != expected_bind:
        errors.append(f"output {output.output_id} responds_to mismatch: {output.responds_to} != {expected_bind}")
    if output.parent_request_id != input_request.parent_request_id:
        errors.append(
            f"output {output.output_id} parent mismatch: "
            f"{output.parent_request_id} != {input_request.parent_request_id}"
        )
    if not output.admission_receipt_ref:
        errors.append(f"output {output.output_id} missing admission receipt")
    return errors


def validate_review_gating(output: OutputResult) -> list[str]:
    """Validate that review acceptance requires completed execution and receipts."""
    errors: list[str] = []
    if output.review_disposition == ReviewDisposition.ACCEPTED:
        if not output.review_receipt_ref:
            errors.append(f"accepted output {output.output_id} missing review receipt")
        if output.execution_status.value != "completed":
            errors.append(f"accepted output {output.output_id} not completed")
        if not output.execution_receipt_ref:
            errors.append(f"accepted output {output.output_id} missing execution receipt")
        if not output.report_ref:
            errors.append(f"accepted output {output.output_id} missing report reference")
    return errors


def validate_stale_revision(
    input_request: InputRequest,
    latest_revision: int,
) -> list[str]:
    """Validate that input revision is not stale."""
    errors: list[str] = []
    if input_request.revision < latest_revision:
        errors.append(f"stale input revision {input_request.revision} (latest is {latest_revision})")
    return errors


def validate_fixture_spec_completeness(
    output: OutputResult,
    intent: str | None = None,
) -> list[str]:
    """Validate fixture specifications when applicable.

    Fixture validation is conditional: only validate when the Research
    intent requires fixture work (CRAFT_FIXTURE, INVESTIGATE_FIXTURE_VALIDATION)
    or when fixture specs are explicitly supplied. Do not turn fixture
    completeness into a global Research admission gate.
    """
    errors: list[str] = []

    if not output.fixture_specs and not output.fixture_validity:
        return errors

    for spec in output.fixture_specs:
        if not spec.preconditions:
            errors.append(f"fixture {spec.fixture_id} missing preconditions")
        if not spec.required_evidence:
            errors.append(f"fixture {spec.fixture_id} missing required evidence")
    for assessment in output.fixture_validity:
        found = any(assessment.fixture_ref == spec.fixture_id for spec in output.fixture_specs)
        if not found:
            errors.append(f"fixture validity assessment {assessment.fixture_ref} references unknown fixture")
    return errors
