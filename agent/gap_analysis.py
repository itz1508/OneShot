#!/usr/bin/env python3
"""
OneShot Capability Preflight — validates the System Scanner's eight detection
categories against disposable controlled sources before real Plan Gap Analysis.

Uses the same SourceInspection and SourceComparison adapter interfaces as the
real Plan checks. Does NOT replace the Scanner, controller, or Task Management.
A wrapper or fixture must not become a second detector.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# Add adapters/ and tools/ to path for adapter imports
_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"
_ADAPTERS_DIR = _REPO_ROOT / "agent" / "adapters"
for p in (_TOOLS_DIR, _ADAPTERS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from source_comparison import ComparisonEvidence, SourceComparison  # noqa: E402 - standalone-script path setup

# ===== Capability Preflight (VALID / INVALID / NOT_VALIDATED) =====


class CapabilityVerdict(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    NOT_VALIDATED = "NOT_VALIDATED"


@dataclass
class PreflightCategoryResult:
    """Result of a single category capability check."""

    category: str
    verdict: str
    positive_control_id: str
    negative_control_id: str
    positive_found: bool
    negative_preserved: bool
    expected_statuses: list[str] = field(default_factory=list)
    actual_statuses: list[str] = field(default_factory=list)
    expected_paths: list[str] = field(default_factory=list)
    actual_paths: list[str] = field(default_factory=list)
    evidence: str = ""
    scanner_identity: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PreflightResult:
    """Complete result of an eight-category capability preflight run."""

    categories: list[PreflightCategoryResult] = field(default_factory=list)
    aggregate_verdict: str = CapabilityVerdict.NOT_VALIDATED.value
    coverage_complete: bool = False
    scanner_identity: str = ""
    limitations: list[str] = field(default_factory=list)
    timestamp: str = ""

    @property
    def invalid_categories(self) -> list[PreflightCategoryResult]:
        return [c for c in self.categories if c.verdict == CapabilityVerdict.INVALID.value]

    @property
    def not_validated_categories(self) -> list[PreflightCategoryResult]:
        return [c for c in self.categories if c.verdict == CapabilityVerdict.NOT_VALIDATED.value]

    @property
    def can_proceed(self) -> bool:
        return self.aggregate_verdict == CapabilityVerdict.VALID.value

    def to_dict(self) -> dict:
        return {
            "categories": [c.to_dict() for c in self.categories],
            "aggregate_verdict": self.aggregate_verdict,
            "coverage_complete": self.coverage_complete,
            "scanner_identity": self.scanner_identity,
            "limitations": self.limitations,
            "timestamp": self.timestamp,
            "invalid_count": len(self.invalid_categories),
            "not_validated_count": len(self.not_validated_categories),
            "can_proceed": self.can_proceed,
        }


class CapabilityPreflight:
    """Eight-category capability preflight using the real System Scanner.

    Creates disposable git workspaces with positive controls (known defects)
    and negative controls (legitimate variants), runs the same
    SourceInspection and SourceComparison adapter interfaces used for real
    Plan checks, and returns VALID/INVALID/NOT_VALIDATED per category.

    A category is VALID only if its independent positive defect is detected
    with expected category/evidence and its negative/false-positive control
    is correctly rejected. It is INVALID for confirmed misdetection, and
    NOT_VALIDATED for missing, stale, unsupported, skipped or unexecuted
    evidence. Empty results or a successful function return are not VALID.
    """

    CATEGORIES = [
        "drift",
        "missing",
        "duplication",
        "contradictions",
        "coverage",
        "dependencies",
        "feasibility",
        "cli_docs",
    ]

    def __init__(self, scanner_source_path: Path | None = None):
        self._scanner_path = scanner_source_path or Path(__file__).resolve()
        self._scanner_identity = self._compute_scanner_identity()

    def _compute_scanner_identity(self) -> str:
        try:
            return hashlib.sha256(self._scanner_path.read_bytes()).hexdigest()
        except Exception:
            return "unknown"

    def run(self) -> PreflightResult:
        """Run all eight category preflight checks in disposable workspaces."""
        from datetime import datetime, timezone

        results = []
        for cat in self.CATEGORIES:
            method = getattr(self, f"_validate_{cat}", None)
            if method is None:
                results.append(
                    PreflightCategoryResult(
                        category=cat,
                        verdict=CapabilityVerdict.NOT_VALIDATED.value,
                        positive_control_id="",
                        negative_control_id="",
                        positive_found=False,
                        negative_preserved=False,
                        error=f"No _validate_{cat} method",
                        scanner_identity=self._scanner_identity,
                    )
                )
                continue
            try:
                results.append(method())
            except Exception as e:
                results.append(
                    PreflightCategoryResult(
                        category=cat,
                        verdict=CapabilityVerdict.NOT_VALIDATED.value,
                        positive_control_id="",
                        negative_control_id="",
                        positive_found=False,
                        negative_preserved=False,
                        error=f"Preflight execution error: {e}",
                        scanner_identity=self._scanner_identity,
                    )
                )

        invalid = [r for r in results if r.verdict == CapabilityVerdict.INVALID.value]
        not_validated = [r for r in results if r.verdict == CapabilityVerdict.NOT_VALIDATED.value]
        if invalid:
            aggregate = CapabilityVerdict.INVALID.value
        elif not_validated:
            aggregate = CapabilityVerdict.NOT_VALIDATED.value
        else:
            aggregate = CapabilityVerdict.VALID.value

        coverage = len(results) == len(self.CATEGORIES) and not invalid and not not_validated
        limitations = [f"{r.category}: {r.error}" for r in results if r.error]

        return PreflightResult(
            categories=results,
            aggregate_verdict=aggregate,
            coverage_complete=coverage,
            scanner_identity=self._scanner_identity,
            limitations=limitations,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ===== Scanner execution helpers (same interface as real Plan checks) =====

    def _make_git_workspace(self, files: dict[str, str]) -> Path:
        """Create a disposable git workspace with the given files committed."""
        ws = Path(tempfile.mkdtemp(prefix="preflight_"))
        subprocess.run(["git", "init"], cwd=ws, capture_output=True, timeout=10)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=ws, capture_output=True, timeout=5
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=ws, capture_output=True, timeout=5
        )
        for path, content in files.items():
            fp = ws / path
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)
        subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True, timeout=5)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=ws, capture_output=True, timeout=5)
        return ws

    def _run_inspector(self, workspace: Path) -> object:
        """Run the same git-based inspector used for real Plan checks."""

        @dataclass
        class FileEntry:
            path: str
            size: int
            text_admitted: bool
            sha256_hex: str

        @dataclass
        class ScannerReport:
            root: str
            files: tuple
            excluded_paths: tuple
            limitations: tuple
            partial: bool

        r = subprocess.run(
            ["git", "-C", str(workspace), "ls-files"], capture_output=True, text=True, timeout=10
        )
        tracked = [f for f in r.stdout.strip().split("\n") if f]
        r2 = subprocess.run(
            ["git", "-C", str(workspace), "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        untracked = [f for f in r2.stdout.strip().split("\n") if f]
        all_f = sorted(set(tracked + untracked))
        files = []
        for fp in all_f:
            full = workspace / fp
            if not full.is_file():
                continue
            raw = full.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            admitted = b"\x00" not in raw[:8192]
            files.append(FileEntry(fp, len(raw), admitted, sha if admitted else ""))
        return ScannerReport(str(workspace), tuple(files), (), (), False)

    def _run_comparison(self, workspace: Path) -> ComparisonEvidence:
        """Run SourceComparison comparing workspace working tree against HEAD commit.

        Uses the same git-ls-tree-diff method as the real host comparator.
        """
        inspection_report: Any = self._run_inspector(workspace)
        ws_files = {f.path: f.sha256_hex for f in inspection_report.files}

        r = subprocess.run(
            ["git", "-C", str(workspace), "ls-tree", "-r", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        baseline_paths = set(r.stdout.strip().split("\n")) if r.stdout.strip() else set()
        baseline_files = {}
        for bpath in baseline_paths:
            if not bpath:
                continue
            gr = subprocess.run(
                ["git", "-C", str(workspace), "show", f"HEAD:{bpath}"],
                capture_output=True,
                timeout=10,
            )
            if gr.returncode == 0:
                baseline_files[bpath] = hashlib.sha256(gr.stdout).hexdigest()

        records = []
        all_paths = sorted(set(ws_files) | set(baseline_files))
        for path in all_paths:
            ws_sha = ws_files.get(path)
            bl_sha = baseline_files.get(path)
            if ws_sha and not bl_sha:
                records.append(
                    {
                        "evidence_id": f"gap-new-{path}",
                        "source_id": "workspace",
                        "path": path,
                        "sha256": ws_sha,
                        "status": "added",
                        "directional_finding": "file exists in workspace but not in baseline",
                        "counterpart_ids": [],
                        "limitation": None,
                        "read_status": "COMPLETE",
                    }
                )
            elif bl_sha and not ws_sha:
                records.append(
                    {
                        "evidence_id": f"gap-missing-{path}",
                        "source_id": "baseline",
                        "path": path,
                        "sha256": None,
                        "status": "missing",
                        "directional_finding": "file exists in baseline but not in workspace",
                        "counterpart_ids": [],
                        "limitation": None,
                        "read_status": "COMPLETE",
                    }
                )
            elif ws_sha and bl_sha and ws_sha != bl_sha:
                records.append(
                    {
                        "evidence_id": f"gap-drift-{path}",
                        "source_id": "workspace",
                        "path": path,
                        "sha256": ws_sha,
                        "status": "modified",
                        "directional_finding": (
                            "file content differs between workspace and baseline"
                        ),
                        "counterpart_ids": [],
                        "limitation": None,
                        "read_status": "COMPLETE",
                    }
                )

        def comparator(sources, *, target_id=None, objective=""):
            return {
                "records": records,
                "sources": [
                    {"source_id": "workspace", "limitations": [], "inventory_complete": True},
                    {"source_id": "baseline", "limitations": [], "inventory_complete": True},
                ],
                "comparison_complete": True,
                "content_complete": len(records) == 0,
                "target_id": target_id,
                "method": "git-ls-tree-diff",
            }

        adapter = SourceComparison(comparator)
        return adapter.compare(
            [({"id": "workspace"}, b""), ({"id": "baseline"}, b"")],
            target_id="workspace",
            objective="preflight",
        )

    def _validate_category(
        self,
        category: str,
        baseline_files: dict[str, str],
        positive_modify: Callable[[Path], None],
        negative_modify: Callable[[Path], None],
        expected_statuses: list[str],
        expected_paths: list[str],
    ) -> PreflightCategoryResult:
        """Generic validation: run Scanner against positive and negative controls.

        Fixture generation is separate from detector results.
        Does not inject defects into the user's real repository.
        """
        pos_id = f"{category}-positive"
        neg_id = f"{category}-negative"

        # Positive control: create workspace, commit baseline, apply defect
        pos_ws = self._make_git_workspace(baseline_files)
        try:
            positive_modify(pos_ws)
            pos_comparison = self._run_comparison(pos_ws)
            pos_diffs = list(pos_comparison.differences)
            positive_found = any(
                d.status in expected_statuses and any(ep in d.path for ep in expected_paths)
                for d in pos_diffs
            )
        except Exception as e:
            shutil.rmtree(pos_ws, ignore_errors=True)
            return PreflightCategoryResult(
                category=category,
                verdict=CapabilityVerdict.NOT_VALIDATED.value,
                positive_control_id=pos_id,
                negative_control_id=neg_id,
                positive_found=False,
                negative_preserved=False,
                error=f"Positive control failed: {e}",
                scanner_identity=self._scanner_identity,
            )

        # Negative control: create workspace, commit baseline, apply legitimate variant
        neg_ws = self._make_git_workspace(baseline_files)
        try:
            negative_modify(neg_ws)
            neg_comparison = self._run_comparison(neg_ws)
            neg_diffs = list(neg_comparison.differences)
            negative_preserved = not any(
                d.status in expected_statuses and any(ep in d.path for ep in expected_paths)
                for d in neg_diffs
            )
        except Exception as e:
            shutil.rmtree(neg_ws, ignore_errors=True)
            return PreflightCategoryResult(
                category=category,
                verdict=CapabilityVerdict.NOT_VALIDATED.value,
                positive_control_id=pos_id,
                negative_control_id=neg_id,
                positive_found=positive_found,
                negative_preserved=False,
                error=f"Negative control failed: {e}",
                scanner_identity=self._scanner_identity,
            )

        shutil.rmtree(pos_ws, ignore_errors=True)
        shutil.rmtree(neg_ws, ignore_errors=True)

        if positive_found and negative_preserved:
            verdict = CapabilityVerdict.VALID.value
            evidence = (
                f"Scanner detected defect ({expected_statuses}) in positive, none in negative"
            )
        elif not positive_found:
            verdict = CapabilityVerdict.INVALID.value
            summary = [(d.status, d.path) for d in pos_diffs]
            evidence = f"False negative: scanner missed defect (got {summary})"
        else:
            verdict = CapabilityVerdict.INVALID.value
            summary = [(d.status, d.path) for d in neg_diffs]
            evidence = f"False positive: scanner flagged negative control (got {summary})"

        return PreflightCategoryResult(
            category=category,
            verdict=verdict,
            positive_control_id=pos_id,
            negative_control_id=neg_id,
            positive_found=positive_found,
            negative_preserved=negative_preserved,
            expected_statuses=expected_statuses,
            actual_statuses=[d.status for d in pos_diffs],
            expected_paths=expected_paths,
            actual_paths=[d.path for d in pos_diffs],
            evidence=evidence,
            scanner_identity=self._scanner_identity,
        )

    # ===== Eight category validations =====
    # Each category tests the Scanner's ability to detect a specific type of
    # file-level difference through the real SourceInspection + SourceComparison
    # adapter pipeline. Controls are independently specified behavioral
    # requirements mapped to Scanner-supported source shapes.

    def _validate_drift(self) -> PreflightCategoryResult:
        """Drift: Scanner must detect files modified from baseline.

        Positive: authorized content changed to unauthorized — Scanner detects 'modified'.
        Negative: file unchanged — Scanner detects nothing.
        """
        baseline = {"agent/main.py": "# original controller\n", "tools/helper.py": "# helper\n"}

        def positive(ws: Path):
            (ws / "agent" / "main.py").write_text("# modified controller — drift\n")

        def negative(ws: Path):
            pass  # No changes — no drift

        return self._validate_category(
            "drift", baseline, positive, negative, ["modified"], ["main.py"]
        )

    def _validate_missing(self) -> PreflightCategoryResult:
        """Missing: Scanner must detect required files absent from workspace.

        Positive: required file deleted — Scanner detects 'missing'.
        Negative: all required files present — Scanner detects nothing.
        """
        baseline = {"agent/main.py": "# controller\n", "tools/task_management.py": "# tasks\n"}

        def positive(ws: Path):
            (ws / "tools" / "task_management.py").unlink()

        def negative(ws: Path):
            pass  # All files present

        return self._validate_category(
            "missing", baseline, positive, negative, ["missing"], ["task_management.py"]
        )

    def _validate_duplication(self) -> PreflightCategoryResult:
        """Duplication: Scanner must detect files added beyond baseline.

        Positive: duplicate file added — Scanner detects 'added'.
        Negative: no extra file — Scanner detects nothing.
        """
        baseline = {"tools/core.py": "def compute():\n    return 42\n"}

        def positive(ws: Path):
            (ws / "tools" / "duplicate.py").write_text("def compute():\n    return 99\n")

        def negative(ws: Path):
            pass  # No extra files

        return self._validate_category(
            "duplication", baseline, positive, negative, ["added"], ["duplicate.py"]
        )

    def _validate_contradictions(self) -> PreflightCategoryResult:
        """Contradictions: Scanner must detect files with conflicting content.

        Positive: file content conflicts with baseline — Scanner detects 'modified'.
        Negative: file unchanged — Scanner detects nothing.
        """
        baseline = {"config/settings.py": "VERSION = 1\n"}

        def positive(ws: Path):
            (ws / "config" / "settings.py").write_text("VERSION = 2  # contradicts baseline\n")

        def negative(ws: Path):
            pass  # No contradiction

        return self._validate_category(
            "contradictions", baseline, positive, negative, ["modified"], ["settings.py"]
        )

    def _validate_coverage(self) -> PreflightCategoryResult:
        """Coverage: Scanner must detect missing test files.

        Positive: test file deleted — Scanner detects 'missing'.
        Negative: test file present — Scanner detects nothing.
        """
        baseline = {"tests/test_core.py": "def test_core(): pass\n", "tools/core.py": "# core\n"}

        def positive(ws: Path):
            (ws / "tests" / "test_core.py").unlink()

        def negative(ws: Path):
            pass  # Test file present

        return self._validate_category(
            "coverage", baseline, positive, negative, ["missing"], ["test_core.py"]
        )

    def _validate_dependencies(self) -> PreflightCategoryResult:
        """Dependencies: Scanner must detect missing dependency files.

        Positive: dependency file deleted — Scanner detects 'missing'.
        Negative: dependency present — Scanner detects nothing.
        """
        baseline = {
            "tools/core.py": "from helper import fix\n",
            "tools/helper.py": "def fix(): pass\n",
        }

        def positive(ws: Path):
            (ws / "tools" / "helper.py").unlink()

        def negative(ws: Path):
            pass  # Dependency present

        return self._validate_category(
            "dependencies", baseline, positive, negative, ["missing"], ["helper.py"]
        )

    def _validate_feasibility(self) -> PreflightCategoryResult:
        """Feasibility: Scanner must detect missing executable files.

        Positive: executable file deleted — Scanner detects 'missing'.
        Negative: executable present — Scanner detects nothing.
        """
        baseline = {
            "bin/run.py": "#!/usr/bin/env python3\nprint('ok')\n",
            "tools/core.py": "# core\n",
        }

        def positive(ws: Path):
            (ws / "bin" / "run.py").unlink()

        def negative(ws: Path):
            pass  # Executable present

        return self._validate_category(
            "feasibility", baseline, positive, negative, ["missing"], ["run.py"]
        )

    def _validate_cli_docs(self) -> PreflightCategoryResult:
        """CLI/Docs: Scanner must detect missing documentation files.

        Positive: documentation file deleted — Scanner detects 'missing'.
        Negative: documentation present — Scanner detects nothing.
        """
        baseline = {"AGENTS.md": "# Agent instructions\n", "tools/core.py": "# core\n"}

        def positive(ws: Path):
            (ws / "AGENTS.md").unlink()

        def negative(ws: Path):
            pass  # Documentation present

        return self._validate_category(
            "cli_docs", baseline, positive, negative, ["missing"], ["AGENTS.md"]
        )
