#!/usr/bin/env python3
"""
OneShot Assignment 00: Repository Summary and Authority

Executable script that clones/verifies the OneShot repository, produces an
evidence-backed summary, identifies the gap matrix (00-11), classifies each
gap, and establishes the Color Eval baseline.

Usage:
    python repo_summary.py [--repo-path PATH] [--output-format json|text]
"""

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class GapEntry:
    """Single entry in the gap matrix."""

    area: str
    requirement: str
    current_state: str
    action: str  # build, adapt, preserve, retire
    evidence: str
    color_eval: str  # GREEN, YELLOW, RED


@dataclass
class RepoSummary:
    """Complete repository summary output."""

    repository: str
    branch: str
    commit_sha: str
    working_tree_clean: bool
    files: list
    gap_matrix: list
    available_tools: list
    color_eval_baseline: str


class RepoSummaryTool:
    """Executable repo-summary capability for OneShot."""

    REPO_URL = "https://github.com/itz1508/OneShot"
    BRANCH = "main"
    EXPECTED_FILES = ["README.md", ".gitignore"]

    GAP_MATRIX_TEMPLATE = [
        ("00", "Authority: ground decisions in evidence", "build"),
        ("01", "Memory retrieval: restart, resume, retry, no-duplicate", "build"),
        ("02", "Quality Input: validate before execution (Main Agent)", "build"),
        ("03", "Repository search: grounded file inventory", "build"),
        ("04", "Research output: structured evidence-backed findings", "build"),
        ("05", "Research review: evaluate groundedness, contradictions", "build"),
        ("06", "Plan: feasible, dependency-aware planning", "build"),
        ("07", "Fixtures: independent expected results", "build"),
        ("08", "Approval: user-confirmed execution boundary", "build"),
        ("09", "Build: execute through supported tools", "build"),
        ("10", "MCP / tools: reuse supported interfaces", "build"),
        ("11", "E2E: test complete task outcomes", "build"),
    ]

    def __init__(self, repo_path: str | None = None):
        """Initialize with optional repo path (defaults to this script's parent)."""
        if repo_path:
            self.repo_path = Path(repo_path)
        else:
            self.repo_path = Path(__file__).resolve().parent.parent

    def _run_git(self, *args: str) -> str:
        """Run a git command in the repo and return stdout."""
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), *args], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {args} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def verify_repository(self) -> tuple:
        """Verify the repository and return (commit_sha, is_clean, files)."""
        commit_sha = self._run_git("rev-parse", "HEAD")
        status = self._run_git("status", "--porcelain")
        is_clean = len(status) == 0

        # List tracked files
        ls_tree = self._run_git("ls-tree", "-r", "HEAD", "--name-only")
        files = [f for f in ls_tree.splitlines() if f]

        return commit_sha, is_clean, files

    def compute_file_hash(self, filepath: str) -> str:
        """Compute SHA-256 hash of a file in the repo."""
        full_path = self.repo_path / filepath
        if not full_path.exists():
            return ""
        h = hashlib.sha256()
        with open(full_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _evaluate_gap_color(self, area_id: str, area_files: list, all_files: list) -> str:
        """Independently evaluate gap color based on actual evidence.

        GREEN: capability exists with test coverage.
        YELLOW: capability exists but no test coverage.
        RED: capability missing and action is build.
        """
        # Check if test files exist for this area
        test_files = [
            f
            for f in all_files
            if f.startswith("tests/test_")
            and any(kw in f for kw in [area_id, area_id.replace("0", "")])
        ]
        if not area_files:
            return "RED"  # Missing capability
        if not test_files:
            return "YELLOW"  # Exists but untested
        return "GREEN"  # Exists and tested

    def build_gap_matrix(self, files: list) -> list:
        """Build the gap matrix from template and actual repo state."""
        # Check which capabilities exist as source files
        existing_source = [f for f in files if f.endswith(".py") and not f.startswith("tests/")]

        gap_entries = []
        for area_id, requirement, default_action in self.GAP_MATRIX_TEMPLATE:
            # If source files exist for this area, action is adapt; otherwise build
            area_files = [
                f
                for f in existing_source
                if area_id in f or requirement.split(":")[0].lower() in f.lower()
            ]
            action = "adapt" if area_files else default_action
            current = "Partially implemented" if area_files else "Not implemented"
            evidence = f"Files: {area_files}" if area_files else "No source files exist"

            entry = GapEntry(
                area=f"{area_id} — {requirement}",
                requirement=requirement,
                current_state=current,
                action=action,
                evidence=evidence,
                color_eval=self._evaluate_gap_color(area_id, area_files, files),
            )
            gap_entries.append(entry)

        return gap_entries

    def enumerate_tools(self) -> list:
        """Enumerate available built-in tools and existing infrastructure."""
        tools = []

        # Check for git
        try:
            subprocess.run(["git", "--version"], capture_output=True, timeout=5)
            tools.append("git — repository operations, branching, committing")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Check for Python
        tools.append(
            f"python{sys.version_info.major}.{sys.version_info.minor} — scripting and execution"
        )

        # Check for pytest (optional dependency probe).
        import importlib.util

        if importlib.util.find_spec("pytest") is not None:
            tools.append("pytest — test framework")

        # Check for MLflow (available but not mandatory).
        if importlib.util.find_spec("mlflow") is not None:
            tools.append("mlflow — tracking and artifact logging (available, not mandatory)")

        return tools

    def assign_color_eval(self, gap_matrix: list) -> str:
        """Assign overall Color Eval baseline from gap matrix."""
        reds = [e for e in gap_matrix if e.color_eval == "RED"]
        yellows = [e for e in gap_matrix if e.color_eval == "YELLOW"]

        if reds:
            return "RED"
        elif yellows:
            return "YELLOW"
        else:
            return "GREEN"

    def run(self) -> RepoSummary:
        """Execute the full repo-summary and return structured output."""
        commit_sha, is_clean, files = self.verify_repository()

        gap_matrix = self.build_gap_matrix(files)
        available_tools = self.enumerate_tools()
        color_eval = self.assign_color_eval(gap_matrix)

        return RepoSummary(
            repository=self.REPO_URL,
            branch=self.BRANCH,
            commit_sha=commit_sha,
            working_tree_clean=is_clean,
            files=files,
            gap_matrix=[asdict(e) for e in gap_matrix],
            available_tools=available_tools,
            color_eval_baseline=color_eval,
        )

    def to_json(self, summary: RepoSummary) -> str:
        """Serialize summary to JSON."""
        return json.dumps(asdict(summary), indent=2)

    def to_text(self, summary: RepoSummary) -> str:
        """Serialize summary to human-readable text."""
        lines = [
            "OneShot Repository Summary",
            "==========================",
            f"Repository: {summary.repository}",
            f"Branch: {summary.branch}",
            f"Commit SHA: {summary.commit_sha}",
            f"Working tree clean: {summary.working_tree_clean}",
            "",
            f"Files ({len(summary.files)}):",
        ]
        for f in summary.files:
            lines.append(f"  {f}")

        lines.extend(["", f"Gap Matrix ({len(summary.gap_matrix)} areas):"])
        lines.append(f"{'Area':<45} {'State':<20} {'Action':<10} {'Color'}")
        lines.append(f"{'-' * 45} {'-' * 20} {'-' * 10} {'-' * 6}")
        for entry in summary.gap_matrix:
            lines.append(

                    f"{entry['area']:<45} {entry['current_state']:<20} "
                    f"{entry['action']:<10} {entry['color_eval']}"

            )

        lines.extend(["", f"Available Tools ({len(summary.available_tools)}):"])
        for tool in summary.available_tools:
            lines.append(f"  {tool}")

        lines.extend(["", f"Color Eval Baseline: {summary.color_eval_baseline}"])

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="OneShot Repository Summary Tool")
    parser.add_argument(
        "--repo-path", default=None, help="Path to the repository (default: script parent)"
    )
    parser.add_argument(
        "--output-format", choices=["json", "text"], default="text", help="Output format"
    )
    args = parser.parse_args()

    tool = RepoSummaryTool(repo_path=args.repo_path)
    summary = tool.run()

    if args.output_format == "json":
        print(tool.to_json(summary))
    else:
        print(tool.to_text(summary))


if __name__ == "__main__":
    main()
