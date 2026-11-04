"""Manual real-server integration probe: MCP stdio -> host Research checkpoint.

Run only with a trusted local MCP command and model provider configured.
This verifies actual stage persistence; it never issues Build authorization.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.contracts.research import ResearchRecord
from agent.runtime.canonical_serialization import digest_model
from agent.runtime.controller import Stage
from mvp.research_host import execute_research
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
    print(json.dumps({
        "status": "verified",
        "task_id": task_id,
        "current_stage": checkpoint.current_stage.value,
        "research_artifact_id": ref["artifact_id"],
        "research_digest": ref["artifact_digest"],
        "evidence_count": len(artifact.evidence),
        "unresolved_count": len(artifact.unknowns),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
