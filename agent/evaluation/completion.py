"""Completion evaluation of a finished workflow Run.

Reviewer directive: "Complete Audit Discovery, parallel file-task
execution, Build Admission, and completion evaluation." This file is
the last of those four. It composes the already-shipped primitives:

  * ``agent.orchestration.Run``        — the completed run.
  * ``agent.prompt_authoring.LLMJudge`` — grading engine (single or
                                           reference_guided mode).
  * ``agent.contracts.oracles``         — independent references.
  * ``TaskManager``                      — stores the completion receipt
                                           on the parent task.

The evaluator never mutates committed stage records; its output is a
new ``completion_receipt`` block on the Run\\u2019s parent task metadata.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent.orchestration import Run


class CompletionReceiptError(RuntimeError):
    """Raised when the Run cannot be evaluated — e.g. the Run has not
    finished, the Judge rejected the candidate as non-JSON, or the
    budget was exceeded during the evaluation."""


class CompletionReceipt(BaseModel):
    """Frozen record of one completion evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str
    at: float
    mode: str  # "single" or "reference_guided"
    verdict: str  # "pass" | "fail" | "inconclusive"
    critical_failure: bool
    rubric_name: str
    judge_model: str
    spent_usd: float
    task_summary: dict[str, int] = Field(default_factory=dict)
    findings: tuple[dict[str, Any], ...] = ()


class CompletionEvaluator:
    """Grade a finished Run and persist a CompletionReceipt.

    Usage::

        evaluator = CompletionEvaluator(judge=my_llm_judge)
        receipt = evaluator.evaluate(
            run,
            candidate={"summary": "...the artifact's shape..."},
            reference=None,  # or an independently-sourced oracle answer
        )
    """

    def __init__(self, *, judge: Any) -> None:
        self._judge = judge

    def evaluate(
        self,
        run: Run,
        *,
        candidate: dict[str, Any],
        reference: dict[str, Any] | None = None,
    ) -> CompletionReceipt:
        """Grade ``candidate`` with the Judge and persist a receipt.

        * ``reference`` — when supplied, the Judge runs in
          reference_guided mode. Reviewer rule: the reference MUST be
          independently sourced (callers should pull from
          ``agent.contracts.oracles``); the Judge itself refuses when
          candidate is reference.
        * ``run`` MUST have finished (``status()`` in
          ``{"completed", "failed"}``). An un-finished run is refused
          with ``CompletionReceiptError``.
        """
        run_status = run.status()
        if run_status not in ("completed", "failed"):
            raise CompletionReceiptError(
                f"run_not_finished: Run.status()={run_status!r}; refuse "
                "to evaluate a run that has not finished."
            )
        try:
            if reference is None:
                result = self._judge.single(candidate)
                mode = "single"
            else:
                result = self._judge.reference_guided(candidate, reference)
                mode = "reference_guided"
        except Exception as exc:  # noqa: BLE001
            raise CompletionReceiptError(
                f"judge_dispatch_failed: {type(exc).__name__}"
            ) from exc

        task_summary = _summarise_tasks(run)
        receipt = CompletionReceipt(
            plan_id=run.plan_id,
            at=time.time(),
            mode=mode,
            verdict=result.verdict,
            critical_failure=bool(getattr(result, "critical_failure", False)),
            rubric_name=self._judge._rubric.name,
            judge_model=self._judge._model,
            spent_usd=float(self._judge.spent_usd),
            task_summary=task_summary,
            findings=tuple(
                {
                    "criterion": f.criterion,
                    "severity": f.severity,
                    "note": f.note,
                }
                for f in getattr(result, "findings", []) or []
            ),
        )
        self._persist(run, receipt)
        return receipt

    def _persist(self, run: Run, receipt: CompletionReceipt) -> None:
        """Append the receipt to the parent task's metadata.

        Best-effort: a persistence race (TaskManager snapshot changed
        under us) raises CompletionReceiptError. We DO NOT silently
        swallow; this is the final receipt for the Run.
        """
        tm = run._controller.tm
        parent_id = run._parent_task_id
        task = tm.get_task(parent_id)
        if task is None:
            raise CompletionReceiptError(
                f"parent_task_absent: TaskManager row {parent_id!r} not found."
            )
        metadata = dict(task.metadata or {})
        revision = int(metadata.get("revision", 1))
        metadata["revision"] = revision + 1
        trail = list(metadata.get("completion_receipts") or [])
        trail.append(receipt.model_dump())
        metadata["completion_receipts"] = trail
        try:
            tm.set_task_metadata(
                parent_id, metadata, if_revision=revision
            )
        except Exception as exc:  # noqa: BLE001
            raise CompletionReceiptError(
                f"receipt_persist_failed: {type(exc).__name__}"
            ) from exc


def _summarise_tasks(run: Run) -> dict[str, int]:
    """Count per-status Tasks in the Run."""
    counts: dict[str, int] = {}
    for t in run.tasks:
        s = t.status()
        counts[s] = counts.get(s, 0) + 1
    return counts


__all__ = [
    "CompletionEvaluator",
    "CompletionReceipt",
    "CompletionReceiptError",
]
