"""Minimal reusable scenario runner.

A scenario is a self-contained dict describing:
  * objective (str)
  * requirements, findings, sources, requirement_trace (research-side)
  * plan_milestones, acceptance_criteria, accepted_requirement_ids,
    claim_decisions, gap_findings (plan-side)
  * accepted_milestone_ids, accepted_criterion_ids (build-side)
  * build_runner: {argv: [str], cwd: str_relative_to_workspace,
                   stdin: str|None, expected_exit: int,
                   expected_stdout_contains: [str]}
  * oracle:
      cross_record_errors_expected: [substring] — these must appear
      cross_record_errors_forbidden: [substring] — these must NOT appear
      classification: "VERIFIED" | "PARTIAL" | "BLOCKED"
      plan_decisions_applicability: {USE: int, DO_NOT_USE: int, VALIDATE_FIRST: int}
      build_accepted_milestones: [str] — must be exactly this list after admission

The runner invokes the REAL OneShotController, captures records, runs the
real build artifact via subprocess, validates via Pydantic + resolver, and
compares against the oracle. Returns a ScenarioResult.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure the agent & tools packages are importable (same technique as conftest)
_REPO_ROOT = Path(__file__).resolve().parents[2]
for sub in ("agent", "agent/contracts", "agent/adapters", "tools"):
    sp = str(_REPO_ROOT / sub)
    if sp not in sys.path:
        sys.path.insert(0, sp)
# noqa: E402 justified — path setup must precede imports.
from main import OneShotController, make_hybrid_resolver  # noqa: E402  # type: ignore[import-not-found]
from models import validate_pipeline  # noqa: E402  # type: ignore[import-not-found]


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    research: dict[str, Any]
    plan: dict[str, Any]
    build: dict[str, Any]
    classification: str
    cross_record_errors: list[str] = field(default_factory=list)
    pydantic_errors: list[str] = field(default_factory=list)
    build_exit: int | None = None
    build_stdout: str = ""
    build_stderr: str = ""
    assertions: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    def summary(self) -> str:
        lines = [f"Scenario {self.name}: {'PASS' if self.passed else 'FAIL'}"]
        for a in self.assertions:
            tag = "✓" if a["ok"] else "✗"
            lines.append(f"  {tag} {a['name']}: {a['detail']}")
        if self.cross_record_errors:
            lines.append(f"  cross-record errors: {self.cross_record_errors}")
        return "\n".join(lines)


def _record_assertion(result: ScenarioResult, name: str, ok: bool, detail: str) -> None:
    result.assertions.append({"name": name, "ok": ok, "detail": detail})
    if not ok:
        result.passed = False


def run_scenario(name: str, scenario: dict[str, Any]) -> ScenarioResult:
    """Execute one scenario end-to-end and return a verdict."""
    # Scenario harness is the designated trusted-test-input seam
    # (G08). Flip the env flag so the controller accepts bundle fields
    # like `gap_findings_mark_resolved` that production refuses.
    os.environ["ONESHOT_TRUSTED_TEST_INPUT"] = "1"
    repo_root = str(_REPO_ROOT)
    storage_dir = tempfile.mkdtemp(prefix=f"oneshot-{name}-")
    storage_path = os.path.join(storage_dir, "tasks.json")

    bundle = dict(scenario)  # pass through

    objective = scenario.get("objective") or f"Scenario {name}"

    ctrl = OneShotController(storage_path=storage_path)
    tid = ctrl.start_task(objective)
    r_result = ctrl.research_plan(tid, objective, repo_root, input_bundle=bundle)

    result = ScenarioResult(
        name=name,
        passed=True,
        research=r_result.get("record", {}),
        plan={},
        build={},
        classification="UNKNOWN",
    )

    if r_result.get("errors"):
        result.classification = "BLOCKED"
        result.pydantic_errors = r_result["errors"]
        _record_assertion(
            result, "research_pydantic", False, f"research errors: {r_result['errors']}"
        )
        return _finalize(result, scenario)

    research = r_result["record"]
    ev_idx = r_result["evidence_index"]
    p_result = ctrl.review_research_plan(tid, research, ev_idx, repo_root, input_bundle=bundle)

    if p_result.get("errors"):
        result.plan = p_result.get("record", {})
        result.classification = "BLOCKED"
        result.pydantic_errors = p_result["errors"]
        _record_assertion(result, "plan_pydantic", False, f"plan errors: {p_result['errors']}")
        return _finalize(result, scenario)

    plan = p_result["record"]
    result.plan = plan
    b_result = ctrl.build_plan(tid, plan, ev_idx, repo_root, input_bundle=bundle)

    if b_result.get("errors"):
        result.build = b_result.get("record", {})
        result.classification = "BLOCKED"
        result.pydantic_errors = b_result["errors"]
        _record_assertion(result, "build_pydantic", False, f"build errors: {b_result['errors']}")
        return _finalize(result, scenario)

    build = b_result["record"]
    result.build = build

    # Run REAL build artifact when the scenario asked for one.
    br = scenario.get("build_runner")
    if br is not None:
        proc = subprocess.run(
            br["argv"],
            cwd=br.get("cwd") or repo_root,
            input=br.get("stdin"),
            capture_output=True,
            text=True,
            timeout=br.get("timeout", 10),
        )
        result.build_exit = proc.returncode
        result.build_stdout = proc.stdout
        result.build_stderr = proc.stderr

    # Resolver-backed cross-record validation (D07 — real evidence).
    resolver = make_hybrid_resolver(ev_idx, Path(repo_root))
    cross_errors = validate_pipeline(research, plan, build, resolve=resolver)
    result.cross_record_errors = cross_errors

    # Overall classification: BLOCKED if pydantic errors already fired above;
    # otherwise VERIFIED iff cross-record errors are empty AND oracle matches,
    # PARTIAL otherwise.
    result.classification = "VERIFIED" if not cross_errors else "PARTIAL"

    return _finalize(result, scenario)


def _finalize(result: ScenarioResult, scenario: dict[str, Any]) -> ScenarioResult:
    oracle = scenario.get("oracle", {})
    cre_expected = oracle.get("cross_record_errors_expected") or []
    cre_forbidden = oracle.get("cross_record_errors_forbidden") or []
    classification_expected = oracle.get("classification")

    joined = " || ".join(result.cross_record_errors)
    for needle in cre_expected:
        _record_assertion(
            result,
            f"cross_error_contains[{needle}]",
            needle in joined,
            f"'{needle}' in errors: {joined}" if needle in joined else f"missing in {joined!r}",
        )
    for needle in cre_forbidden:
        _record_assertion(
            result,
            f"cross_error_absent[{needle}]",
            needle not in joined,
            f"'{needle}' absent" if needle not in joined else f"forbidden in {joined!r}",
        )

    if classification_expected is not None:
        _record_assertion(
            result,
            "classification",
            result.classification == classification_expected,
            f"got {result.classification}; expected {classification_expected}",
        )

    # Oracle: plan.claim_decisions applicability counts.
    pda = oracle.get("plan_decisions_applicability")
    if pda is not None:
        counts: dict[str, int] = {"USE": 0, "DO_NOT_USE": 0, "VALIDATE_FIRST": 0}
        for d in result.plan.get("claim_decisions") or []:
            m = d.get("applicability")
            if m in counts:
                counts[m] += 1
        _record_assertion(
            result,
            "plan_decisions_counts",
            counts == pda,
            f"got {counts}; expected {pda}",
        )

    # Oracle: Build admission filter — accepted milestones after filtering.
    bam = oracle.get("build_accepted_milestones")
    if bam is not None:
        got = (result.build.get("plan_input") or {}).get("accepted_milestone_ids") or []
        _record_assertion(
            result,
            "build_accepted_milestones",
            list(got) == list(bam),
            f"got {got}; expected {bam}",
        )

    # Oracle: real build runner outcomes.
    br = scenario.get("build_runner")
    oracle_build = oracle.get("build_runner") or {}
    if br is not None:
        if "expected_exit" in oracle_build:
            _record_assertion(
                result,
                "build_runner_exit",
                result.build_exit == oracle_build["expected_exit"],
                f"got exit={result.build_exit}; "
                f"expected={oracle_build['expected_exit']}; stderr={result.build_stderr[:200]!r}",
            )
        for s in oracle_build.get("stdout_contains") or []:
            _record_assertion(
                result,
                f"build_runner_stdout[{s}]",
                s in result.build_stdout,
                f"'{s}' {'in' if s in result.build_stdout else 'not in'} stdout",
            )

    return result


def dumps(result: ScenarioResult) -> str:
    return json.dumps(
        {
            "name": result.name,
            "passed": result.passed,
            "classification": result.classification,
            "assertions": result.assertions,
            "cross_record_errors": result.cross_record_errors,
            "pydantic_errors": result.pydantic_errors,
            "build_exit": result.build_exit,
        },
        indent=2,
    )


# Allow `python -m tests.scenarios._runner <scenario-module>` smoke runs.
if __name__ == "__main__":  # pragma: no cover - manual dev-time smoke
    with contextlib.suppress(ImportError):
        import importlib

        if len(sys.argv) > 1:
            mod = importlib.import_module(sys.argv[1])
            name = getattr(mod, "NAME", sys.argv[1])
            scenario = mod.scenario()
            r = run_scenario(name, scenario)
            print(r.summary())
            print(dumps(r))
            sys.exit(0 if r.passed else 1)
