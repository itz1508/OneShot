"""Builder Discovery runner.

The runner's job is narrow:

  1. Accept a ``DiscoveryHandoff`` (a frozen Pydantic model describing
     the planned file operations the Build stage should execute).
  2. Validate it against the active prompt revision\'s
     ``output_contract`` when a ``PromptStore`` is supplied.
  3. Translate the handoff into a ``RunPlan`` and start a ``Run`` via
     ``agent.start()``.
  4. Return the ``Run`` for the caller to drive (``execute``,
     ``pause``, ``resume``, ``status``).

Design pins:

* Builder Discovery NEVER mutates ``TaskManager`` directly \\u2014 it
  delegates to ``agent.start()`` which owns the state writes.
* The runner does not perform any file I/O. Deterministic Research /
  Plan / Build code paths stay untouched.
* The runner is OPT-IN: callers that still prefer the legacy
  ``OneShotController.run_workflow`` path keep using it unchanged.
* The runner carries NO authority over tool permissions \\u2014 it only
  builds a RunPlan; the executor passed to ``Run.execute()`` is
  what actually invokes tools.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.orchestration import PlannedFileOperation, Run, RunPlan


class DiscoveryHandoffError(ValueError):
    """Raised when the handoff fails validation (empty files list,
    duplicate paths, unknown prompt revision)."""


class DiscoveryHandoff(BaseModel):
    """Frozen description of what Builder Discovery hands to Build.

    Mirrors the shape of a ``RunPlan`` but captures the discovery
    provenance (``prompt_id``, ``revision_digest``) so Build receipts
    can bind back to the prompt that authorised them.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_id: str
    objective: str
    files: tuple[PlannedFileOperation, ...] = Field(min_length=1)
    prompt_id: str | None = None
    revision_digest: str | None = None

    @field_validator("plan_id")
    @classmethod
    def _nonblank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("plan_id must be a non-empty string.")
        return v

    @field_validator("files")
    @classmethod
    def _no_duplicate_paths(
        cls, files: tuple[PlannedFileOperation, ...]
    ) -> tuple[PlannedFileOperation, ...]:
        seen: set[str] = set()
        for f in files:
            if f.path in seen:
                raise ValueError(
                    f"duplicate planned file path: {f.path!r}. "
                    "One task per planned file — the handoff must list "
                    "each path at most once."
                )
            seen.add(f.path)
        return files


class BuilderDiscoveryRunner:
    """Opt-in bridge from a DiscoveryHandoff to an executable Run.

    Usage::

        runner = BuilderDiscoveryRunner(controller=my_oneshot_controller)
        run = runner.start_from_handoff(handoff)
        results = run.execute(executor=my_writer)
    """

    def __init__(
        self,
        *,
        controller: Any = None,
        prompt_store: Any = None,
    ) -> None:
        self._controller = controller
        self._prompt_store = prompt_store

    def start_from_handoff(
        self,
        handoff: DiscoveryHandoff,
        *,
        storage_path: str | None = None,
    ) -> Run:
        """Validate the handoff, build a RunPlan, start a Run.

        Returns the ``Run`` — the caller drives execution.
        """
        self._bind_prompt_if_declared(handoff)
        plan = RunPlan(
            plan_id=handoff.plan_id,
            objective=handoff.objective,
            files=handoff.files,
        )
        from agent import start as _start

        return _start(
            plan,
            storage_path=storage_path,
            controller=self._controller,
        )

    def _bind_prompt_if_declared(self, handoff: DiscoveryHandoff) -> None:
        """When the handoff names a prompt_id AND the runner has a
        PromptStore, verify the prompt exists at an ACTIVE revision.

        A missing PromptStore is tolerated (the handoff is deemed
        caller-authorised). A missing prompt is a hard refusal.
        """
        if handoff.prompt_id is None:
            return
        if self._prompt_store is None:
            return
        store = self._prompt_store
        if not hasattr(store, "active_revision"):
            return
        active = store.active_revision(handoff.prompt_id)
        if active is None:
            raise DiscoveryHandoffError(
                f"discovery_handoff_unknown_prompt: no active revision for "
                f"prompt_id={handoff.prompt_id!r} in the configured PromptStore."
            )
        if handoff.revision_digest is None:
            return
        digest = getattr(active, "content_digest", None) or getattr(
            active, "digest", None
        )
        if digest is not None and digest != handoff.revision_digest:
            raise DiscoveryHandoffError(
                f"discovery_handoff_digest_mismatch: handoff declares "
                f"revision_digest={handoff.revision_digest!r} but the "
                f"PromptStore\\u2019s active revision has digest={digest!r}."
            )


__all__ = [
    "BuilderDiscoveryRunner",
    "DiscoveryHandoff",
    "DiscoveryHandoffError",
]
