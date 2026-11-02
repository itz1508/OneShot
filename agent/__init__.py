"""OneShot public package surface.

The reviewer-approved public API is deliberately small:

* ``agent.start(plan_id)``   — create a ``Run`` bound to a workflow.
* ``agent.Run``              — the workflow lifecycle handle
                                (``pause`` / ``resume`` / ``status``,
                                iterable ``.tasks``).
* ``agent.Task``              — one planned file operation. ``.status()``
                                returns the current ``TaskStatus``.
* ``agent.RunPlan`` /
  ``agent.PlannedFileOperation`` — Pydantic-strict declarations for
                                programmatic callers.
* ``agent.get_run(plan_id)``  — look up a Run previously started in
                                this process.

Internal workflow orchestration (``OneShotController`` and the
specialist components in ``agent.__main__``) and the durable state
owner (``TaskManager`` in ``tools/``) are intentionally NOT exported
from this top level — callers should use the public ``start`` /
``Run`` / ``Task`` surface.

Example:

    import agent

    run = agent.start(plan_id)
    run.pause()
    run.resume()
    run.status()
    for task in run.tasks:
        print(task.status())
"""

from agent.orchestration import (
    PlannedFileOperation,
    Run,
    RunPlan,
    Task,
    get_run,
    start,
)

__all__ = [
    "PlannedFileOperation",
    "Run",
    "RunPlan",
    "Task",
    "get_run",
    "start",
]
