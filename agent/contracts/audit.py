"""Audit findings contract — persisted through host-owned artifact storage.

Distinguishable from ResearchRecord: different contract_id, contract_version,
and artifact_id prefix. Audit never issues host receipts or advances stages
on its own; the host dispatches audit within the existing Research stage and
owns the receipt and stage transition.
"""

from __future__ import annotations

from pydantic import Field

from agent.contracts.common import ContractModel


class AuditFinding(ContractModel):
    """A single audit observation with stable identity and source evidence."""

    finding_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    code: str = Field(min_length=1)
    status: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    path: str = Field(min_length=1)
    line: int = Field(ge=0)
    message: str = Field(min_length=1)
    evidence_digest: str = ""


class AuditFindingsRecord(ContractModel):
    """Persisted audit findings — not a ResearchRecord.

    The host stores this through ArtifactStore with contract_id
    ``audit_findings`` so downstream consumers can distinguish it from
    ``research_record`` artifacts.
    """

    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage_revision: int = Field(ge=1)
    root: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    requested_capabilities: tuple[str, ...] = ()
    executed_capabilities: tuple[str, ...] = ()
    findings: tuple[AuditFinding, ...] = ()
    limitations: tuple[str, ...] = ()
    disposition: str = Field(min_length=1)
    request: str = ""
    source_revision: str = ""
