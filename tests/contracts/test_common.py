"""Contract tests for common primitives — CT01-CT06."""

import pytest
from pydantic import ValidationError

from agent.contracts.common import (
    ArtifactRef,
    ContractModel,
    DiagnosticStatus,
    EvidenceRef,
    OperationState,
    ProposalState,
    SpecificationState,
    StepResult,
    StepStatus,
    UpstreamBinding,
)


class TestContractModel:
    def test_frozen_model_cannot_be_modified(self):
        """CT01: Contract models are immutable."""

        class TestModel(ContractModel):
            value: str = "test"

        m = TestModel()
        with pytest.raises((ValidationError, TypeError)):
            m.value = "changed"

    def test_extra_fields_forbidden(self):
        """CT02: Unknown fields rejected."""

        class TestModel(ContractModel):
            value: str = "test"

        with pytest.raises(ValidationError):
            TestModel(value="ok", unknown="bad")

    def test_artifact_ref_valid(self):
        """CT03: Valid ArtifactRef accepted."""
        ref = ArtifactRef(
            artifact_id="art-001",
            artifact_revision=1,
            artifact_digest="a" * 64,
            contract_id="research",
            contract_version="1.0",
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        assert ref.artifact_id == "art-001"

    def test_invalid_sha256_rejected(self):
        """CT04: Invalid digest format rejected."""
        with pytest.raises(ValidationError):
            ArtifactRef(
                artifact_id="art-001",
                artifact_revision=1,
                artifact_digest="not-a-hash",
                contract_id="research",
                contract_version="1.0",
                serializer_profile="rfc8785-jcs-sha256-v1",
            )

    def test_step_result_executed_requires_receipt(self):
        """CT05: Executed steps require receipt."""
        with pytest.raises(ValidationError):
            StepResult(
                step_id="s1",
                status=StepStatus.COMPLETED,
                receipt_ref=None,
            )

    def test_step_result_non_executed_requires_reason(self):
        """CT06: Non-executed steps require reason."""
        with pytest.raises(ValidationError):
            StepResult(
                step_id="s1",
                status=StepStatus.NOT_RUN,
                reason=None,
            )

    def test_evidence_ref_valid(self):
        """EvidenceRef with all fields."""
        ev = EvidenceRef(
            evidence_id="EVD-001",
            content_digest="b" * 64,
            location="/path/to/evidence",
            description="test evidence",
            observation="file contains expected pattern",
            receipt_ref="rcpt-001",
            artifact_ref="art-001",
        )
        assert ev.evidence_id == "EVD-001"
        assert ev.observation == "file contains expected pattern"

    def test_evidence_ref_invalid_id_rejected(self):
        """EvidenceRef with wrong pattern rejected."""
        with pytest.raises(ValidationError):
            EvidenceRef(
                evidence_id="ev-001",
                content_digest="b" * 64,
                location="/path",
            )

    def test_step_result_blocked_requires_blocker(self):
        """Blocked step must have blocker field."""
        with pytest.raises(ValidationError):
            StepResult(
                step_id="s1",
                status=StepStatus.BLOCKED,
                reason="missing dependency",
                blocker=None,
            )

    def test_step_result_blocked_with_blocker(self):
        """Blocked step with blocker passes."""
        sr = StepResult(
            step_id="s1",
            status=StepStatus.BLOCKED,
            reason="missing dependency",
            blocker="upstream artifact not frozen",
        )
        assert sr.blocker == "upstream artifact not frozen"

    def test_diagnostic_status_values(self):
        """DiagnosticStatus has exactly 3 values."""
        assert DiagnosticStatus.VALID == "valid"
        assert DiagnosticStatus.NOT_VALID == "not_valid"
        assert DiagnosticStatus.UNCERTAINTY == "uncertainty"

    def test_proposal_state_values(self):
        """ProposalState has exactly 8 values."""
        assert len(list(ProposalState)) == 8

    def test_operation_state_projection(self):
        """OperationState projects to StepStatus."""
        assert OperationState.COMPLETED.final_report_status is StepStatus.COMPLETED
        assert OperationState.EFFECT_UNCERTAIN.final_report_status is StepStatus.BLOCKED
        assert OperationState.SKIPPED.final_report_status is StepStatus.SKIPPED
        with pytest.raises(ValueError):
            _ = OperationState.IN_FLIGHT.final_report_status

    def test_specification_state_values(self):
        """SpecificationState has exactly 3 values."""
        assert len(list(SpecificationState)) == 3

    def test_upstream_binding_valid(self):
        """UpstreamBinding binds artifact to receipts."""
        ref = ArtifactRef(
            artifact_id="art-001",
            artifact_revision=1,
            artifact_digest="a" * 64,
            contract_id="research",
            contract_version="1.0",
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        ub = UpstreamBinding(
            artifact=ref,
            validation_receipt_ref="rcpt-v-001",
            handoff_receipt_ref="rcpt-h-001",
        )
        assert ub.validation_receipt_ref == "rcpt-v-001"
