"""Surface explicit unfinished implementation markers without inferring runtime failure."""

from __future__ import annotations

import tokenize
from pathlib import Path

from agent.audit.core import Finding, evidence, python_files


def scan_completeness(root: Path, scope: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in python_files(root, scope):
        with path.open("rb") as source:
            for token in tokenize.tokenize(source.readline):
                if token.type != tokenize.COMMENT:
                    continue
                if any(marker in token.string.upper() for marker in ("TODO", "FIXME")):
                    findings.append(
                        evidence(
                            root, path, token.start[0], "UNRESOLVED_COMMENT", "completeness", "low",
                            "Source comment requests follow-up; verify relevance against accepted intent.",
                        )
                    )
    return findings
