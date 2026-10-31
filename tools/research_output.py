#!/usr/bin/env python3
"""
OneShot Assignment 04: Research Output Package

Structured research output with provenance (file path, line range, commit SHA),
independent validation values, contradictions, and open questions.
"""

import hashlib
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Provenance:
    """Source provenance for a finding."""
    file_path: str
    line_start: int
    line_end: int
    commit_sha: str
    content_snippet: str = ""


@dataclass
class Finding:
    """A single research finding with provenance."""
    id: str
    description: str
    provenance: list = field(default_factory=list)
    validation_value: Optional[str] = None
    is_contradiction: bool = False


@dataclass
class ResearchOutput:
    """Complete research output package."""
    findings: list = field(default_factory=list)
    contradictions: list = field(default_factory=list)
    open_questions: list = field(default_factory=list)
    plan_candidate: dict = field(default_factory=dict)
    commit_sha: str = ""


class ResearchOutputBuilder:
    """Builds structured research output with provenance."""

    def __init__(self, repo_path: Optional[str] = None):
        from pathlib import Path
        self.repo_path = Path(repo_path) if repo_path else Path(__file__).resolve().parent.parent

    def _get_commit_sha(self) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()

    def create_provenance(self, file_path: str, line_start: int, line_end: int, snippet: str = "") -> Provenance:
        """Create provenance with file path, line range, and commit SHA."""
        return Provenance(
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            commit_sha=self._get_commit_sha(),
            content_snippet=snippet[:200],
        )

    def add_finding(self, output: ResearchOutput, finding_id: str, description: str,
                    provenance: list, validation_value: str = None) -> Finding:
        """Add a finding with provenance and independent validation value."""
        finding = Finding(
            id=finding_id,
            description=description,
            provenance=provenance,
            validation_value=validation_value,
            is_contradiction=False,
        )
        output.findings.append(finding)
        return finding

    def add_contradiction(self, output: ResearchOutput, finding_id: str, description: str,
                          provenance: list) -> Finding:
        """Add a contradiction finding."""
        finding = Finding(
            id=finding_id,
            description=description,
            provenance=provenance,
            is_contradiction=True,
        )
        output.contradictions.append(finding)
        return finding

    def add_open_question(self, output: ResearchOutput, question: str, context: str = ""):
        """Add an open question."""
        output.open_questions.append({"question": question, "context": context})

    def set_plan_candidate(self, output: ResearchOutput, plan: dict):
        """Set the plan candidate from research findings."""
        output.plan_candidate = plan

    def finalize(self, output: ResearchOutput) -> ResearchOutput:
        """Finalize research output with commit SHA."""
        output.commit_sha = self._get_commit_sha()
        return output

    def to_dict(self, output: ResearchOutput) -> dict:
        """Serialize to dict."""
        return asdict(output)
