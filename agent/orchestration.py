"""Public workflow-orchestration surface for OneShot.

Reviewer directive on PR #10 (post-rename): expose a public
``agent.start()`` entry point that returns a ``Run`` object whose
lifecycle (``pause``, ``resume``, ``status``) and task iteration
(``for task in run.tasks: task.status()``) are the agreed public
API. Keep ``TaskManager`` as the internal state and persistence
owner; keep the existing specialist components (``OneShotController``
and friends) as internal workflow orchestration.

The exact interface the reviewer asked for:

    import agent

    run = agent.start(plan_id)
    run.pause()
    run.resume()
    run.status()
    for task in run.tasks:
        print(task.status())

Design notes:

* ``plan_id`` is a flexible input — it accepts either a Pydantic
  ``RunPlan`` object (built in-process) or a mapping with the same
  shape. One task per planned file, matching the 1-file = 1-task
  convention the Plan enforces.
* ``Run`` and ``Task`` are thin orchestration objects that delegate
  durable state to the internal ``TaskManager``. They own only the
  in-process lifecycle flag (``paused``) and a stable mapping from
  ``Task`` identifiers to ``TaskManager`` task ids.
* Pause/resume is advisory for the current turn: the workflow is
  still synchronous, so ``pause()`` sets a flag that is honoured on
  the next scheduled transition. The underlying ``TaskManager``
  snapshot continues to be the source of truth — a Run is just a
  per-process handle on a workflow in progress.
* The classes are deliberately framework-light. No new persistence
  layer, no new permission authority, no new provider path.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Lazy imports to keep agent.orchestration import-cheap for the public
# surface. ``OneShotController`` lives in ``agent.__main__`` (the CLI
# entry point) and pulls in TaskManager + specialists; we only touch
# it when a Run is actually created.


TaskStatus = Literal["pending", "running", "paused", "completed", "failed"]
RunStatus = Literal["pending", "running", "paused", "completed", "failed"]


class PlannedFileOperation(BaseModel):
    """One planned file operation inside a RunPlan.

    One task per planned file is the agreed convention. ``path`` is
    the file this task's single operation targets; ``operation`` is a
    short verb (``create`` / ``edit`` / ``remove`` / etc.) that the
    orchestrator records on the task metadata for the UI.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    operation: str = "edit"
    note: str = ""


