"""Scanner exact digest tests — SCN01-SCN10."""

from agent.contracts.common import ArtifactRef
from agent.contracts.research import Requirement, ResearchRecord
from agent.contracts.scanner import ScannerCapabilityID, ScannerOutcome, ScannerRequest
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.scanner_gateway import ScannerGateway


def make_ref(aid="cand-001", rev=1, digest=None):
    return ArtifactRef(
        artifact_id=aid,
        artifact_revision=rev,
        artifact_digest=digest or "a" * 64,
        contract_id="planning",
        contract_version="1.0",
        serializer_profile="rfc8785-jcs-sha256-v1",
    )


def make_store_with_artifact(tmp_path, artifact_id="cand-001", rev=1):
    """Create an ArtifactStore with a stored artifact, return (store, digest)."""
    store = ArtifactStore(tmp_path)
    record = ResearchRecord(
        task_id="task-001",
        run_id="run-001",
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="user",
                original_wording="need",
                statement="implement",
            ),
        ),
    )
    digest = store.put_immutable(record, artifact_id, rev, "planning", "1.0")
    return store, digest


class TestScannerGateway:
    def test_scan_passes_when_all_capabilities_registered(self, tmp_path):
        """SCN01: Scan passes when all capabilities have detectors that pass."""
        store, digest = make_store_with_artifact(tmp_path)
        gw = ScannerGateway(artifact_store=store)
        for c in ["syntax", "imports", "types"]:
            gw.register_detector(c, lambda _: ())
        ref = make_ref(digest=digest)
        result = gw.scan_exact(ref, "repo-001", ("syntax", "imports", "types"))
        assert result.outcome == ScannerOutcome.PASS

    def test_scan_blocked_when_capability_missing(self, tmp_path):
        """SCN02: Scan blocked when capability not registered."""
        store, _ = make_store_with_artifact(tmp_path)
        gw = ScannerGateway(artifact_store=store)
        gw.register_detector("syntax", lambda _: ())
        ref = make_ref(digest=store.get_digest("cand-001", 1))
        result = gw.scan_exact(ref, "repo-001", ("syntax", "security"))
        assert result.outcome == ScannerOutcome.BLOCKED
        assert "security" in result.capabilities_not_checked

    def test_scan_checked_capabilities_listed(self, tmp_path):
        """SCN03: Checked capabilities listed in result."""
        store, digest = make_store_with_artifact(tmp_path)
        gw = ScannerGateway(artifact_store=store)
        for c in ["syntax", "imports"]:
            gw.register_detector(c, lambda _: ())
        ref = make_ref(digest=digest)
        result = gw.scan_exact(ref, "repo-001", ("syntax", "imports"))
        assert result.outcome == ScannerOutcome.PASS
        assert "syntax" in result.capabilities_checked
        assert "imports" in result.capabilities_checked

    def test_scan_unchecked_capabilities_listed(self):
        """SCN04: Unchecked capabilities listed with limitation reasons."""
        gw = ScannerGateway()
        gw.register_detector("syntax", lambda _: ())
        ref = make_ref()
        result = gw.scan_exact(ref, "repo-001", ("syntax", "types"))
        assert "types" in result.capabilities_not_checked
        assert len(result.limitation_reasons) > 0

    def test_supported_capabilities(self):
        """SCN05: Supported capabilities are readable."""
        gw = ScannerGateway()
        gw.register_capability("syntax")
        gw.register_capability("imports")
        assert "syntax" in gw.supported_capabilities
        assert "imports" in gw.supported_capabilities

    def test_scan_result_has_request_id(self, tmp_path):
        """SCN06: Scan result has a request ID."""
        store, digest = make_store_with_artifact(tmp_path)
        gw = ScannerGateway(artifact_store=store)
        gw.register_detector("syntax", lambda _: ())
        ref = make_ref(digest=digest)
        result = gw.scan_exact(ref, "repo-001", ("syntax",))
        assert result.request_id

    def test_scan_with_empty_capabilities(self):
        """SCN07: Scan with no requested capabilities passes."""
        gw = ScannerGateway()
        ref = make_ref()
        result = gw.scan_exact(ref, "repo-001", ())
        assert result.outcome == ScannerOutcome.PASS

    def test_capability_ids_are_str_enum(self):
        """SCN08: Scanner capability IDs are string enums."""
        assert ScannerCapabilityID.SYNTAX.value == "syntax"
        assert ScannerCapabilityID.IMPORTS.value == "imports"
        assert ScannerCapabilityID.SECURITY.value == "security"

    def test_scan_exact_digest_in_request(self):
        """SCN09: Scanner request carries exact candidate digest."""
        request = ScannerRequest(
            task_id="task-001",
            candidate_artifact=make_ref(digest="f" * 64),
            specification_revision=1,
            specification_digest="f" * 64,
            repository_source="repo-001",
            requested_capabilities=("syntax",),
        )
        assert request.specification_digest == "f" * 64

    def test_scan_finding_shape(self):
        """SCN10: Scanner finding has required fields."""
        from agent.contracts.scanner import ScannerFinding

        finding = ScannerFinding(
            finding_id="find-001",
            capability="syntax",
            severity="warning",
            message="unused import",
        )
        assert finding.capability == "syntax"
