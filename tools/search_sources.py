#!/usr/bin/env python3
"""Repository file inventory via `git ls-tree` and `git grep`.

Reusable primitive: `SearchSources(repo_path)` enumerates every tracked
file at HEAD, filters by extension or glob, and reads file info (type,
size, line count, 200-char content summary). Used by
`agent.main.OneShotController.research_plan` to build the SHA-256
evidence index at Research stage entry, and by the baseline
`tests/test_research_plan_build.py::TestSearchSources` suite.

All operations shell out to `git` (no custom filesystem walker) so the
inventory is always what git-grep / rg would see — the same view that
the agent-read deny list in `.agents/settings.json` operates against.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileEntry:
    """A single file in the repository inventory."""

    path: str
    file_type: str
    size: int
    line_count: int
    content_summary: str


class SearchSources:
    """Repository search using built-in tools (os, subprocess/git)."""

    def __init__(self, repo_path: str | None = None):
        self.repo_path = Path(repo_path) if repo_path else Path(__file__).resolve().parent.parent

    def _run_git(self, *args: str) -> str:
        """Run git command using built-in subprocess."""
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), *args], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {args} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def list_files(self) -> list[str]:
        """List all tracked files using git ls-tree (built-in git)."""
        output = self._run_git("ls-tree", "-r", "HEAD", "--name-only")
        return [f for f in output.splitlines() if f]

    def search_by_pattern(self, pattern: str) -> list[str]:
        """Search files by glob pattern using built-in Path.glob."""
        matched = []
        for f in self.list_files():
            if pattern.lower() in f.lower():
                matched.append(f)
        return matched

    def search_by_extension(self, ext: str) -> list[str]:
        """Search files by extension."""
        if not ext.startswith("."):
            ext = "." + ext
        return [f for f in self.list_files() if f.endswith(ext)]

    def get_file_info(self, filepath: str) -> FileEntry:
        """Get file info: type, size, line count, content summary."""
        full_path = self.repo_path / filepath
        if not full_path.exists():
            raise FileNotFoundError(f"{filepath} not found")

        ext = Path(filepath).suffix
        type_map = {
            ".py": "python",
            ".md": "markdown",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".gitignore": "git",
            ".sh": "shell",
        }
        file_type = type_map.get(ext, "unknown")

        size = full_path.stat().st_size
        content = full_path.read_text(errors="replace")
        line_count = len(content.splitlines())
        summary = content[:200].replace("\n", " ").strip()

        return FileEntry(
            path=filepath,
            file_type=file_type,
            size=size,
            line_count=line_count,
            content_summary=summary,
        )

    def search_archive_branch(self, branch_name: str) -> list[str]:
        """Search files in an archive branch (read-only)."""
        try:
            output = self._run_git("ls-tree", "-r", branch_name, "--name-only")
            return [f for f in output.splitlines() if f]
        except RuntimeError:
            return []

    def build_inventory(self) -> list[FileEntry]:
        """Build complete file inventory with types, sizes, summaries."""
        files = self.list_files()
        inventory = []
        for f in files:
            try:
                info = self.get_file_info(f)
                inventory.append(info)
            except FileNotFoundError:
                continue
        return inventory

    def find_by_content(self, keyword: str) -> list[str]:
        """Find files containing a keyword using git grep (built-in)."""
        try:
            output = self._run_git("grep", "-l", keyword)
            return [f for f in output.splitlines() if f]
        except RuntimeError:
            return []
