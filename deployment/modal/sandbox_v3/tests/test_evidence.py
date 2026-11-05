"""Host-export and evidence integrity regressions."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from test_contracts import make_request

from modal_build_sandbox.evidence import changed_paths, validate_candidate, write_evidence_zip
from modal_build_sandbox.snapshot import sha256_file


def test_candidate_manifest_bytes_verified(tmp_path):
    req = make_request(tmp_path)
    assert validate_candidate(req).startswith(b"diff --git")
    with pytest.raises(ValueError, match="byte identity"):
        validate_candidate(req.model_copy(update={"candidate_bundle_sha256": "0" * 64}))


def test_complete_delta_includes_unexpected_created_paths():
    before = {"x": {"sha256": "1", "mode": 0o644, "size": 1}}
    after = {"x": {"sha256": "2", "mode": 0o644, "size": 1}, "unadmitted": {"sha256": "3", "mode": 0o644, "size": 1}}
    change = changed_paths(before, after)
    assert [(x.path, x.operation) for x in change] == [("unadmitted", "create"), ("x", "modify")]


def test_private_evidence_archive_has_bound_hashes(tmp_path):
    archive, digest = write_evidence_zip(tmp_path, [("baseline", b"raw stdout", b"raw stderr")], b"{}")
    assert sha256_file(archive) == digest
    with zipfile.ZipFile(archive) as z:
        assert z.read("commands/baseline.stderr") == b"raw stderr"


def test_reject_candidate_bundle_extra_entries(tmp_path):
    req = make_request(tmp_path)
    bundle = Path(req.candidate_bundle_ref)
    with zipfile.ZipFile(bundle, "a") as z:
        z.writestr("execute.sh", "danger")
    altered = req.model_copy(update={"candidate_bundle_sha256": sha256_file(bundle)})
    with pytest.raises(ValueError, match="unsupported entries"):
        validate_candidate(altered)


def test_command_output_cap_is_bounded(tmp_path):
    from modal_build_sandbox.contracts import CommandSpec
    from modal_build_sandbox.evidence import matches_oracle, run_command

    cmd = CommandSpec(command_id="output-limit", argv=("python", "-c", "print('X'*50000)"), purpose="focused")
    result, stdout, stderr = run_command(cmd, tmp_path, tmp_path, 1024)
    assert result.stdout_size <= 1024
    assert result.stdout_truncated
    assert not matches_oracle(cmd, result)


def test_id_path_escape_rejected(tmp_path):
    from pydantic import ValidationError

    from modal_build_sandbox.contracts import SandboxExecutionRequest

    req = make_request(tmp_path)
    with pytest.raises(ValidationError):
        SandboxExecutionRequest.model_validate({**req.model_dump(), "operation_id": "../../outside"})
