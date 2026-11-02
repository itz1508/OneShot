"""BuilderDiscoveryRunner tests — handoff validation + bridging to Run."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.builder_discovery import (
    BuilderDiscoveryRunner,
    DiscoveryHandoff,
    DiscoveryHandoffError,
)
from agent.orchestration import PlannedFileOperation, Run


class TestHandoffValidation:
    def test_empty_files_refused(self):
        with pytest.raises(Exception):  # noqa: B017 - Pydantic ValidationError
            DiscoveryHandoff(plan_id="x", objective="o", files=())

    def test_duplicate_paths_refused(self):
        with pytest.raises(Exception, match="duplicate planned file path"):  # noqa: B017
            DiscoveryHandoff(
                plan_id="x",
                objective="o",
                files=(
                    PlannedFileOperation(path="a.py"),
                    PlannedFileOperation(path="a.py"),
                ),
            )

    def test_blank_plan_id_refused(self):
        with pytest.raises(Exception):  # noqa: B017
            DiscoveryHandoff(
                plan_id="   ",
                objective="o",
                files=(PlannedFileOperation(path="a.py"),),
            )


class TestStartFromHandoff:
    def test_handoff_produces_run_with_matching_tasks(self, tmp_path):
        h = DiscoveryHandoff(
            plan_id="disc-01",
            objective="discovery smoke",
            files=(
                PlannedFileOperation(path="x.py", operation="edit"),
                PlannedFileOperation(path="y.py", operation="create"),
            ),
        )
        runner = BuilderDiscoveryRunner()
        run = runner.start_from_handoff(
            h, storage_path=str(tmp_path / "tasks.json")
        )
        assert isinstance(run, Run)
        assert run.plan_id == "disc-01"
        assert [t.path for t in run.tasks] == ["x.py", "y.py"]
        assert [t.operation for t in run.tasks] == ["edit", "create"]

    def test_run_executes_tasks_to_completion(self, tmp_path):
        h = DiscoveryHandoff(
            plan_id="disc-02",
            objective="run through",
            files=(PlannedFileOperation(path="a.py"),),
        )
        runner = BuilderDiscoveryRunner()
        run = runner.start_from_handoff(
            h, storage_path=str(tmp_path / "tasks.json")
        )
        results = run.execute()
        assert set(results.values()) == {"completed"}


class TestPromptStoreBinding:
    def test_unknown_prompt_refused(self, tmp_path):
        store = SimpleNamespace(active_revision=lambda prompt_id: None)
        h = DiscoveryHandoff(
            plan_id="disc-03",
            objective="prompt binding",
            files=(PlannedFileOperation(path="a.py"),),
            prompt_id="unknown-prompt",
        )
        runner = BuilderDiscoveryRunner(prompt_store=store)
        with pytest.raises(DiscoveryHandoffError, match="unknown_prompt"):
            runner.start_from_handoff(
                h, storage_path=str(tmp_path / "tasks.json")
            )

    def test_digest_mismatch_refused(self, tmp_path):
        active_rev = SimpleNamespace(content_digest="abc123")
        store = SimpleNamespace(
            active_revision=lambda prompt_id: active_rev
        )
        h = DiscoveryHandoff(
            plan_id="disc-04",
            objective="digest mismatch",
            files=(PlannedFileOperation(path="a.py"),),
            prompt_id="builder-discovery",
            revision_digest="def456",
        )
        runner = BuilderDiscoveryRunner(prompt_store=store)
        with pytest.raises(DiscoveryHandoffError, match="digest_mismatch"):
            runner.start_from_handoff(
                h, storage_path=str(tmp_path / "tasks.json")
            )

    def test_matching_digest_accepted(self, tmp_path):
        active_rev = SimpleNamespace(content_digest="abc123")
        store = SimpleNamespace(
            active_revision=lambda prompt_id: active_rev
        )
        h = DiscoveryHandoff(
            plan_id="disc-05",
            objective="digest ok",
            files=(PlannedFileOperation(path="a.py"),),
            prompt_id="builder-discovery",
            revision_digest="abc123",
        )
        runner = BuilderDiscoveryRunner(prompt_store=store)
        run = runner.start_from_handoff(
            h, storage_path=str(tmp_path / "tasks.json")
        )
        assert run.plan_id == "disc-05"

    def test_no_prompt_store_tolerated(self, tmp_path):
        """A handoff that declares a prompt_id but is passed to a
        runner without a PromptStore proceeds (caller-authorised)."""
        h = DiscoveryHandoff(
            plan_id="disc-06",
            objective="caller authorised",
            files=(PlannedFileOperation(path="a.py"),),
            prompt_id="builder-discovery",
        )
        runner = BuilderDiscoveryRunner()
        run = runner.start_from_handoff(
            h, storage_path=str(tmp_path / "tasks.json")
        )
        assert run.plan_id == "disc-06"
