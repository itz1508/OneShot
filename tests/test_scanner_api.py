"""Scanner API behavior, read-only discovery and guarded effects."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.scanner import (
    ScanError,
    scan_edit_change,
    scan_edit_write,
    scan_filesystems,
    scan_match_variable,
)


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    p = tmp_path / "example.py"
    p.write_text("Builder Discovery\nbuilder_discovery\nkeep Builder alone\n", encoding="utf-8")
    (tmp_path / "binary.bin").write_bytes(b"\xff\xfe")
    subprocess.run(["git", "-C", str(tmp_path), "add", "example.py", "binary.bin"], check=True)
    return tmp_path


RULES = [
    {"name": "role", "pattern": "Builder Discovery", "replacement": "Audit Discovery"},
    {"name": "identifier", "pattern": "builder_discovery", "replacement": "audit_discovery"},
]


def test_inventory_reports_files_without_writes(sample: Path) -> None:
    before = (sample / "example.py").read_bytes()
    inventory = scan_filesystems(sample)
    assert inventory["count"] == 2
    assert all(x["status"] == "file" for x in inventory["files"])
    assert (sample / "example.py").read_bytes() == before


def test_match_extracts_name_location_and_preserves_original(sample: Path) -> None:
    hits = scan_match_variable(sample, RULES)
    assert hits["count"] == 2
    assert [(h["name"], h["line"], h["column"]) for h in hits["matches"]] == [
        ("role", 1, 1), ("identifier", 2, 1),
    ]
    assert (sample / "example.py").read_text().startswith("Builder Discovery")
    assert [x["path"] for x in hits["skipped"]] == ["binary.bin"]


def test_change_previews_all_patterns_and_is_read_only(sample: Path) -> None:
    plan = scan_edit_change(sample, RULES)
    assert plan["count"] == 1
    change = plan["changes"][0]
    assert change["path"] == "example.py"
    assert change["after_content"] == "Audit Discovery\naudit_discovery\nkeep Builder alone\n"
    assert change["before_sha256"] == hashlib.sha256(
        (sample / "example.py").read_bytes()
    ).hexdigest()
    assert "-Builder Discovery" in change["diff"]
    assert (sample / "example.py").read_text().startswith("Builder Discovery")


def test_write_requires_authorization_and_explicit_path(sample: Path) -> None:
    change = scan_edit_change(sample, RULES)["changes"]
    with pytest.raises(ScanError, match="Build authorization"):
        scan_edit_write(sample, change, allowed_paths=["example.py"])
    with pytest.raises(ScanError, match="not approved"):
        scan_edit_write(sample, change, authorized=True, allowed_paths=["binary.bin"])
    assert (sample / "example.py").read_text().startswith("Builder Discovery")


def test_write_applies_exact_preview_and_reports_sha(sample: Path) -> None:
    change = scan_edit_change(sample, RULES)["changes"]
    receipt = scan_edit_write(sample, change, allowed_paths=["example.py"], authorized=True)
    assert receipt["count"] == 1
    assert receipt["written"][0]["sha256"] == change[0]["after_sha256"]
    assert (sample / "example.py").read_text().startswith("Audit Discovery")


def test_stale_content_blocks_write(sample: Path) -> None:
    change = scan_edit_change(sample, RULES)["changes"]
    (sample / "example.py").write_text("new unrelated edit\n")
    with pytest.raises(ScanError, match="stale source"):
        scan_edit_write(sample, change, allowed_paths=["example.py"], authorized=True)
    assert (sample / "example.py").read_text() == "new unrelated edit\n"


def test_tampered_preview_blocks_write(sample: Path) -> None:
    change = scan_edit_change(sample, RULES)["changes"]
    change[0]["after_content"] = "tampered"
    with pytest.raises(ScanError, match="invalid proposed content digest"):
        scan_edit_write(sample, change, allowed_paths=["example.py"], authorized=True)


def test_overlap_fails_closed(sample: Path) -> None:
    with pytest.raises(ScanError, match="overlapping"):
        scan_edit_change(sample, [
            {"name": "a", "pattern": "Builder Discovery", "replacement": "Audit Discovery"},
            {"name": "b", "pattern": "Discovery", "replacement": "D"},
        ])


def test_untracked_opt_in(sample: Path) -> None:
    (sample / "untracked.txt").write_text("Builder Discovery\n")
    assert scan_match_variable(sample, RULES)["count"] == 2
    assert scan_match_variable(sample, RULES, include_untracked=True)["count"] == 3
    with pytest.raises(ScanError, match="not tracked"):
        scan_edit_change(sample, RULES, paths=["untracked.txt"])


def test_symlink_never_followed(sample: Path, tmp_path: Path) -> None:
    other = tmp_path.parent / (tmp_path.name + "-external")
    other.write_text("Builder Discovery")
    link = sample / "link.py"
    try:
        link.symlink_to(other)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    subprocess.run(["git", "-C", str(sample), "add", "link.py"], check=True)
    results = scan_match_variable(sample, RULES)
    assert results["count"] == 2
    assert "link.py" in {x["path"] for x in results["skipped"]}


def test_cli_match_change_and_guarded_write(sample: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

    def cli(op: str, data: dict, apply: bool = False) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable, "-m", "tools.scanner", op, "--repo-root", str(sample)]
        if apply:
            cmd.append("--apply")
        return subprocess.run(cmd, input=json.dumps(data), capture_output=True, text=True, env=env)

    preview = cli("change", {"rules": RULES})
    assert preview.returncode == 0, preview.stderr
    changes = json.loads(preview.stdout)["result"]["changes"]
    assert cli("write", {"changes": changes, "allowed_paths": ["example.py"]}).returncode == 2
    done = cli("write", {"changes": changes, "allowed_paths": ["example.py"]}, apply=True)
    assert done.returncode == 0, done.stderr
    assert (sample / "example.py").read_text().startswith("Audit Discovery")
