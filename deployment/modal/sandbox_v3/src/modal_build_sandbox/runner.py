"""One isolated Sandbox per attempt; authoritative import is explicitly out of scope."""

from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .applicator import apply_changes, prepare_changes
from .contracts import (
    Cleanup,
    Diagnostic,
    Outcome,
    SandboxCommandResult,
    SandboxExecutionRequest,
    SandboxExecutionResult,
)
from .evidence import changed_paths, matches_oracle, run_command, validate_candidate, write_evidence_zip
from .policy import canonical_digest, check_commands
from .recovery import AttemptStore
from .snapshot import archive_directory, extract_verified_tar, scan_tree, sha256_file


def profile_digest(req: SandboxExecutionRequest) -> str:
    """Coherence digest only; not a trusted host authorization receipt."""
    return canonical_digest(
        {
            "image_id": req.image_id,
            "profile_id": req.sandbox_profile_id,
            "limits": req.limits.model_dump(mode="json"),
            "network_blocked": True,
        }
    )


def preflight(req: SandboxExecutionRequest) -> None:
    if req.sandbox_profile_digest != profile_digest(req):
        raise ValueError("sandbox profile digest mismatch")
    if (
        Path(req.source_snapshot_ref).stat().st_size > req.limits.max_archive_bytes
        or sha256_file(req.source_snapshot_ref) != req.source_snapshot_sha256
    ):
        raise ValueError("source archive digest mismatch")
    check_commands(req)
    validate_candidate(req)
    with tempfile.TemporaryDirectory(prefix="oneshot-source-preflight-") as tmp:
        target = Path(tmp) / "source"
        snapshot = extract_verified_tar(
            Path(req.source_snapshot_ref),
            target,
            archive_digest=req.source_snapshot_sha256,
            expected_tree_digest=req.expected_source_tree_digest,
            max_archive_bytes=req.limits.max_archive_bytes,
            max_extracted_bytes=req.limits.max_extracted_bytes,
        )
        for rel, expected in req.expected_preimages.items():
            observed = snapshot.get(rel)
            if (observed["sha256"] if observed else None) != expected:
                raise ValueError("preflight preimage mismatch")


def _run_worker(req: SandboxExecutionRequest, root: Path, output: Path, sandbox_id: str) -> SandboxExecutionResult:
    """Trusted worker, run *inside* isolated Modal container. Never claim host receipt."""
    output.mkdir(exist_ok=True, parents=True)
    patch = validate_candidate(req)
    before = extract_verified_tar(
        Path(req.source_snapshot_ref),
        root,
        archive_digest=req.source_snapshot_sha256,
        expected_tree_digest=req.expected_source_tree_digest,
        max_archive_bytes=req.limits.max_archive_bytes,
        max_extracted_bytes=req.limits.max_extracted_bytes,
    )
    baselines: list[SandboxCommandResult] = []
    focused: list[SandboxCommandResult] = []
    broad: list[SandboxCommandResult] = []
    records: list[tuple[str, bytes, bytes]] = []
    problems: list[str] = []
    status = Outcome.COMPLETED
    diagnostic = Diagnostic.VALID
    effect = "none"

    for category, spec_list, into in (
        ("baseline", req.baseline_checks, baselines),
        ("focused", req.focused_checks, focused),
        ("broader", req.broader_checks, broad),
    ):
        if category == "focused":
            if problems:
                break
            pending_changes = prepare_changes(root, patch, req.authorized_paths, req.expected_preimages)
            apply_changes(root, pending_changes)
            effect = "patch applied in disposable workspace; pending independent host check"
        if category == "broader" and problems:
            break
        for c in spec_list:
            command_result, stdout, stderr = run_command(c, root, output, req.limits.max_output_bytes)
            into.append(command_result)
            records.append((c.command_id, stdout, stderr))
            if not matches_oracle(c, command_result):
                problems.append(f"{category} check {c.command_id} did not match its oracle")
                break

    after = scan_tree(root, max_bytes=req.limits.max_extracted_bytes)
    changes = changed_paths(before, after)
    unauthorized = sorted({x.path for x in changes} - set(req.authorized_paths))
    if len(changes) > req.limits.max_changed_paths or unauthorized:
        problems.append("unexpected modified paths or changed-path limit exceeded")
        diagnostic = Diagnostic.NOT_VALID
        status = Outcome.BLOCKED
    elif problems:
        status, diagnostic = Outcome.FAILED, Diagnostic.NOT_VALID
    after_tar = output / "after.tar"
    after_digest, output_tree = archive_directory(root, after_tar, max_bytes=req.limits.max_archive_bytes)
    result = SandboxExecutionResult(
        operation_id=req.operation_id,
        attempt_id=req.attempt_id,
        work_item_id=req.work_item_id,
        sandbox_id=sandbox_id,
        image_id=req.image_id,
        sandbox_profile_id=req.sandbox_profile_id,
        sandbox_profile_digest=req.sandbox_profile_digest,
        input_archive_sha256=req.source_snapshot_sha256,
        input_tree_digest=req.expected_source_tree_digest,
        candidate_bundle_sha256=req.candidate_bundle_sha256,
        command_plan_sha256=req.command_plan_sha256,
        baseline_results=tuple(baselines),
        focused_results=tuple(focused),
        broader_results=tuple(broad),
        changed_paths=changes,
        output_tree_digest=output_tree,
        execution_status=status,
        diagnostic_status=diagnostic,
        effect_reconciliation=effect,
        after_archive_ref=str(after_tar),
        after_archive_sha256=after_digest,
        detail="; ".join(problems)[:500],
    )
    if req.baseline_expectation == "not_required" and baselines:
        raise ValueError("unexpected baseline")
    bundle, digest = write_evidence_zip(output, records, result.model_dump_json().encode())
    result = result.model_copy(update={"evidence_bundle_ref": bundle, "evidence_bundle_sha256": digest})
    (output / "result.json").write_text(result.model_dump_json(), encoding="utf-8")
    return result


