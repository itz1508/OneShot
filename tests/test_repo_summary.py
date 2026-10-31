#!/usr/bin/env python3
"""
Tests for OneShot Assignment 00: repo_summary.py

Verifies the script executes, produces correct output, and handles edge cases.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Add src to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from repo_summary import RepoSummaryTool, RepoSummary, GapEntry


class TestRepoSummary:
    """Contract and E2E tests for repo_summary.py."""

    def setup_method(self):
        self.tool = RepoSummaryTool(repo_path=str(REPO_ROOT))

    def test_verify_repository_returns_commit_sha(self):
        """git rev-parse HEAD returns a verifiable commit SHA."""
        commit_sha, is_clean, files = self.tool.verify_repository()
        assert commit_sha, "Commit SHA must not be empty"
        assert len(commit_sha) == 40, f"Commit SHA must be 40 chars, got {len(commit_sha)}"
        assert all(c in "0123456789abcdef" for c in commit_sha), "SHA must be hex"

    def test_working_tree_status(self):
        """git status returns whether working tree is clean or has changes."""
        _, is_clean, _ = self.tool.verify_repository()
        assert isinstance(is_clean, bool), "is_clean must be boolean"

    def test_file_listing_includes_readme(self):
        """Repository file listing includes README.md and .gitignore."""
        _, _, files = self.tool.verify_repository()
        assert "README.md" in files, "README.md must be in file listing"
        assert ".gitignore" in files, ".gitignore must be in file listing"

    def test_gap_matrix_has_12_entries(self):
        """Gap matrix covers all 12 areas (00-11)."""
        _, _, files = self.tool.verify_repository()
        gap_matrix = self.tool.build_gap_matrix(files)
        assert len(gap_matrix) == 12, f"Expected 12 gap entries, got {len(gap_matrix)}"

    def test_gap_matrix_all_classified(self):
        """Each gap entry has a valid action (build/adapt/preserve/retire)."""
        _, _, files = self.tool.verify_repository()
        gap_matrix = self.tool.build_gap_matrix(files)
        valid_actions = {"build", "adapt", "preserve", "retire"}
        for entry in gap_matrix:
            assert entry.action in valid_actions, f"Invalid action: {entry.action}"

    def test_gap_matrix_all_green_initially(self):
        """All gap entries start as GREEN (repo is clean and ready)."""
        _, _, files = self.tool.verify_repository()
        gap_matrix = self.tool.build_gap_matrix(files)
        for entry in gap_matrix:
            assert entry.color_eval == "GREEN", f"{entry.area} should be GREEN initially"

    def test_enumerate_tools_returns_non_empty(self):
        """Available tools list is non-empty (at least git and python)."""
        tools = self.tool.enumerate_tools()
        assert len(tools) >= 2, f"Expected at least 2 tools, got {len(tools)}"
        assert any("git" in t for t in tools), "git must be in tools list"
        assert any("python" in t for t in tools), "python must be in tools list"

    def test_run_produces_complete_summary(self):
        """Full run() produces a RepoSummary with all fields populated."""
        summary = self.tool.run()
        assert isinstance(summary, RepoSummary)
        assert summary.repository == "https://github.com/itz1508/OneShot"
        assert summary.branch == "main"
        assert summary.commit_sha
        assert len(summary.files) > 0
        assert len(summary.gap_matrix) == 12
        assert len(summary.available_tools) > 0
        assert summary.color_eval_baseline in ("GREEN", "YELLOW", "RED")

    def test_json_output_is_valid(self):
        """to_json produces valid JSON with expected fields."""
        summary = self.tool.run()
        json_str = self.tool.to_json(summary)
        parsed = json.loads(json_str)
        assert "repository" in parsed
        assert "commit_sha" in parsed
        assert "gap_matrix" in parsed
        assert len(parsed["gap_matrix"]) == 12
        assert "available_tools" in parsed

    def test_text_output_has_required_sections(self):
        """to_text produces human-readable output with required sections."""
        summary = self.tool.run()
        text = self.tool.to_text(summary)
        assert "OneShot Repository Summary" in text
        assert "Commit SHA:" in text
        assert "Gap Matrix" in text
        assert "Available Tools" in text
        assert "Color Eval Baseline" in text

    def test_script_executes_via_cli(self):
        """Script runs successfully from command line."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "repo_summary.py"), "--output-format", "json"],
            capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT)
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        parsed = json.loads(result.stdout)
        assert parsed["repository"] == "https://github.com/itz1508/OneShot"
        assert len(parsed["gap_matrix"]) == 12

    def test_file_hash_computation(self):
        """compute_file_hash returns valid SHA-256 hex for README.md."""
        h = self.tool.compute_file_hash("README.md")
        assert h, "Hash must not be empty"
        assert len(h) == 64, f"SHA-256 must be 64 chars, got {len(h)}"
        assert all(c in "0123456789abcdef" for c in h), "Hash must be hex"
