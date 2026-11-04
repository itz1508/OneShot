"""Build TaskTodo compiler is deterministic, dependency-safe and effect-free."""

import pytest

from agent.contracts.common import ArtifactRef
from agent.contracts.planning import BuildSpecification, CreateAction
from agent.contracts.task_todo import Build
from agent.runtime.build_todos import compile_build


def ref():
    return ArtifactRef(
        artifact_id="frozen",
        artifact_revision=1,
        artifact_digest="a" * 64,
        contract_id="build_specification",
        contract_version="1.0",
        serializer_profile="jcs-rfc8785-v1",
    )


def action(action_id, path, depends_on=()):
    return CreateAction(
        action_id=action_id,
        requirement_ids=("REQ-001",),
        acceptance_criteria_ids=("AC-001",),
        code_intent_ids=("ci-1",),
        preconditions=("workspace available",),
        depends_on=depends_on,
        validation_steps=("run tests",),
        expected_result="file exists",
        recovery_requirement="remove only owned file",
        target_path=path,
        target_conflict_check_ref="conflict-checked",
    )


def test_disjoint_waves_and_dependencies():
    spec = BuildSpecification(
        spec_id="s",
        objective="create files",
        actions=(
            action("a", "a.py"),
            action("b", "b.py"),
            action("c", "a.py", ("a",)),
        ),
    )
    build = compile_build(spec, ref())
    assert build.waves == (("a", "b"), ("c",))
    assert compile_build(spec, ref()) == build
    assert build.todos[0].authorized_paths == ("a.py",)


def test_overlapping_paths_serialized_without_dependency():
    spec = BuildSpecification(
        spec_id="s",
        objective="create files",
        actions=(
            action("a", "same.py"),
            action("b", "same.py"),
        ),
    )
    assert compile_build(spec, ref()).waves == (("a",), ("b",))


def test_dependency_cycle_and_traversal_rejected():
    spec = BuildSpecification(
        spec_id="s",
        objective="create files",
        actions=(
            action("a", "a.py", ("b",)),
            action("b", "b.py", ("a",)),
        ),
    )
    with pytest.raises(ValueError, match="cyclic"):
        compile_build(spec, ref())
    unsafe = BuildSpecification(spec_id="s", objective="create files", actions=(action("a", "../escape.py"),))
    with pytest.raises(ValueError, match="unsafe"):
        compile_build(unsafe, ref())


def test_parent_child_workspace_paths_never_share_wave():
    spec = BuildSpecification(
        spec_id="nested",
        objective="serialize namespace edits",
        actions=(action("parent", "src"), action("child", "src/main.py")),
    )
    build = compile_build(spec, ref())
    assert build.waves == (("parent",), ("child",))


def test_manual_build_rejects_reused_source_action():
    spec = BuildSpecification(
        spec_id="duplicate",
        objective="distinct action ownership",
        actions=(action("a", "a.py"), action("b", "b.py")),
    )
    compiled = compile_build(spec, ref())
    second = compiled.todos[1].model_copy(update={"source_action_ids": ("a",)})
    with pytest.raises(ValueError, match="multiple TaskTodo"):
        Build.model_validate(
            {
                **compiled.model_dump(),
                "todos": [compiled.todos[0].model_dump(), second.model_dump()],
            }
        )
