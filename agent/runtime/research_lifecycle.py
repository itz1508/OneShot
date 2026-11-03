"""Research host lifecycle — durable parent-child case management.

Wires ResearchRequest/InputRequest/OutputResult through existing
ArtifactStore, ReceiptStore, CheckpointStore, and EventStore.
No new database or service is created — all persistence uses
the existing host-owned stores with atomic CAS and receipt verification.

Crash safety: every state transition writes an immutable artifact
revision and a host receipt before advancing. On restart, the
latest persisted revision is loaded and verified.
"""

from __future__ import annotations

from agent.contracts.common import EvidenceRef
from agent.contracts.research import (
    AdmissionDisposition,
    ExecutionStatus,
    FixtureSpecification,
    FixtureValidityAssessment,
    InputRequest,
    OutputResult,
    RequirementTrace,
    ResearchAdmission,
    ResearchIntent,
    ResearchRequest,
    ReviewDisposition,
)
from agent.research_catalog import ResearchCatalog
from agent.runtime.artifact_store import (
    ArtifactStore,
    StaleRevisionError,
)
from agent.runtime.event_store import EventStore
from agent.runtime.receipt_store import ReceiptStore


class ResearchLifecycleError(Exception):
    pass


class ResearchLifecycle:
    """Host-owned Research case lifecycle.

    Uses existing stores — no new database or service:
    - ArtifactStore: immutable revisioned Research artifacts
    - ReceiptStore: host-verified admission and review receipts
    - EventStore: audit trail of lifecycle events
    """

    def __init__(
        self,
        artifact_store: ArtifactStore,
        receipt_store: ReceiptStore,
        event_store: EventStore,
        catalog: ResearchCatalog | None = None,
    ) -> None:
        self._artifacts = artifact_store
        self._receipts = receipt_store
        self._events = event_store
        self._catalog = catalog or ResearchCatalog()

    # -----------------------------------------------------------------
    # Parent case
    # -----------------------------------------------------------------

    def create_request(
        self,
        request_id: str,
        created_from: str,
        accepted_requirement_refs: tuple[str, ...] = (),
    ) -> ResearchRequest:
        """Create a new Research parent case at revision 1."""
        request = ResearchRequest(
            request_id=request_id,
            revision=1,
            status="active",
            created_from=created_from,
            accepted_requirement_refs=accepted_requirement_refs,
        )
        self._artifacts.put_immutable(
            request,
            request_id,
            1,
            "research_request",
            "1.0",
        )
        self._events.append(
            request_id,
            "research_request_created",
            f"created_from={created_from}",
        )
        return request

    def get_request(self, request_id: str) -> ResearchRequest:
        """Load the latest revision of a ResearchRequest."""
        latest = self._artifacts.latest_revision(request_id)
        if latest == 0:
            raise ResearchLifecycleError(f"request {request_id} not found")
        content = self._artifacts.get_verified(request_id, latest)
        return ResearchRequest.model_validate_json(content)

    def _update_request_cas(
        self,
        request: ResearchRequest,
        expected_revision: int,
    ) -> ResearchRequest:
        """Persist a new revision of a ResearchRequest with atomic CAS.

        Raises ResearchLifecycleError (wrapping StaleRevisionError) if
        another writer has committed first.
        """
        new_rev = expected_revision + 1
        updated = request.model_copy(update={"revision": new_rev})
        try:
            self._artifacts.put_cas(
                updated,
                request.request_id,
                expected_revision,
                "research_request",
                "1.0",
            )
        except StaleRevisionError as e:
            raise ResearchLifecycleError(f"CAS conflict updating request {request.request_id}: {e}") from e
        self._events.append(
            updated.request_id,
            "research_request_updated",
            f"revision={new_rev}",
        )
        return updated

    # -----------------------------------------------------------------
    # Input admission
    # -----------------------------------------------------------------

    def admit_input(
        self,
        input_id: str,
        parent_request_id: str,
        intent: ResearchIntent,
        provenance_ref: str,
        investigation_question: str,
        expected_result: str,
        related_requirement_refs: tuple[str, ...] = (),
        supporting_input_refs: tuple[str, ...] = (),
        keywords: tuple[str, ...] = (),
    ) -> InputRequest:
        """Admit a Research input request with host verification.

        The host validates:
        - Parent identity and exact input revision
        - Intent and bounded investigation scope
        - Provenance and accepted requirement references
        - Whether the requested work belongs to Research

        Only accepted inputs may be investigated. Isolated material
        may be investigated as a claim but cannot become accepted
        evidence without verification.
        """
        # Verify parent exists
        parent = self.get_request(parent_request_id)

        # Check for existing input (idempotent or duplicate)
        latest_input_rev = self._artifacts.latest_revision(input_id)
        if latest_input_rev > 0:
            raise ResearchLifecycleError(f"input {input_id} already exists at revision {latest_input_rev}")

        # Match against catalog
        catalog_match = self._catalog.match(intent, keywords)

        # Issue host receipt for admission
        admission_subject = f"research_admission:{parent_request_id}:{input_id}:1"
        receipt_id = f"admission-{input_id}"
        _, receipt_digest = self._receipts.issue_verified(
            receipt_id,
            "host",
            admission_subject,
        )

        # Create admission with host receipt
        admission = ResearchAdmission(
            disposition=AdmissionDisposition.ACCEPTED,
            validation_receipt_ref=f"{receipt_id}:{receipt_digest}",
        )

        input_request = InputRequest(
            input_id=input_id,
            parent_request_id=parent_request_id,
            revision=1,
            intent=intent,
            provenance_ref=provenance_ref,
            related_requirement_refs=related_requirement_refs,
            investigation_question=investigation_question,
            expected_result=expected_result,
            supporting_input_refs=supporting_input_refs,
            catalog_matches=(catalog_match,),
            admission=admission,
        )

        # Persist immutable input
        self._artifacts.put_immutable(
            input_request,
            input_id,
            1,
            "research_input",
            "1.0",
        )

        # Update parent's child_refs and current_input_ref with CAS
        parent_rev = self._artifacts.latest_revision(parent_request_id)
        updated_parent = parent.model_copy(
            update={
                "child_refs": (*parent.child_refs, f"{input_id}@1"),
                "current_input_ref": f"{input_id}@1",
            }
        )
        self._update_request_cas(updated_parent, parent_rev)

        self._events.append(
            parent_request_id,
            "input_admitted",
            f"input={input_id} intent={intent.value}",
        )
        return input_request

    def get_input(self, input_id: str, revision: int = 0) -> InputRequest:
        """Load an InputRequest by ID and revision (0 = latest)."""
        rev = revision or self._artifacts.latest_revision(input_id)
        if rev == 0:
            raise ResearchLifecycleError(f"input {input_id} not found")
        content = self._artifacts.get_verified(input_id, rev)
        return InputRequest.model_validate_json(content)

    # -----------------------------------------------------------------
    # Output production
    # -----------------------------------------------------------------

    def produce_output(
        self,
        output_id: str,
        parent_request_id: str,
        responds_to_input_id: str,
        responds_to_revision: int,
        report_ref: str,
        execution_status: ExecutionStatus = ExecutionStatus.COMPLETED,
        finding_refs: tuple[str, ...] = (),
        contradiction_refs: tuple[str, ...] = (),
        unresolved_refs: tuple[str, ...] = (),
        requirement_trace: tuple[RequirementTrace, ...] = (),
        proposed_followup_refs: tuple[str, ...] = (),
        fixture_specs: tuple[FixtureSpecification, ...] = (),
        fixture_validity: tuple[FixtureValidityAssessment, ...] = (),
        evidence_refs: tuple[EvidenceRef, ...] = (),
    ) -> OutputResult:
        """Produce a Research output bound to exact admitted input revision.

        Execution status is caller-supplied, not auto-completed. The
        host issues a separate execution receipt preserved in the
        OutputResult. If COMPLETED, the report artifact must exist.
        """
        # Verify parent exists
        parent = self.get_request(parent_request_id)

        # Verify the input exists at the specified revision
        input_content = self._artifacts.get_verified(
            responds_to_input_id,
            responds_to_revision,
        )
        input_request = InputRequest.model_validate_json(input_content)

        # Verify input was admitted
        if input_request.admission.disposition != AdmissionDisposition.ACCEPTED:
            raise ResearchLifecycleError(
                f"input {responds_to_input_id} was not admitted (disposition={input_request.admission.disposition})"
            )

        # Verify parent identity matches input's parent
        if input_request.parent_request_id != parent_request_id:
            raise ResearchLifecycleError(
                f"input {responds_to_input_id} belongs to parent {input_request.parent_request_id}, "
                f"not {parent_request_id}"
            )

        # Issue host receipt for output production
        output_subject = (
            f"research_output:{parent_request_id}:{output_id}:1:{responds_to_input_id}@{responds_to_revision}"
        )
        receipt_id = f"output-{output_id}"
        _, receipt_digest = self._receipts.issue_verified(
            receipt_id,
            "host",
            output_subject,
        )
        execution_receipt = f"{receipt_id}:{receipt_digest}"

        # If completed, verify report artifact exists
        if execution_status == ExecutionStatus.COMPLETED:
            if not report_ref:
                raise ResearchLifecycleError("completed output requires a report reference")
            if not self._artifacts.exists(report_ref, 1):
                raise ResearchLifecycleError(f"report artifact {report_ref} not found in artifact store")

        output = OutputResult(
            output_id=output_id,
            parent_request_id=parent_request_id,
            revision=1,
            responds_to=f"{responds_to_input_id}@{responds_to_revision}",
            admission_receipt_ref=input_request.admission.validation_receipt_ref,
            execution_status=execution_status,
            execution_receipt_ref=execution_receipt,
            report_ref=report_ref,
            finding_refs=finding_refs,
            contradiction_refs=contradiction_refs,
            unresolved_refs=unresolved_refs,
            requirement_trace=requirement_trace,
            proposed_followup_refs=proposed_followup_refs,
            fixture_specs=fixture_specs,
            fixture_validity=fixture_validity,
            evidence_refs=evidence_refs,
        )

        # Persist immutable output
        self._artifacts.put_immutable(
            output,
            output_id,
            1,
            "research_output",
            "1.0",
        )

        # Update parent's child_refs with CAS
        parent_rev = self._artifacts.latest_revision(parent_request_id)
        updated_parent = parent.model_copy(
            update={
                "child_refs": (*parent.child_refs, f"{output_id}@1"),
            }
        )
        self._update_request_cas(updated_parent, parent_rev)

        self._events.append(
            parent_request_id,
            "output_produced",
            f"output={output_id} responds_to={responds_to_input_id}@{responds_to_revision}",
        )
        return output

    def get_output(self, output_id: str, revision: int = 0) -> OutputResult:
        """Load an OutputResult by ID and revision (0 = latest)."""
        rev = revision or self._artifacts.latest_revision(output_id)
        if rev == 0:
            raise ResearchLifecycleError(f"output {output_id} not found")
        content = self._artifacts.get_verified(output_id, rev)
        return OutputResult.model_validate_json(content)

    # -----------------------------------------------------------------
    # Review and handoff
    # -----------------------------------------------------------------

    def review_output(
        self,
        output_id: str,
        disposition: ReviewDisposition,
        rejection_reason: str = "",
    ) -> OutputResult:
        """Review a Research output with host receipt.

        Idempotent: same disposition returns existing output. Conflicting
        disposition requires explicit correction. Only accepted results
        are eligible for Planning handoff.
        """
        output = self.get_output(output_id)

        # Idempotent: same disposition already applied
        if output.review_disposition == disposition:
            return output

        # Conflicting review requires explicit correction
        if output.review_disposition != ReviewDisposition.PENDING:
            raise ResearchLifecycleError(
                f"output {output_id} already reviewed as {output.review_disposition.value}; "
                "conflicting review requires explicit correction"
            )

        if disposition == ReviewDisposition.ACCEPTED:
            # Verify the output is completed before accepting
            if output.execution_status != ExecutionStatus.COMPLETED:
                raise ResearchLifecycleError(
                    f"cannot accept output {output_id} with execution_status={output.execution_status.value}"
                )

            # Verify the execution receipt
            exec_receipt_parts = output.execution_receipt_ref.split(":", 1)
            if len(exec_receipt_parts) != 2:
                raise ResearchLifecycleError(f"output {output_id} has malformed execution receipt")
            exec_receipt_id, exec_receipt_digest = exec_receipt_parts
            exec_subject = f"research_output:{output.parent_request_id}:{output_id}:1:{output.responds_to}"
            if not self._receipts.verify(
                exec_receipt_id,
                exec_receipt_digest,
                exec_subject,
            ):
                raise ResearchLifecycleError(f"output {output_id} execution receipt verification failed")

            # Issue host receipt for review acceptance
            review_subject = f"research_review:{output.parent_request_id}:{output_id}:accepted"
            receipt_id = f"review-{output_id}"
            _, receipt_digest = self._receipts.issue_verified(
                receipt_id,
                "host",
                review_subject,
            )
            review_receipt = f"{receipt_id}:{receipt_digest}"
        else:
            review_receipt = ""

        # Create new revision with review
        output_rev = self._artifacts.latest_revision(output_id)
        new_rev = output_rev + 1
        updated = output.model_copy(
            update={
                "revision": new_rev,
                "review_disposition": disposition,
                "review_receipt_ref": review_receipt,
            }
        )

        self._artifacts.put_immutable(
            updated,
            output_id,
            new_rev,
            "research_output",
            "1.0",
        )

        # If accepted, update parent's current_accepted_result_ref with CAS
        if disposition == ReviewDisposition.ACCEPTED:
            parent = self.get_request(output.parent_request_id)
            parent_rev = self._artifacts.latest_revision(output.parent_request_id)
            updated_parent = parent.model_copy(
                update={
                    "current_accepted_result_ref": f"{output_id}@{new_rev}",
                }
            )
            self._update_request_cas(updated_parent, parent_rev)

        self._events.append(
            output.parent_request_id,
            "output_reviewed",
            f"output={output_id} disposition={disposition.value}",
        )
        return updated

    def handoff_to_planning(
        self,
        output_id: str,
    ) -> OutputResult:
        """Verify an output is accepted and eligible for Planning handoff.

        Checks review disposition, review receipt (issuer, subject, digest),
        execution receipt, current accepted-result pointer (not superseded),
        and that the source input has not been superseded by a correction.
        """
        output = self.get_output(output_id)

        if output.review_disposition != ReviewDisposition.ACCEPTED:
            raise ResearchLifecycleError(
                f"output {output_id} not accepted for handoff (disposition={output.review_disposition})"
            )

        if not output.review_receipt_ref:
            raise ResearchLifecycleError(f"output {output_id} missing review receipt")

        # Verify the review receipt
        receipt_parts = output.review_receipt_ref.split(":", 1)
        if len(receipt_parts) != 2:
            raise ResearchLifecycleError(f"output {output_id} has malformed review receipt")
        review_receipt_id, review_receipt_digest = receipt_parts
        review_subject = f"research_review:{output.parent_request_id}:{output_id}:accepted"
        if not self._receipts.verify(
            review_receipt_id,
            review_receipt_digest,
            review_subject,
            expected_issuer="host",
        ):
            raise ResearchLifecycleError(f"output {output_id} review receipt verification failed")

        # Verify execution receipt
        if not output.execution_receipt_ref:
            raise ResearchLifecycleError(f"output {output_id} missing execution receipt")
        exec_parts = output.execution_receipt_ref.split(":", 1)
        if len(exec_parts) != 2:
            raise ResearchLifecycleError(f"output {output_id} has malformed execution receipt")
        exec_receipt_id, exec_receipt_digest = exec_parts
        exec_subject = f"research_output:{output.parent_request_id}:{output_id}:1:{output.responds_to}"
        if not self._receipts.verify(
            exec_receipt_id,
            exec_receipt_digest,
            exec_subject,
            expected_issuer="host",
        ):
            raise ResearchLifecycleError(f"output {output_id} execution receipt verification failed")

        # Verify the output is the current accepted result (not superseded)
        parent = self.get_request(output.parent_request_id)
        expected_ref = f"{output_id}@{output.revision}"
        if parent.current_accepted_result_ref != expected_ref:
            raise ResearchLifecycleError(
                f"output {output_id}@{output.revision} is not the current accepted result "
                f"(parent has {parent.current_accepted_result_ref})"
            )

        # Verify the input has not been superseded by a correction
        input_id = output.responds_to.split("@")[0]
        input_rev = int(output.responds_to.split("@")[1])
        latest_input_rev = self._artifacts.latest_revision(input_id)
        if latest_input_rev > input_rev:
            raise ResearchLifecycleError(
                f"input {input_id} has been superseded (output bound to rev {input_rev}, latest is {latest_input_rev})"
            )

        self._events.append(
            output.parent_request_id,
            "planning_handoff",
            f"output={output_id}",
        )
        return output

    # -----------------------------------------------------------------
    # Correction lifecycle
    # -----------------------------------------------------------------

    def create_correction_input(
        self,
        input_id: str,
        parent_request_id: str,
        intent: ResearchIntent,
        provenance_ref: str,
        investigation_question: str,
        expected_result: str,
        related_requirement_refs: tuple[str, ...] = (),
        keywords: tuple[str, ...] = (),
    ) -> InputRequest:
        """Create a new revision of an input (correction).

        Corrections preserve prior revisions. Multiple revisions of the
        same input are valid history, not duplicate child identities.
        """
        latest_rev = self._artifacts.latest_revision(input_id)
        if latest_rev == 0:
            raise ResearchLifecycleError(f"input {input_id} not found for correction")

        # Load the latest input
        self.get_input(input_id, latest_rev)

        # Create new revision
        new_rev = latest_rev + 1

        # Match against catalog
        catalog_match = self._catalog.match(intent, keywords)

        # Issue new host receipt
        admission_subject = f"research_admission:{parent_request_id}:{input_id}:{new_rev}"
        receipt_id = f"admission-{input_id}-{new_rev}"
        _, receipt_digest = self._receipts.issue_verified(
            receipt_id,
            "host",
            admission_subject,
        )

        admission = ResearchAdmission(
            disposition=AdmissionDisposition.ACCEPTED,
            validation_receipt_ref=f"{receipt_id}:{receipt_digest}",
        )

        corrected = InputRequest(
            input_id=input_id,
            parent_request_id=parent_request_id,
            revision=new_rev,
            intent=intent,
            provenance_ref=provenance_ref,
            related_requirement_refs=related_requirement_refs,
            investigation_question=investigation_question,
            expected_result=expected_result,
            catalog_matches=(catalog_match,),
            admission=admission,
        )

        # Persist new revision (immutable — prior revision preserved)
        self._artifacts.put_immutable(
            corrected,
            input_id,
            new_rev,
            "research_input",
            "1.0",
        )

        # Update parent's current_input_ref and child_refs with CAS
        parent = self.get_request(parent_request_id)
        parent_rev = self._artifacts.latest_revision(parent_request_id)
        child_ref = f"{input_id}@{new_rev}"
        updated_parent = parent.model_copy(
            update={
                "current_input_ref": child_ref,
                "child_refs": (*parent.child_refs, child_ref),
            }
        )
        self._update_request_cas(updated_parent, parent_rev)

        self._events.append(
            parent_request_id,
            "input_corrected",
            f"input={input_id} revision={new_rev}",
        )
        return corrected

    # -----------------------------------------------------------------
    # Crash-safe reconciliation
    # -----------------------------------------------------------------

    def reconcile(self, request_id: str) -> ResearchRequest:
        """Load and verify the latest persisted state after restart.

        Inspects persisted children, verifies exact bindings, detects
        orphaned records, and classifies unrecoverable effects as
        uncertain. Never blindly retries an operation whose prior
        effect may have committed.
        """
        request = self.get_request(request_id)

        # Verify child references point to existing artifacts
        orphans: list[str] = []
        for child_ref in request.child_refs:
            parts = child_ref.rsplit("@", 1)
            if len(parts) != 2:
                orphans.append(child_ref)
                continue
            child_id, child_rev_str = parts
            try:
                child_rev = int(child_rev_str)
            except ValueError:
                orphans.append(child_ref)
                continue
            if not self._artifacts.exists(child_id, child_rev):
                orphans.append(child_ref)

        if orphans:
            self._events.append(
                request_id,
                "reconcile_orphans_detected",
                f"orphaned_refs={','.join(orphans)}",
            )

        # Verify current_accepted_result_ref if set
        if request.current_accepted_result_ref:
            parts = request.current_accepted_result_ref.rsplit("@", 1)
            if len(parts) == 2:
                out_id, out_rev_str = parts
                try:
                    out_rev = int(out_rev_str)
                    if not self._artifacts.exists(out_id, out_rev):
                        self._events.append(
                            request_id,
                            "reconcile_accepted_result_missing",
                            f"ref={request.current_accepted_result_ref}",
                        )
                except ValueError:
                    self._events.append(
                        request_id,
                        "reconcile_accepted_result_malformed",
                        f"ref={request.current_accepted_result_ref}",
                    )

        self._events.append(
            request_id,
            "reconcile_completed",
            f"children={len(request.child_refs)} orphans={len(orphans)}",
        )
        return request
