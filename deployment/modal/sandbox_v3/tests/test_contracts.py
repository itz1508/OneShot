"""Fixture producer + versioned contract regression tests."""

from __future__ import annotations

import difflib
import hashlib
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from modal_build_sandbox.contracts import CandidateManifest, CommandSpec, SandboxExecutionRequest
from modal_build_sandbox.evidence import build_candidate_bundle
from modal_build_sandbox.policy import commands_digest
from modal_build_sandbox.runner import preflight, profile_digest
from modal_build_sandbox.snapshot import archive_directory

FIXTURE = Path(__file__).parent / "fixtures" / "email_normalizer"


def make_request(
    tmp_path: Path,
    *,
    attempt: str = "1",
    replacement: str = "    return value.strip().lower()\n",
    source_override: str | None = None,
) -> SandboxExecutionRequest:
    src = tmp_path / "source"
    src.mkdir(parents=True, exist_ok=True)
    (src / "tests").mkdir(exist_ok=True)
    before = source_override or (FIXTURE / "app.py").read_text()
    (src / "app.py").write_text(before)
    shutil.copyfile(FIXTURE / "test_app.py", src / "tests" / "test_app.py")
    tar = tmp_path / "source.tar"
    archive_hash, tree_hash = archive_directory(src, tar)
    after = "def normalize_email(value: str) -> str:\n" + replacement
    diff = "diff --git a/app.py b/app.py\n" + "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile="a/app.py", tofile="b/app.py"
        )
    )
    patch = diff.encode("utf-8")
    manifest = CandidateManifest(
        operation_id="op-1",
        attempt_id=attempt,
        work_item_id="todo-app",
        task_revision="accepted-r1",
        source_snapshot_sha256=archive_hash,
        declared_paths=("app.py",),
        patch_sha256=hashlib.sha256(patch).hexdigest(),
        patch_bytes=len(patch),
    )
    bundle = tmp_path / f"candidate-{attempt}.zip"
    bundle_hash = build_candidate_bundle(bundle, patch, manifest)
    baseline = CommandSpec(
        command_id="baseline",
        argv=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_app.py"),
        purpose="baseline",
        expected_error="AssertionError",
    )
    focused = CommandSpec(
        command_id="focused",
        argv=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_app.py"),
        purpose="focused",
    )
    broader = CommandSpec(command_id="broader", argv=("python", "-m", "compileall", "-q", "-f", "."), purpose="broader")
    payload = {
        "operation_id": "op-1",
        "attempt_id": attempt,
        "work_item_id": "todo-app",
        "task_revision": "accepted-r1",
        "source_snapshot_ref": str(tar),
        "source_snapshot_sha256": archive_hash,
        "expected_source_tree_digest": tree_hash,
        "image_id": "im-immutable-fixture",
        "sandbox_profile_id": "offline-py311-v3",
        "sandbox_profile_digest": "0" * 64,
        "primary_authorized_path": "app.py",
        "authorized_paths": ("app.py",),
        "expected_preimages": {"app.py": hashlib.sha256(before.encode()).hexdigest()},
        "candidate_bundle_ref": str(bundle),
        "candidate_bundle_sha256": bundle_hash,
        "baseline_expectation": "expected_failure",
        "baseline_checks": (baseline,),
        "focused_checks": (focused,),
        "broader_checks": (broader,),
        "command_plan_sha256": "0" * 64,
        "network_blocked": True,
    }
    draft = SandboxExecutionRequest(**payload)
    return SandboxExecutionRequest(
        **{**payload, "sandbox_profile_digest": profile_digest(draft), "command_plan_sha256": commands_digest(draft)}
    )


def test_fixture_admission_checks(tmp_path):
    req = make_request(tmp_path)
    preflight(req)


def test_reject_unverified_profile(tmp_path):
    req = make_request(tmp_path)
    with pytest.raises(ValueError, match="profile digest"):
        preflight(req.model_copy(update={"sandbox_profile_digest": "f" * 64}))


def test_reject_unsupported_network_and_unknown_fields(tmp_path):
    req = make_request(tmp_path)
    for update in ({"network_blocked": False}, {"contract_version": "2.0"}, {"future_field": True}):
        with pytest.raises(ValidationError):
            SandboxExecutionRequest.model_validate({**req.model_dump(), **update})


def test_reject_aliased_paths(tmp_path):
    req = make_request(tmp_path)
    with pytest.raises(ValidationError):
        SandboxExecutionRequest.model_validate({**req.model_dump(), "authorized_paths": ("app.py", "APP.py")})


def test_reject_wrong_preimage(tmp_path):
    req = make_request(tmp_path)
    with pytest.raises(ValueError, match="preimage"):
        preflight(req.model_copy(update={"expected_preimages": {"app.py": "a" * 64}}))


def test_baseline_failure_requires_oracle(tmp_path):
    req = make_request(tmp_path)
    with pytest.raises(ValidationError):
        SandboxExecutionRequest.model_validate(
            {**req.model_dump(), "baseline_checks": [{**req.baseline_checks[0].model_dump(), "expected_error": None}]}
        )
