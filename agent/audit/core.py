"""Read-only, evidence-grounded audit capability runner; not a workflow controller."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    capability: str
    code: str
    status: str
    severity: str
    path: str
    line: int
    message: str
    evidence_digest: str


@dataclass(frozen=True)
class AuditResult:
    root: str
    scope: str
    requested_capabilities: tuple[str, ...]
    executed_capabilities: tuple[str, ...]
    findings: tuple[Finding, ...]
    limitations: tuple[str, ...]
    disposition: str
    request: str = ""

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        findings = data["findings"]
        assert isinstance(findings, tuple)
        for finding in findings:
            identity = "|".join((finding["capability"], finding["path"], str(finding["line"]), finding["code"]))
            finding["finding_id"] = "AUD-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        return data


def evidence(
    root: Path,
    path: Path,
    line: int,
    code: str,
    capability: str,
    severity: str,
    message: str,
    status: str = "candidate",
) -> Finding:
    """Capture file digest so a later host can reconcile stale findings."""
    data = path.read_bytes()
    return Finding(
        capability,
        code,
        status,
        severity,
        path.relative_to(root).as_posix(),
        line,
        message,
        hashlib.sha256(data).hexdigest(),
    )


def python_files(root: Path, scope: Path) -> Iterable[Path]:
    """Walk only ordinary files; never recurse through directory symlinks."""
    for path in sorted(scope.rglob("*.py")):
        if any(
            part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in path.relative_to(root).parts
        ):
            continue
        if path.is_file() and not path.is_symlink():
            yield path


Scanner = Callable[[Path, Path], list[Finding]]


def scan(root: Path, scope: str = ".", capabilities: tuple[str, ...] = (), request: str = "") -> AuditResult:
    from agent.audit.completeness import scan_completeness
    from agent.audit.contracts import scan_contracts
    from agent.audit.dependencies import scan_dependencies
    from agent.audit.frontend import scan_frontend
    from agent.audit.integration import scan_integration
    from agent.audit.paths import scan_paths
    from agent.audit.recovery import scan_recovery
    from agent.audit.security import scan_security
    from agent.audit.state import scan_state
    from agent.audit.verification import scan_verification
    from agent.audit.wiring import scan_wiring

    scanners: dict[str, Scanner] = {
        "paths": scan_paths,
        "wiring": scan_wiring,
        "security": scan_security,
        "contracts": scan_contracts,
        "completeness": scan_completeness,
        "verification": scan_verification,
        "frontend": scan_frontend,
        "state": scan_state,
        "dependencies": scan_dependencies,
        "integration": scan_integration,
        "recovery": scan_recovery,
    }
    requested = capabilities or tuple(scanners)
    unknown = sorted(set(requested) - set(scanners))
    if unknown:
        raise ValueError(f"unknown audit capabilities: {', '.join(unknown)}")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository root must be a directory")
    target = (root / scope).resolve(strict=True)
    if not target.is_relative_to(root):
        raise ValueError("audit scope escapes repository root")
    if not target.is_dir():
        raise ValueError("audit scope must be a directory")
    findings: list[Finding] = []
    limitations = [
        "Static observations are not runtime or E2E verification.",
        "Only Python and literal frontend API route patterns are inspected; dynamic wiring requires runtime evidence.",
    ]
    executed: list[str] = []
    for name in dict.fromkeys(requested):
        try:
            findings.extend(scanners[name](root, target))
            executed.append(name)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            limitations.append(f"{name} not completed: {type(exc).__name__}")
    findings.sort(key=lambda f: (f.capability, f.path, f.line, f.code))
    if len(executed) != len(set(requested)):
        disposition = "blocked"
    elif findings:
        disposition = "findings_open"
    else:
        disposition = "not_e2e_verified"
    return AuditResult(
        str(root),
        target.relative_to(root).as_posix(),
        requested,
        tuple(executed),
        tuple(findings),
        tuple(limitations),
        disposition,
        request,
    )
