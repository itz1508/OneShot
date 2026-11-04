"""Manual real-server integration probe: MCP stdio -> host Research checkpoint.

Run only with a trusted local MCP command and model provider configured.
This verifies actual stage persistence; it never issues Build authorization.
"""

from __future__ import annotations

import argparse
import json
import os
from hashlib import sha256
from pathlib import Path

from agent.contracts.research import ResearchRecord
from agent.runtime.canonical_serialization import digest_model
from agent.runtime.controller import Stage
from mvp.research_host import configured_evidence_sources, execute_research
from mvp.service import MVPService


def main() -> int:
    parser = argparse.ArgumentParser(description="OneShot MCP Research end-to-end probe")
    parser.add_argument("--state-root", type=Path, default=Path(".oneshot-probe-state"))
    parser.add_argument("--prompt", default="Inspect the authorized repository evidence and report limitations.")
    args = parser.parse_args()

    service = MVPService(args.state_root)
    task = service.create(args.prompt)
    task_id = str(task["task_id"])
    outcome = execute_research(service, task_id)
    checkpoint = service.host.get_state(task_id)
    if checkpoint is None or checkpoint.current_stage is not Stage.AUDIT_DISCOVERY:
        raise RuntimeError("Research did not advance through the host checkpoint")
    ref = outcome["artifact_ref"]
    assert isinstance(ref, dict)
    research_bytes = service.artifacts.get_verified(str(ref["artifact_id"]), 1)
    artifact = ResearchRecord.model_validate_json(research_bytes)
    if digest_model(artifact) != ref["artifact_digest"]:
        raise RuntimeError("Persisted Research digest mismatch")
    sources = configured_evidence_sources()
    evidence_verified = False
    if sources is not None:
        root = Path(os.environ["MCP_WORKSPACE_ROOT"]).resolve(strict=True)
        workspace_paths = sources["workspace_paths"]
        if not isinstance(workspace_paths, list):
            raise RuntimeError("Invalid host evidence selection")
        for relative in workspace_paths:
            if not isinstance(relative, str):
                raise RuntimeError("Invalid host evidence path")
            target = root / relative
            # This probe is for an operator-trusted workspace, not untrusted filesystem races.
            if target.is_symlink() or not target.resolve(strict=True).is_relative_to(root):
                raise RuntimeError("Unsafe source in independent evidence verification")
            digest = sha256(target.read_bytes()).hexdigest()
            if not any(
                item.location == relative
                and item.source == "configured_workspace"
                and item.content_digest == digest
                and item.status == "valid"
                for item in artifact.evidence
            ):
                raise RuntimeError(f"Missing independently verified evidence for {relative}")
        evidence_verified = True
    print(
        json.dumps(
            {
                "status": "verified",
                "task_id": task_id,
                "current_stage": checkpoint.current_stage.value,
                "research_artifact_id": ref["artifact_id"],
                "research_digest": ref["artifact_digest"],
                "evidence_count": len(artifact.evidence),
                "evidence_verified": evidence_verified,
                "unresolved_count": len(artifact.unknowns),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