def sandbox_worker(request_path: str) -> None:
    """Modal command entry. Fixed source path is part of trusted adapter, not agent input."""
    req = SandboxExecutionRequest.model_validate_json(Path(request_path).read_text(encoding="utf-8"))
    req = req.model_copy(
        update={"source_snapshot_ref": "/input/source.tar", "candidate_bundle_ref": "/input/bundle.zip"}
    )
    _run_worker(
        req, Path("/workspace"), Path("/output"), Path("/input/sandbox-id.txt").read_text(encoding="utf-8").strip()
    )


class StandaloneRunner:
    def __init__(self, runtime: Any, attempts: AttemptStore, output_root: Path):
        self.runtime, self.attempts, self.output_root = runtime, attempts, Path(output_root)
        if self.output_root.is_symlink():
            raise ValueError("output root must not be a symlink")
        self.output_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.output_root, 0o700)

    @staticmethod
    def _sandbox_name(req: SandboxExecutionRequest) -> str:
        h = hashlib.sha256(f"{req.operation_id}:{req.attempt_id}".encode()).hexdigest()[:24]
        return f"oneshot-v3-{h}"

    def execute(self, req: SandboxExecutionRequest) -> SandboxExecutionResult:
        preflight(req)  # Must happen before remote resource creation or any effects.
        name = self._sandbox_name(req)
        self.attempts.start(req.operation_id, req.attempt_id, name)
        previous = "INTENT_RECORDED"
        sb: Any = None
        output = self.output_root / req.operation_id / req.attempt_id
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        result: SandboxExecutionResult | None = None
        cleanup = Cleanup.NOT_CREATED
        try:
            sb = self.runtime.create(req, name)
            sid = str(sb.object_id)
            self.attempts.transition(req.operation_id, req.attempt_id, previous, "SANDBOX_CREATED", sandbox_id=sid)
            previous = "SANDBOX_CREATED"
            self.runtime.upload(sb, req)
            self.attempts.transition(req.operation_id, req.attempt_id, previous, "INPUT_UPLOADED")
            previous = "INPUT_UPLOADED"
            # Worker may apply candidate effects. Persist intent *before* dispatch.
            self.attempts.transition(req.operation_id, req.attempt_id, previous, "PRE_EFFECT")
            previous = "PRE_EFFECT"
            rc = self.runtime.execute(sb, req.limits.lifetime_seconds)
            if rc != 0:
                raise RuntimeError("sandbox worker execution failed; effects require reconciliation")
            self.attempts.transition(req.operation_id, req.attempt_id, previous, "EFFECT_OBSERVED")
            previous = "EFFECT_OBSERVED"
            result_path, after_tar, evidence_zip = self.runtime.download(sb, output)
            self.attempts.transition(req.operation_id, req.attempt_id, previous, "OUTPUT_EXPORTED")
            previous = "OUTPUT_EXPORTED"
            reported = SandboxExecutionResult.model_validate_json(result_path.read_text(encoding="utf-8"))
            self._verify_export(req, reported, after_tar, evidence_zip, sid)
            self.attempts.transition(req.operation_id, req.attempt_id, previous, "HOST_STAGING_VERIFIED")
            previous = "HOST_STAGING_VERIFIED"
            result = reported.model_copy(
                update={
                    "after_archive_ref": str(after_tar),
                    "evidence_bundle_ref": str(evidence_zip),
                    "effect_reconciliation": "host independently verified sandbox export",
                }
            )
        except Exception as exc:
            # Scheduling may have succeeded even if create() lost its response.
            # Absence of a local handle is not proof the remote Sandbox never existed.
            next_state = "UNCERTAIN"
            self.attempts.transition(req.operation_id, req.attempt_id, previous, next_state, detail=type(exc).__name__)
            previous = next_state
            raise
        finally:
            if sb is not None:
                try:
                    self.runtime.terminate(sb)
                    cleanup = Cleanup.CONFIRMED
                except Exception:
                    cleanup = Cleanup.FAILED
            if previous in {"HOST_STAGING_VERIFIED", "BLOCKED_PRE_EFFECT", "UNCERTAIN"}:
                # Uncertain effects remain uncertain; termination does not prove reconciliation.
                new_state = (
                    "TERMINATION_RECORDED"
                    if previous == "HOST_STAGING_VERIFIED" and cleanup == Cleanup.CONFIRMED
                    else previous
                )
                if new_state != previous:
                    self.attempts.transition(req.operation_id, req.attempt_id, previous, new_state)
        if result is None:
            raise RuntimeError("no independently verified result")
        return result.model_copy(update={"cleanup_state": cleanup})

    def inspect_attempt(self, operation_id: str, attempt_id: str) -> dict[str, object]:
        """Read-only inspection; existence/poll alone never authorizes a retry or marks completion."""
        record = self.attempts.get(operation_id, attempt_id)
        try:
            sandbox = self.runtime.recover(
                str(record["sandbox_name"]), str(record["sandbox_id"]) if record["sandbox_id"] else None
            )
            observed = sandbox.poll()
            observation = "running" if observed is None else "terminated"
        except Exception as exc:
            observation = "lookup_uncertain:" + type(exc).__name__
        return {
            "operation_id": operation_id,
            "attempt_id": attempt_id,
            "persisted_state": record["state"],
            "sandbox_id": record["sandbox_id"],
            "sandbox_name": record["sandbox_name"],
            "remote_observation": observation,
            "retry_authorized": False,
        }

    def _verify_export(
        self,
        req: SandboxExecutionRequest,
        result: SandboxExecutionResult,
        after_tar: Path,
        evidence_zip: Path,
        sandbox_id: str,
    ) -> None:
        if (
            result.operation_id,
            result.attempt_id,
            result.work_item_id,
            result.sandbox_id,
            result.image_id,
            result.sandbox_profile_id,
            result.sandbox_profile_digest,
            result.input_archive_sha256,
            result.input_tree_digest,
            result.candidate_bundle_sha256,
            result.command_plan_sha256,
        ) != (
            req.operation_id,
            req.attempt_id,
            req.work_item_id,
            sandbox_id,
            req.image_id,
            req.sandbox_profile_id,
            req.sandbox_profile_digest,
            req.source_snapshot_sha256,
            req.expected_source_tree_digest,
            req.candidate_bundle_sha256,
            req.command_plan_sha256,
        ):
            raise ValueError("sandbox result binding mismatch")
        if not result.after_archive_sha256 or sha256_file(after_tar) != result.after_archive_sha256:
            raise ValueError("exported archive digest mismatch")
        if not result.evidence_bundle_sha256 or sha256_file(evidence_zip) != result.evidence_bundle_sha256:
            raise ValueError("evidence bundle digest mismatch")
        if evidence_zip.stat().st_size > req.limits.max_evidence_bytes:
            raise ValueError("evidence exceeds retention limit")
        # Verify private raw evidence matches each digest/length claimed by the sandbox.
        with zipfile.ZipFile(evidence_zip) as bundle:
            claims = result.baseline_results + result.focused_results + result.broader_results
            expected_entries = {"result.json"} | {
                f"commands/{claim.command_id}.{kind}" for claim in claims for kind in ("stdout", "stderr")
            }
            if set(bundle.namelist()) != expected_entries or len(bundle.namelist()) != len(expected_entries):
                raise ValueError("evidence inventory mismatch")
            for claim in claims:
                for kind in ("stdout", "stderr"):
                    raw = bundle.read(f"commands/{claim.command_id}.{kind}")
                    if len(raw) != getattr(claim, f"{kind}_size") or hashlib.sha256(raw).hexdigest() != getattr(
                        claim, f"{kind}_sha256"
                    ):
                        raise ValueError("raw command evidence does not match reported digest")
        patch = validate_candidate(req)
        with tempfile.TemporaryDirectory(prefix="oneshot-independent-") as work:
            base = Path(work)
            before = extract_verified_tar(
                Path(req.source_snapshot_ref),
                base / "before",
                archive_digest=req.source_snapshot_sha256,
                expected_tree_digest=req.expected_source_tree_digest,
                max_archive_bytes=req.limits.max_archive_bytes,
                max_extracted_bytes=req.limits.max_extracted_bytes,
            )
            if not result.output_tree_digest:
                raise ValueError("missing output tree identity")
            after = extract_verified_tar(
                after_tar,
                base / "after",
                archive_digest=result.after_archive_sha256,
                expected_tree_digest=result.output_tree_digest,
                max_archive_bytes=req.limits.max_archive_bytes,
                max_extracted_bytes=req.limits.max_extracted_bytes,
            )
            observed = changed_paths(before, after)
            if observed != result.changed_paths:
                raise ValueError("independent changed-path manifest mismatch")
            unauthorized = {change.path for change in observed if change.path not in req.authorized_paths}
            too_many = len(observed) > req.limits.max_changed_paths
            if unauthorized or too_many:
                # A correctly rejected negative case is evidence, not an accepted patch.
                if result.execution_status != Outcome.BLOCKED or result.diagnostic_status != Diagnostic.NOT_VALID:
                    raise ValueError("unauthorized change falsely accepted")
            else:
                # For any non-blocked result, reproduce candidate bytes, not just path names.
                expected = prepare_changes(base / "before", patch, req.authorized_paths, req.expected_preimages)
                apply_changes(base / "before", expected)
                if scan_tree(base / "before") != after:
                    raise ValueError("export does not match candidate patch bytes")
        specs = req.baseline_checks + req.focused_checks + req.broader_checks
        results = result.baseline_results + result.focused_results + result.broader_results
        if len({r.command_id for r in results}) != len(results) or any(
            r.command_id not in {c.command_id for c in specs} for r in results
        ):
            raise ValueError("unknown or duplicated command result")
        for item in results:
            spec = next(c for c in specs if c.command_id == item.command_id)
            if item.argv_digest != canonical_digest(spec.argv):
                raise ValueError("command execution binding mismatch")
        if result.execution_status == Outcome.COMPLETED:
            if len(result.focused_results) != len(req.focused_checks) or len(result.broader_results) != len(
                req.broader_checks
            ):
                raise ValueError("missing successful verification commands")
            if not all(matches_oracle(c, next(r for r in results if r.command_id == c.command_id)) for c in specs):
                raise ValueError("claimed success contradicts command oracle")
