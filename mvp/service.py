"""MVP task input and event adapter. HostController owns workflow state.

This adapter does not execute or promote workflow stages and never emits
fabricated Research/Audit/Plan completion records.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from agent.runtime.artifact_store import ArtifactStore, StaleRevisionError
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.controller import HostController

_ID = re.compile(r"^[0-9a-f]{32}$")


class TaskInput(BaseModel):
    task_id: str
    text: str = Field(min_length=1, max_length=20000)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MVPError(ValueError):
    pass


class MVPService:
    def __init__(self, state_root: str | Path) -> None:
        self.host = HostController(state_root)
        self.artifacts: ArtifactStore = self.host.artifact_store

    @staticmethod
    def _check_id(task_id: str) -> str:
        if _ID.fullmatch(task_id) is None:
            raise MVPError("invalid task identifier")
        return task_id

    @staticmethod
    def _artifact_id(task_id: str) -> str:
        return f"mvp-input:{task_id}"

    def create(self, prompt: str) -> dict[str, object]:
        cleaned = prompt.strip()
        if not cleaned or len(cleaned) > 20000:
            raise MVPError("task text must contain 1–20000 characters")
        task_id = uuid4().hex
        run_id = f"run-{task_id}"
        record = TaskInput(task_id=task_id, text=cleaned)
        self.artifacts.put_immutable(record, self._artifact_id(task_id), 1, "mvp_task_input", "1.0")
        self.host.init_task(task_id, run_id)
        self.host.event_store.append(task_id, "mvp_input_persisted", "input revision 1")
        self.host.event_store.append(task_id, "mvp_mcp_unavailable", "MCP client not connected; no workflow executed")
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, object]:
        self._check_id(task_id)
        state = self.host.get_state(task_id)
        if state is None:
            raise MVPError("task not found")
        input_record, revision, digest = self.read_input(task_id)
        return {
            "task_id": task_id,
            "run_id": state.run_id,
            "current_stage": state.current_stage.value,
            "completed_stages": [s.value for s in state.completed_stages],
            "execution_status": "awaiting_mcp",
            "input_revision": revision,
            "input_digest": digest,
            "input_text": input_record.text,
            "mcp_connected": False,
        }

    def read_input(self, task_id: str) -> tuple[TaskInput, int, str]:
        self._check_id(task_id)
        aid = self._artifact_id(task_id)
        revision = self.artifacts.latest_revision(aid)
        if revision < 1:
            raise MVPError("task input not found")
        raw = self.artifacts.get_verified(aid, revision)
        digest = self.artifacts.get_digest(aid, revision)
        if digest is None:
            raise MVPError("missing input artifact digest")
        record = TaskInput.model_validate_json(raw)
        if record.task_id != task_id:
            raise MVPError("input identity mismatch")
        return record, revision, digest

    def revise_input(self, task_id: str, text: str, expected_revision: int) -> dict[str, object]:
        self._check_id(task_id)
        if self.host.get_state(task_id) is None:
            raise MVPError("task not found")
        if expected_revision < 1:
            raise MVPError("invalid expected revision")
        content = text.strip()
        if not content or len(content) > 20000:
            raise MVPError("task text must contain 1–20000 characters")
        record = TaskInput(task_id=task_id, text=content)
        try:
            self.artifacts.put_cas(record, self._artifact_id(task_id), expected_revision, "mvp_task_input", "1.0")
        except StaleRevisionError as exc:
            raise MVPError("input revision conflict") from exc
        self.host.event_store.append(task_id, "mvp_input_revised", f"input revision {expected_revision + 1}")
        return self.get(task_id)

    def events(self, task_id: str, after: int = 0) -> list[dict[str, object]]:
        self._check_id(task_id)
        if after < 0:
            raise MVPError("invalid event cursor")
        if self.host.get_state(task_id) is None:
            raise MVPError("task not found")
        return [
            {
                "sequence": event["seq"],
                "type": event["event_type"],
                "message": event["event_data"],
                "created_at": event["created_at"],
            }
            for event in self.host.event_store.list(task_id)
            if event["seq"] > after
        ]

    def artifacts_for_task(self, task_id: str) -> list[dict[str, object]]:
        record, revision, digest = self.read_input(task_id)
        return [{
            "name": "_input.json",
            "kind": "input",
            "revision": revision,
            "digest": digest,
            "content": record.model_dump_json(indent=2),
        }]
