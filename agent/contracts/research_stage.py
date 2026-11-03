"""Canonical workflow records for OneShot."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


RequirementId = Annotated[
    str,
    Field(pattern=r"^REQ-[0-9]{3,}$"),
]
FindingId = Annotated[
    str,
    Field(pattern=r"^FND-[0-9]{3,}$"),
]
SourceId = Annotated[
    str,
    Field(pattern=r"^SRC-[0-9]{3,}$"),
]
EvidenceId = Annotated[
    str,
    Field(pattern=r"^EVD-[0-9]{3,}$"),
]
TodoId = Annotated[
    str,
    Field(pattern=r"^TODO-[0-9]{3,}$"),
]
HelpTaskId = Annotated[
    str,
    Field(pattern=r"^HELP-[0-9]{3,}$"),
]


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        validate_default=True,
    )


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"
    SUPPORTED = "supported"
    CANDIDATE = "candidate"
    CONFLICTING = "conflicting"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class TodoStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ActionCheckStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ValidationStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class HelpTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class EvidenceReference(ContractModel):
    evidence_id: EvidenceId
    reference: str = Field(min_length=1)
    observation: str = Field(min_length=1)
    requirement_ids: list[RequirementId] = Field(
        default_factory=list,
    )


class ActionCheck(ContractModel):
    expected_result: str = Field(min_length=1)
    status: ActionCheckStatus = ActionCheckStatus.NOT_RUN
    actual_result: str | None = None
    evidence_ids: list[EvidenceId] = Field(
        default_factory=list,
    )


class TodoRecord(ContractModel):
    todo_id: TodoId
    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    status: TodoStatus = TodoStatus.PENDING
    evidence_ids: list[EvidenceId] = Field(
        default_factory=list,
    )
    action_check: ActionCheck
    actual_error: str | None = None
    blocker: str | None = None
    recovery_reference: str | None = None
    resume_point: str | None = None

    @model_validator(mode="after")
    def validate_final_status(self) -> Self:
        if self.status is TodoStatus.COMPLETED:
            if self.action_check.status is not ActionCheckStatus.PASSED:
                raise ValueError(
                    f"{self.todo_id} requires a passed action check."
                )

            if not self.evidence_ids:
                raise ValueError(
                    f"{self.todo_id} requires completion evidence."
                )

        if self.status is TodoStatus.FAILED:
            if not self.actual_error:
                raise ValueError(
                    f"{self.todo_id} requires the actual error."
                )

            if not self.recovery_reference:
                raise ValueError(
                    f"{self.todo_id} requires a recovery reference."
                )

        if self.status is TodoStatus.BLOCKED:
            if not self.blocker:
                raise ValueError(
                    f"{self.todo_id} requires a blocker description."
                )

            if not self.recovery_reference:
                raise ValueError(
                    f"{self.todo_id} requires a recovery reference."
                )

            if not self.resume_point:
                raise ValueError(
                    f"{self.todo_id} requires a resume point."
                )

        return self


class RequirementRecord(ContractModel):
    requirement_id: RequirementId
    original_wording: str = Field(min_length=1)
    source_type: Literal[
        "original_request",
        "accepted_clarification",
        "accepted_after_discovery",
    ]
    source_reference: str = Field(min_length=1)
    research_question: str = Field(min_length=1)
    evidence_needed: list[str] = Field(default_factory=list)
    finding_ids: list[FindingId] = Field(default_factory=list)
    evidence_status: EvidenceStatus
    missing_evidence: list[str] = Field(default_factory=list)
    investigation_needed: list[str] = Field(default_factory=list)
    remaining_uncertainty: list[str] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def validate_evidence_state(self) -> Self:
        if self.evidence_status is EvidenceStatus.UNRESOLVED:
            if not self.missing_evidence:
                raise ValueError(
                    f"{self.requirement_id} requires missing evidence."
                )

            if not self.investigation_needed:
                raise ValueError(
                    f"{self.requirement_id} requires an "
                    "investigation path."
                )

        return self


class SourceRecord(ContractModel):
    source_id: SourceId
    title: str = Field(min_length=1)
    source_type: Literal[
        "official_specification",
        "official_documentation",
        "primary_repository",
        "official_release_notes",
        "maintainer_guidance",
        "technical_reference",
        "secondary_analysis",
        "available_evidence",
    ]
    url: AnyUrl | None = None
    local_reference: str | None = None
    supported_claims: list[str] = Field(default_factory=list)
    requirement_ids: list[RequirementId] = Field(
        default_factory=list,
    )

    @model_validator(mode="after")
    def require_source_location(self) -> Self:
        if self.url is None and self.local_reference is None:
            raise ValueError(
                f"{self.source_id} requires a URL or local reference."
            )

        return self


class FindingRecord(ContractModel):
    finding_id: FindingId
    statement: str = Field(min_length=1)
    requirement_ids: list[RequirementId] = Field(min_length=1)
    source_ids: list[SourceId] = Field(default_factory=list)
    evidence_status: EvidenceStatus
    dependencies: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    remaining_uncertainty: list[str] = Field(
        default_factory=list,
    )
    missing_evidence: list[str] = Field(default_factory=list)
    investigation_needed: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_state(self) -> Self:
        if self.evidence_status is EvidenceStatus.UNRESOLVED:
            if not self.missing_evidence:
                raise ValueError(
                    f"{self.finding_id} requires missing evidence."
                )

            if not self.investigation_needed:
                raise ValueError(
                    f"{self.finding_id} requires an "
                    "investigation path."
                )

            return self

        if (
            self.evidence_status is not EvidenceStatus.NOT_APPLICABLE
            and not self.source_ids
        ):
            raise ValueError(
                f"{self.finding_id} requires a source reference."
            )

        return self


class HelpTaskRecord(ContractModel):
    help_task_id: HelpTaskId
    objective: str = Field(min_length=1)
    requirement_ids: list[RequirementId] = Field(min_length=1)
    scope: str = Field(min_length=1)
    questions: list[str] = Field(min_length=1)
    evidence_needed: list[str] = Field(default_factory=list)
    expected_result: str = Field(min_length=1)
    excluded_decisions: list[str] = Field(default_factory=list)
    status: HelpTaskStatus
    result_reference: str | None = None
    actual_error: str | None = None
    assessed: bool = False
    accepted_finding_ids: list[FindingId] = Field(
        default_factory=list,
    )
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_final_status(self) -> Self:
        if self.status is HelpTaskStatus.COMPLETED:
            if not self.result_reference:
                raise ValueError(
                    f"{self.help_task_id} requires a result reference."
                )

            if not self.assessed:
                raise ValueError(
                    f"{self.help_task_id} requires result assessment."
                )

        if self.status is HelpTaskStatus.FAILED:
            if not self.actual_error:
                raise ValueError(
                    f"{self.help_task_id} requires the actual error."
                )

        return self


class ComparisonResult(ContractModel):
    comparison_id: str = Field(pattern=r"^CMP-[0-9]{3,}$")
    requirement_ids: list[RequirementId] = Field(min_length=1)
    source_ids: list[SourceId] = Field(min_length=1)
    options: list[str] = Field(min_length=2)
    evaluation_basis: list[str] = Field(min_length=1)
    findings: list[str] = Field(min_length=1)
    tradeoffs: list[str] = Field(default_factory=list)
    contradiction_references: list[str] = Field(
        default_factory=list,
    )
    remaining_uncertainty: list[str] = Field(
        default_factory=list,
    )


class ResearchRecommendation(ContractModel):
    recommendation_id: str = Field(pattern=r"^REC-[0-9]{3,}$")
    requirement_ids: list[RequirementId] = Field(min_length=1)
    source_ids: list[SourceId] = Field(min_length=1)
    preferred_option: str = Field(min_length=1)
    evaluation_basis: list[str] = Field(min_length=1)
    tradeoffs: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(
        default_factory=list,
    )
    remaining_uncertainty: list[str] = Field(
        default_factory=list,
    )
    change_conditions: list[str] = Field(default_factory=list)


class ArtifactReference(ContractModel):
    artifact_type: Literal["request", "report", "record"]
    relative_path: str = Field(min_length=1)
    revision: int = Field(ge=1)


class ValidationCheck(ContractModel):
    check_id: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    status: ValidationStatus
    actual_result: str = Field(min_length=1)
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class ResearchRecord(ContractModel):
    record_type: Literal["research"] = "research"
    record_version: Literal["1.0"] = "1.0"
    run_id: str = Field(min_length=1)
    task_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    )
    revision: int = Field(ge=1)
    created_at: datetime
    request_digest: str = Field(
        pattern=r"^[a-f0-9]{64}$",
    )

    requirements: list[RequirementRecord] = Field(min_length=1)
    findings: list[FindingRecord] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    todos: list[TodoRecord] = Field(min_length=1)
    help_tasks: list[HelpTaskRecord] = Field(default_factory=list)
    comparisons: list[ComparisonResult] = Field(
        default_factory=list,
    )
    recommendations: list[ResearchRecommendation] = Field(
        default_factory=list,
    )
    contradictions: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        requirement_ids = {
            item.requirement_id for item in self.requirements
        }
        finding_ids = {
            item.finding_id for item in self.findings
        }
        source_ids = {
            item.source_id for item in self.sources
        }
        evidence_ids = {
            item.evidence_id for item in self.evidence
        }

        if len(requirement_ids) != len(self.requirements):
            raise ValueError("Requirement IDs must be unique.")

        if len(finding_ids) != len(self.findings):
            raise ValueError("Finding IDs must be unique.")

        if len(source_ids) != len(self.sources):
            raise ValueError("Source IDs must be unique.")

        if len(evidence_ids) != len(self.evidence):
            raise ValueError("Evidence IDs must be unique.")

        for requirement in self.requirements:
            _require_known(
                owner=requirement.requirement_id,
                relation="findings",
                references=requirement.finding_ids,
                known=finding_ids,
            )

        for finding in self.findings:
            _require_known(
                owner=finding.finding_id,
                relation="requirements",
                references=finding.requirement_ids,
                known=requirement_ids,
            )
            _require_known(
                owner=finding.finding_id,
                relation="sources",
                references=finding.source_ids,
                known=source_ids,
            )

        for todo in self.todos:
            _require_known(
                owner=todo.todo_id,
                relation="evidence",
                references=todo.evidence_ids,
                known=evidence_ids,
            )

        for help_task in self.help_tasks:
            _require_known(
                owner=help_task.help_task_id,
                relation="requirements",
                references=help_task.requirement_ids,
                known=requirement_ids,
            )
            _require_known(
                owner=help_task.help_task_id,
                relation="findings",
                references=help_task.accepted_finding_ids,
                known=finding_ids,
            )

        for comparison in self.comparisons:
            _require_known(
                owner=comparison.comparison_id,
                relation="requirements",
                references=comparison.requirement_ids,
                known=requirement_ids,
            )
            _require_known(
                owner=comparison.comparison_id,
                relation="sources",
                references=comparison.source_ids,
                known=source_ids,
            )

        for recommendation in self.recommendations:
            _require_known(
                owner=recommendation.recommendation_id,
                relation="requirements",
                references=recommendation.requirement_ids,
                known=requirement_ids,
            )
            _require_known(
                owner=recommendation.recommendation_id,
                relation="sources",
                references=recommendation.source_ids,
                known=source_ids,
            )

        artifact_types = [
            artifact.artifact_type
            for artifact in self.artifacts
        ]

        if len(artifact_types) != len(set(artifact_types)):
            raise ValueError(
                "Artifact types must be unique."
            )

        missing_artifacts = {
            "request",
            "report",
            "record",
        } - set(artifact_types)

        if missing_artifacts:
            raise ValueError(
                "Missing artifact references: "
                f"{sorted(missing_artifacts)}"
            )

        return self


def _require_known(
    *,
    owner: str,
    relation: str,
    references: list[str],
    known: set[str],
) -> None:
    unknown = set(references) - known

    if unknown:
        raise ValueError(
            f"{owner} references unknown {relation}: "
            f"{sorted(unknown)}"
        )
