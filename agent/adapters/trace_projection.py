"""Correlate a verified event scope using the host's existing trace reader.

This is a read-only projection, not a tracer, event writer, task controller,
or E2E assertion engine. Terminal job events do not prove task acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol


class TraceReader(Protocol):
    def __call__(self, job_id: str, events: Iterable[dict], artifact: dict | None = None) -> object: ...


@dataclass(frozen=True)
class ExecutionTrace:
    task_id: str | None
    action_id: str | None
    job_id: str
    execution_outcome: str
    inspection_coverage: str
    generation_mode: str
    terminal_event: str
    event_count: int
    scope_consistent: bool  # Event ID consistency, not authenticated ownership.
    scope_basis: str
    completion_verified: bool = False  # Must be established by contract/E2E owner, not events.


class TraceProjection:
    def __init__(self, reader: TraceReader) -> None:
        self._reader = reader

    def project(self, job_id: str, events: Iterable[dict], *, artifact: dict | None = None,
                task_id: str | None = None, action_id: str | None = None,
                scoped_by_owner: bool = False) -> ExecutionTrace:
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("A job identity is required")
        if type(scoped_by_owner) is not bool:
            raise TypeError("Owner scoping must be an explicit boolean")
        if task_id is not None and (not isinstance(task_id, str) or not task_id):
            raise ValueError("Invalid task ID")
        if action_id is not None and (not isinstance(action_id, str) or not action_id):
            raise ValueError("Invalid action ID")
        rows = list(events)
        if not all(isinstance(e, dict) and isinstance(e.get("kind"), str) for e in rows):
            raise TypeError("Events must be structured records with a kind")
        identities = [e.get("job_id") for e in rows if "job_id" in e]
        if any(identity != job_id for identity in identities):
            raise ValueError("Trace contains events belonging to another job")
        if artifact is not None and (not isinstance(artifact, dict) or
                                     ("job_id" in artifact and artifact["job_id"] != job_id)):
            raise ValueError("Artifact does not belong to the requested job")
        trace = self._reader(job_id, rows, artifact)
        outcome = getattr(trace, "execution_outcome", None)
        coverage = getattr(trace, "inspection_coverage", None)
        mode = getattr(trace, "generation_mode", None)
        terminal = getattr(trace, "terminal_event", None)
        observed_count = getattr(trace, "event_count", None)
        if not all(isinstance(v, str) and v for v in (outcome, coverage, mode, terminal)):
            raise TypeError("Trace reader omitted required observations")
        if type(observed_count) is not int or observed_count != len(rows):
            raise ValueError("Trace reader returned an inconsistent event count")
        # Self-reported owner scoping is NOT independent evidence of scoping.
        # Events with matching IDs permit an internal consistency check only.
        scope_consistent = bool(rows) and len(identities) == len(rows)
        basis = "event_ids_match" if scope_consistent else (
            "owner_asserted_unverified" if scoped_by_owner else "unverified"
        )
        return ExecutionTrace(task_id, action_id, job_id, outcome, coverage,
                              mode, terminal, observed_count, scope_consistent, basis)
