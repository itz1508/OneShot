#!/usr/bin/env python3
"""
OneShot Assignment 05: Research Review (Optional)

Optional review that evaluates groundedness, completeness, and contradictions.
User retains authority over research findings. Review is optional, not binding.
Color Eval: GREEN = all checks pass, YELLOW = partial, RED = critical failure.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ColorEval(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class ReviewResult:
    """Result of research review."""
    color: str
    groundedness_pass: bool
    completeness_pass: bool
    contradictions_found: int
    findings_with_provenance: int
    findings_without_provenance: int
    details: list = field(default_factory=list)


class ResearchReview:
    """Optional research review. User retains authority over findings."""

    def review(self, research_output: dict) -> ReviewResult:
        """Review research output for groundedness, completeness, contradictions."""
        findings = research_output.get("findings", [])
        contradictions = research_output.get("contradictions", [])

        details = []
        with_prov = 0
        without_prov = 0

        for f in findings:
            # Handle both dict and dataclass objects
            if isinstance(f, dict):
                prov = f.get("provenance")
                fid = f.get("id", "?")
                val = f.get("validation_value")
            else:
                prov = getattr(f, "provenance", None)
                fid = getattr(f, "id", "?")
                val = getattr(f, "validation_value", None)
            
            if prov:
                with_prov += 1
            else:
                without_prov += 1
                details.append(f"Finding {fid} lacks provenance")
            
            if not val:
                details.append(f"Finding {fid} lacks validation value")

        groundedness = with_prov > 0 and without_prov == 0
        completeness = len(findings) > 0 and all((f.get("validation_value") if isinstance(f, dict) else getattr(f, "validation_value", None)) for f in findings)
        contradictions_count = len(contradictions)

        # Critical: any finding without provenance is a substantive issue
        if without_prov > 0:
            details.append(f"{without_prov} findings lack provenance — not grounded")
        if not completeness:
            details.append("Some findings lack independent validation values")
        if contradictions_count > 0:
            details.append(f"{contradictions_count} contradictions found")

        if groundedness and completeness and contradictions_count == 0:
            color = ColorEval.GREEN
        elif without_prov == 0 and (not completeness or contradictions_count > 0):
            color = ColorEval.YELLOW
        else:
            color = ColorEval.RED  # Critical: ungrounded findings

        return ReviewResult(
            color=color.value,
            groundedness_pass=groundedness,
            completeness_pass=completeness,
            contradictions_found=contradictions_count,
            findings_with_provenance=with_prov,
            findings_without_provenance=without_prov,
            details=details,
        )
