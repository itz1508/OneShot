"""One authoritative, scope-isolated durable task and result store.

Callers are authenticated by their trusted process configuration, not by task IDs.
This single-process SQLite implementation is intentionally not a multi-tenant service.
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from output.main import validate_output


class TaskRejected(ValueError):
    """Invalid, unauthorized, stale or conflicting task operation."""


class TaskStore:
    def __init__(self, database: Path, *, scope: str) -> None:
        if not scope or not scope.strip():
            raise TaskRejected("A trusted nonempty scope is required")
        self.database = Path(database)
        self.scope = scope
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, scope TEXT NOT NULL,
                    request_id TEXT NOT NULL, objective TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0,
                    final_type TEXT, final_id TEXT,
                    UNIQUE(scope, request_id)
                );
                CREATE TABLE IF NOT EXISTS results (
                    scope TEXT NOT NULL, task_id TEXT NOT NULL,
                    type TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY (scope, task_id, type, id),
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY, scope TEXT NOT NULL,
                    task_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    kind TEXT NOT NULL, detail TEXT NOT NULL,
                    UNIQUE(scope, task_id, revision),
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY, scope TEXT NOT NULL,
                    task_id TEXT NOT NULL, plan_id TEXT NOT NULL,
                    temp_name TEXT NOT NULL, state TEXT NOT NULL, evidence TEXT,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database, timeout=5, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            yield db
        finally:
            db.close()

    @staticmethod
    def _must_text(value: Any, what: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise TaskRejected(f"{what} must be nonempty")
        return value

    def _task(self, db: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = db.execute("SELECT * FROM tasks WHERE id=? AND scope=?", (task_id, self.scope)).fetchone()
        if row is None:
            raise TaskRejected("Task not found in authorized scope")
        return row

    @staticmethod
    def _revision(expected: int, actual: int) -> None:
        if type(expected) is not int or expected != actual:
            raise TaskRejected("Stale task revision")

    def _event(self, db: sqlite3.Connection, task_id: str, revision: int, kind: str, detail: dict[str, Any]) -> None:
        db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", (
            uuid4().hex, self.scope, task_id, revision, kind,
            json.dumps(detail, sort_keys=True, ensure_ascii=False),
        ))

    def create_task(self, *, request_id: str, objective: str) -> dict[str, Any]:
        self._must_text(request_id, "request_id")
        self._must_text(objective, "objective")
        task_id = uuid4().hex
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute(
                    "SELECT * FROM tasks WHERE scope=? AND request_id=?", (self.scope, request_id)
                ).fetchone()
                if existing:
                    if existing["objective"] != objective:
                        raise TaskRejected("Request identity already belongs to another objective")
                    db.commit()
                    return self._view(existing)
                db.execute("INSERT INTO tasks(id,scope,request_id,objective) VALUES(?,?,?,?)",
                           (task_id, self.scope, request_id, objective))
                self._event(db, task_id, 0, "created", {"request_id": request_id})
                db.commit()
                return self.get_task(task_id)
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def _view(row: sqlite3.Row) -> dict[str, Any]:
        return {k: row[k] for k in ("id", "request_id", "objective", "revision", "final_type", "final_id")}

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as db:
            return self._view(self._task(db, task_id))

    def events(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            self._task(db, task_id)
            rows = db.execute("SELECT revision,kind,detail FROM events WHERE scope=? AND task_id=? ORDER BY revision",
                              (self.scope, task_id)).fetchall()
            return [{"revision": r["revision"], "kind": r["kind"], "detail": json.loads(r["detail"])} for r in rows]

    def get_result(self, task_id: str, result_type: str, result_id: str) -> dict[str, Any]:
        with self._connect() as db:
            self._task(db, task_id)
            row = db.execute("SELECT body FROM results WHERE scope=? AND task_id=? AND type=? AND id=?",
                             (self.scope, task_id, result_type, result_id)).fetchone()
            if row is None:
                raise TaskRejected("Result not found")
            return json.loads(row["body"])

    def get_final(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task["final_type"] is None:
            raise TaskRejected("Task does not have a committed final result")
        return self.get_result(task_id, task["final_type"], task["final_id"])

    def _insert_result(self, db: sqlite3.Connection, row: sqlite3.Row, value: dict[str, Any]) -> None:
        if value["request_id"] != row["request_id"]:
            raise TaskRejected("Result request identity mismatch")
        if value["type"] == "research" and "validation_values" in value:
            identifiers = [entry["id"] for entry in value["validation_values"]]
            if len(identifiers) != len(set(identifiers)):
                raise TaskRejected("Research validation value IDs must be unique")
        if value["type"] == "plan" and "research_id" in value:
            self._get_link(db, row["id"], "research", value["research_id"])
            if "validation_value_refs" in value:
                source_row = db.execute(
                    "SELECT body FROM results WHERE scope=? AND task_id=? AND type='research' AND id=?",
                    (self.scope, row["id"], value["research_id"]),
                ).fetchone()
                # The lookup above is scoped and follows the checked Research link.
                source = json.loads(source_row["body"])
                valid_ids = {item["id"] for item in source.get("validation_values", [])}
                if not set(value["validation_value_refs"]).issubset(valid_ids):
                    raise TaskRejected("Plan references an unknown Research validation value")
        if value["type"] == "build":
            self._get_link(db, row["id"], "plan", value["plan_id"])
        db.execute("INSERT INTO results VALUES(?,?,?,?,?)", (
            self.scope, row["id"], value["type"], value["id"],
            json.dumps(value, sort_keys=True, ensure_ascii=False),
        ))

    def _get_link(self, db: sqlite3.Connection, task_id: str, kind: str, result_id: str) -> None:
        exists = db.execute("SELECT 1 FROM results WHERE scope=? AND task_id=? AND type=? AND id=?",
                            (self.scope, task_id, kind, result_id)).fetchone()
        if exists is None:
            raise TaskRejected(f"Referenced {kind} result not found in task")

    def save_host_result(self, *, task_id: str, expected_revision: int, value: dict[str, Any]) -> dict[str, Any]:
        result = validate_output(value)
        if result["type"] not in ("research", "plan"):
            raise TaskRejected("Build results must come from actual Builder execution")
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = self._task(db, task_id)
                self._revision(expected_revision, row["revision"])
                if row["final_type"] is not None:
                    raise TaskRejected("Task is finalized")
                self._insert_result(db, row, result)
                revision = row["revision"] + 1
                db.execute("UPDATE tasks SET revision=? WHERE id=?", (revision, task_id))
                self._event(db, task_id, revision, "result_recorded", {"type": result["type"], "id": result["id"]})
                db.commit()
                return self.get_task(task_id)
            except BaseException:
                db.rollback()
                raise

    def finish_task(self, *, task_id: str, expected_revision: int, result_type: str, result_id: str) -> dict[str, Any]:
        if result_type not in ("research", "plan", "build"):
            raise TaskRejected("Unknown result type")
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = self._task(db, task_id)
                self._revision(expected_revision, row["revision"])
                if row["final_type"] is not None:
                    raise TaskRejected("Task already finalized")
                self._get_link(db, task_id, result_type, result_id)
                revision = row["revision"] + 1
                db.execute("UPDATE tasks SET final_type=?,final_id=?,revision=? WHERE id=?",
                           (result_type, result_id, revision, task_id))
                self._event(db, task_id, revision, "finalized", {"type": result_type, "id": result_id})
                db.commit()
                return self.get_task(task_id)
            except BaseException:
                db.rollback()
                raise

    def begin_build(self, *, task_id: str, expected_revision: int, plan_id: str, build_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(build_id, str) or re.fullmatch(r"[0-9a-f]{32}", build_id) is None:
            raise TaskRejected("Invalid internal build identity")
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = self._task(db, task_id)
                self._revision(expected_revision, row["revision"])
                if row["final_type"] is not None:
                    raise TaskRejected("Task is finalized")
                plan = db.execute("SELECT body FROM results WHERE scope=? AND task_id=? AND type='plan' AND id=?",
                                  (self.scope, task_id, plan_id)).fetchone()
                if plan is None:
                    raise TaskRejected("Authorized plan not found in task")
                db.execute("INSERT INTO attempts(id,scope,task_id,plan_id,temp_name,state) VALUES(?,?,?,?,?,?)",
                           (build_id, self.scope, task_id, plan_id, build_id, "started"))
                revision = row["revision"] + 1
                db.execute("UPDATE tasks SET revision=? WHERE id=?", (revision, task_id))
                self._event(db, task_id, revision, "build_started", {"id": build_id, "plan_id": plan_id})
                db.commit()
                return self.get_task(task_id), json.loads(plan["body"])
            except BaseException:
                db.rollback()
                raise

    def note_build_evidence(self, *, task_id: str, build_id: str, observation: dict[str, Any]) -> None:
        """Durably preserve observed execution facts before cleanup occurs."""
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = self._task(db, task_id)
                attempt = db.execute("SELECT id FROM attempts WHERE id=? AND scope=? AND task_id=? AND state='started'",
                                     (build_id, self.scope, task_id)).fetchone()
                if attempt is None:
                    raise TaskRejected("Active build attempt not found")
                data = json.dumps(observation, sort_keys=True, ensure_ascii=False)
                db.execute("UPDATE attempts SET evidence=? WHERE id=?", (data, build_id))
                revision = row["revision"] + 1
                db.execute("UPDATE tasks SET revision=? WHERE id=?", (revision, task_id))
                self._event(db, task_id, revision, "build_observed", {"id": build_id, "observation": observation})
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def finish_build(self, *, task_id: str, build_id: str, value: dict[str, Any]) -> dict[str, Any]:
        result = validate_output(value)
        if result["type"] != "build" or result["id"] != build_id:
            raise TaskRejected("Incorrect build result identity")
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                row = self._task(db, task_id)
                attempt = db.execute("SELECT * FROM attempts WHERE id=? AND scope=? AND task_id=? AND state='started'",
                                     (build_id, self.scope, task_id)).fetchone()
                if attempt is None or result["plan_id"] != attempt["plan_id"]:
                    raise TaskRejected("Active build attempt not found")
                self._insert_result(db, row, result)
                db.execute("UPDATE attempts SET state='finished' WHERE id=?", (build_id,))
                revision = row["revision"] + 1
                db.execute("UPDATE tasks SET revision=? WHERE id=?", (revision, task_id))
                self._event(db, task_id, revision, "build_finished", {"id": build_id,
                            "outcome": result["execution"]["outcome"], "cleanup": result["cleanup"]["outcome"]})
                db.commit()
                return self.get_task(task_id)
            except BaseException:
                db.rollback()
                raise

    def pending_builds(self) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM attempts WHERE scope=? AND state='started'",
                              (self.scope,)).fetchall()
            return [{**{k: row[k] for k in ("id", "task_id", "plan_id", "temp_name")},
                     "evidence": json.loads(row["evidence"]) if row["evidence"] else None}
                    for row in rows]