class RunPlan(BaseModel):
    """A frozen description of what a Run should do.

    A RunPlan carries:
      * ``plan_id`` — a stable id for the workflow (free-form string
        or UUID). The Run exposes it via ``run.plan_id``.
      * ``objective`` — the user-facing one-line goal.
      * ``files`` — the planned file operations, in execution order.
        Independent operations may run in parallel (reviewer
        directive); the orchestrator decides on scheduling.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str
    objective: str
    files: tuple[PlannedFileOperation, ...] = Field(default_factory=tuple)

    @field_validator("plan_id")
    @classmethod
    def _plan_id_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("plan_id must be a non-empty string.")
        return v


@dataclass
class Task:
    """One planned file operation inside a Run.

    ``.status()`` returns the current ``TaskStatus`` string by reading
    the committed ``TaskManager`` snapshot — the Task object does not
    cache state across calls, so callers always see fresh data.
    """

    task_id: str
    path: str
    operation: str
    _run: Run  # back-reference so .status() can consult the run's TM

    def status(self) -> TaskStatus:
        return self._run._task_status(self.task_id)


class Run:
    """A single workflow in progress.

    One Run per start() call. Keeps a stable list of ``Task`` objects
    (one per planned file), an in-process pause flag, and a reference
    to the internal ``OneShotController`` that owns the shared
    ``TaskManager``.

    Thread-safety: ``pause`` / ``resume`` / ``status`` are safe to
    call from any thread. The guard is a per-Run lock; underlying
    ``TaskManager`` state is already guarded by its own atomic
    writer.
    """

    def __init__(
        self,
        *,
        plan: RunPlan,
        controller,  # OneShotController; typed as Any to avoid circular import
        parent_task_id: str,
        task_ids: tuple[str, ...],
    ) -> None:
        self._plan = plan
        self._controller = controller
        self._parent_task_id = parent_task_id
        self._state_lock = threading.Lock()
        self._paused = False
        # One Task per planned file, preserving plan order.
        self._tasks: tuple[Task, ...] = tuple(
            Task(
                task_id=tid,
                path=pf.path,
                operation=pf.operation,
                _run=self,
            )
            for pf, tid in zip(plan.files, task_ids, strict=True)
        )

    # ------------------------------------------------------------------
    # Public API — plan_id / tasks / status / pause / resume
    # ------------------------------------------------------------------

    @property
    def plan_id(self) -> str:
        return self._plan.plan_id

    @property
    def tasks(self) -> tuple[Task, ...]:
        """Iterable of planned-file Task objects, in plan order."""
        return self._tasks

    def status(self) -> RunStatus:
        """Aggregate run status.

        ``paused`` beats everything (the user explicitly held the
        workflow). Otherwise the aggregate is derived from the
        TaskManager state of each Task:
          * all tasks completed → ``"completed"``
          * any task failed → ``"failed"``
          * any task running → ``"running"``
          * else → ``"pending"``
        """
        with self._state_lock:
            if self._paused:
                return "paused"
        states = {t.status() for t in self._tasks} or {"pending"}
        if states == {"completed"}:
            return "completed"
        if "failed" in states:
            return "failed"
        if "running" in states:
            return "running"
        return "pending"

    def pause(self) -> None:
        """Request a pause.

        Marks the run as paused and records a progress note on the
        parent task. Already-paused runs are a no-op.
        """
        with self._state_lock:
            if self._paused:
                return
            self._paused = True
        self._record_progress("pause requested")

    def resume(self) -> None:
        """Clear a pause.

        Already-running runs are a no-op.
        """
        with self._state_lock:
            if not self._paused:
                return
            self._paused = False
        self._record_progress("resume requested")

    @property
    def paused(self) -> bool:
        with self._state_lock:
            return self._paused

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _task_status(self, task_id: str) -> TaskStatus:
        """Project a TaskManager state onto the TaskStatus vocabulary."""
        with self._state_lock:
            if self._paused:
                # The pause lives on the Run, not on each child task's
                # TaskManager row; while paused, every pending/running
                # task is reported as paused.
                raw = self._controller.tm.get_task(task_id)
                committed_raw = raw.state if raw is not None else "pending"
                if committed_raw == "completed":
                    return "completed"
                if committed_raw == "failed":
                    return "failed"
                return "paused"
        task = self._controller.tm.get_task(task_id)
        if task is None:
            return "pending"
        state: str = task.state
        # TaskManager vocabulary (pending/running/completed/failed) is
        # already aligned with our TaskStatus Literal; narrow explicitly
        # for the type-checker.
        if state == "pending":
            return "pending"
        if state == "running":
            return "running"
        if state == "completed":
            return "completed"
        if state == "failed":
            return "failed"
        return "pending"

    def _record_progress(self, note: str) -> None:
        """Append a progress note on the parent task without failing.

        Best-effort: a failed append (missing task, race) is swallowed.
        TaskManager remains the sole durable owner.
        """
        try:
            task = self._controller.tm.get_task(self._parent_task_id)
            if task is None:
                return
            meta = dict(task.metadata or {})
            trail = list(meta.get("run_lifecycle_trail") or [])
            trail.append({"note": note})
            meta["run_lifecycle_trail"] = trail
            self._controller.tm.set_task_metadata(
                self._parent_task_id, meta
            )
        except Exception:  # noqa: BLE001 - lifecycle progress is advisory
            return


# ---------------------------------------------------------------------
# Public entry point: agent.start(plan_id)
# ---------------------------------------------------------------------

_RUN_LOCK = threading.Lock()
_RUNS: dict[str, Run] = {}


def start(
    plan_id: RunPlan | Mapping | str,
    *,
    storage_path: str | Path | None = None,
    controller=None,
) -> Run:
    """Start a workflow and return a ``Run`` handle.

    ``plan_id`` accepts three shapes:
      * a ``RunPlan`` instance (preferred);
      * a mapping with ``plan_id``, ``objective``, and ``files``
        keys (built in-process by callers that already have the data
        as a dict);
      * a bare string, in which case a one-task placeholder plan is
        synthesised with that id, no files, and a short objective
        suffix. This path exists so smoke tests can call
        ``agent.start("ping")`` without constructing a full plan.

    ``storage_path`` overrides the TaskManager snapshot path (default:
    the CLI's ``/tmp/oneshot_tasks.json`` when none is supplied).
    Callers that have already built an ``OneShotController`` may pass
    it as ``controller=`` and the start helper reuses it instead of
    constructing a new one; this keeps a single TaskManager snapshot
    across repeated ``start`` calls in the same process.
    """
    plan = _coerce_plan(plan_id)
    if controller is None:
        from agent.__main__ import OneShotController

        controller = OneShotController(
            storage_path=str(storage_path or "/tmp/oneshot_tasks.json")
        )
    # Start the parent task on the TaskManager.
    parent_task_id = controller.start_task(
        request_ref=plan.objective,
        metadata={"plan_id": plan.plan_id, "run_file_count": len(plan.files)},
    )
    # Create one child task per planned file. We reuse TaskManager
    # directly (the authoritative state owner).
    child_task_ids: list[str] = []
    for pf in plan.files:
        child = controller.tm.create_task(
            metadata={
                "plan_id": plan.plan_id,
                "parent_task_id": parent_task_id,
                "file_path": pf.path,
                "operation": pf.operation,
                "note": pf.note,
                "stage": "build",
                "owner": "agent.orchestration",
                "revision": 1,
            }
        )
        child_task_ids.append(child.task_id)
    run = Run(
        plan=plan,
        controller=controller,
        parent_task_id=parent_task_id,
        task_ids=tuple(child_task_ids),
    )
    with _RUN_LOCK:
        _RUNS[plan.plan_id] = run
    return run


def get_run(plan_id: str) -> Run | None:
    """Look up a Run previously started in this process. Returns None
    when no such Run exists (e.g. after an interpreter restart —
    durable state lives on TaskManager; the Run handle is in-process)."""
    with _RUN_LOCK:
        return _RUNS.get(plan_id)


def _coerce_plan(
    arg: RunPlan | Mapping | str,
) -> RunPlan:
    if isinstance(arg, RunPlan):
        return arg
    if isinstance(arg, Mapping):
        return RunPlan.model_validate(dict(arg))
    if isinstance(arg, str):
        return RunPlan(
            plan_id=arg,
            objective=f"start:{arg}",
            files=(),
        )
    raise TypeError(
        f"agent.start: plan_id must be a RunPlan, mapping, or str; got "
        f"{type(arg).__name__}."
    )


__all__ = [
    "PlannedFileOperation",
    "Run",
    "RunPlan",
    "Task",
    "get_run",
    "start",
]
