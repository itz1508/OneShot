"""Fail-closed tool catalog and Build Admission integration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.contracts.common import ArtifactRef
from agent.contracts.planning import BuildSpecification, CreateAction
from agent.contracts.tool_registry import (
    ParamKind,
    SandboxProfile,
    ToolEffect,
    ToolInvocation,
    ToolParam,
    ToolRegistrySnapshot,
    ToolSpec,
    resolve_invocation,
)
from agent.contracts.validation.structural import tool_invocation_gaps
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.build_admission import BuildAdmission, BuildAdmissionError
from agent.runtime.package_lock import PackageLock
from agent.runtime.receipt_store import ReceiptStore
from agent.runtime.tool_registry import (
    ToolRegistryError,
    load_pinned_tool_registry,
    pin_tool_registry,
)

DIGEST = "a" * 64
IMAGE = "example.invalid/build@sha256:" + "b" * 64


def catalog(*, network: bool = False) -> ToolRegistrySnapshot:
    return ToolRegistrySnapshot(
        registry_version="1",
        sandbox_profiles=(
            SandboxProfile(
                profile_id="build-sandbox",
                image_ref=IMAGE,
                network_allowed=network,
                allowed_effects=(ToolEffect.READ_ONLY, ToolEffect.WORKSPACE_WRITE, ToolEffect.EXTERNAL),
            ),
        ),
        tools=(
            ToolSpec(
                tool_id="pytest-quiet",
                version="1.0",
                executable_digest=DIGEST,
                argv_template=("uv", "run", "--no-sync", "pytest", "-q", "{path}"),
                params=(ToolParam(name="path", kind=ParamKind.WORKSPACE_PATH),),
                allowed_stages=("build",),
                effect=ToolEffect.WORKSPACE_WRITE,
                network=False,
                timeout_seconds=60,
                max_output_bytes=100_000,
                sandbox_profile_id="build-sandbox",
            ),
        ),
    )


def spec(invocation: ToolInvocation) -> BuildSpecification:
    return BuildSpecification(
        spec_id="build-001",
        objective="test build",
        actions=(
            CreateAction(
                action_id="act-001",
                requirement_ids=("REQ-001",),
                acceptance_criteria_ids=("AC-001",),
                code_intent_ids=("intent-001",),
                preconditions=("target absent",),
                validation_steps=("pytest passes",),
                verification_tools=(invocation,),
                expected_result="created",
                recovery_requirement="clean up",
                target_path="tests/test_new.py",
                target_conflict_check_ref="scan-001",
            ),
        ),
    )


def invocation(tool_id: str = "pytest-quiet", path: str = "tests") -> ToolInvocation:
    return ToolInvocation(tool_id=tool_id, args={"path": path})


def test_registered_invocation_is_argv_only() -> None:
    result = resolve_invocation(catalog(), invocation(), "build", frozenset({"tests/test_new.py"}))
    assert result.argv == ("uv", "run", "--no-sync", "pytest", "-q", "tests")
    assert result.image_ref == IMAGE


@pytest.mark.parametrize("value", ["../etc", "/etc", r"C:\Windows", "-rf", "a\\b", "a/../b"])
def test_unsafe_workspace_paths_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        resolve_invocation(catalog(), invocation(path=value), "build", frozenset())


def test_wrong_stage_and_unknown_tool_rejected() -> None:
    with pytest.raises(ValueError, match="stage"):
        resolve_invocation(catalog(), invocation(), "research", frozenset())
    with pytest.raises(ValueError, match="unregistered"):
        resolve_invocation(catalog(), invocation(tool_id="evil"), "build", frozenset())


def test_invented_argument_rejected() -> None:
    with pytest.raises(ValueError, match="arguments"):
        resolve_invocation(
            catalog(), ToolInvocation(tool_id="pytest-quiet", args={"other": "tests"}), "build", frozenset()
        )


def test_path_param_requires_exact_affected_path() -> None:
    base = catalog()
    tool = base.tools[0].model_copy(update={"params": (ToolParam(name="path", kind=ParamKind.PATH),)})
    changed = base.model_copy(update={"tools": (tool,)})
    with pytest.raises(ValueError, match="not admitted"):
        resolve_invocation(changed, invocation(path="other.py"), "build", frozenset({"tests/test_new.py"}))


def test_unknown_profile_rejected() -> None:
    with pytest.raises(ValidationError, match="sandbox profile"):
        ToolRegistrySnapshot(
            registry_version="1",
            tools=catalog().tools,
            sandbox_profiles=(SandboxProfile(profile_id="different", image_ref=IMAGE),),
        )


def test_template_cannot_embed_user_value_in_option() -> None:
    data = catalog().tools[0].model_dump()
    data["argv_template"] = ("uv", "--output={path}")
    with pytest.raises(ValidationError, match="complete argv token"):
        ToolSpec(**data)


def test_network_and_effect_must_agree() -> None:
    data = catalog().tools[0].model_dump()
    data["network"] = True
    with pytest.raises(ValidationError, match="network requires external"):
        ToolSpec(**data)


def test_snapshot_pinning_is_immutable(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    ref = pin_tool_registry(store, catalog(), "tools-001")
    assert load_pinned_tool_registry(store, ref) == catalog()
    with pytest.raises(ToolRegistryError, match="digest"):
        load_pinned_tool_registry(store, ref.model_copy(update={"artifact_digest": "0" * 64}))


def test_scanner_fails_before_freeze_without_registered_tool() -> None:
    check = spec(invocation("unregistered"))
    assert "unregistered" in "; ".join(tool_invocation_gaps(check, catalog()))
    assert "snapshot required" in "; ".join(tool_invocation_gaps(check, None))


def test_build_admission_derives_tools_from_locked_spec(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    receipts = ReceiptStore(tmp_path)
    registry_ref = pin_tool_registry(store, catalog(), "tools-001")
    upstream: list[ArtifactRef] = []
    for name in ("research", "audit", "frozen"):
        model = spec(invocation()) if name == "frozen" else catalog()
        digest = store.put_immutable(model, name, 1, "fixture", "1")
        upstream.append(
            ArtifactRef(
                artifact_id=name,
                artifact_revision=1,
                artifact_digest=digest,
                contract_id="fixture",
                contract_version="1",
                serializer_profile="rfc8785-jcs-sha256-v1",
            )
        )
    lock = PackageLock(store, receipts).lock("lock-001", *upstream, tool_registry_ref=registry_ref)
    subject = ":".join(ref.artifact_digest for ref in upstream) + ":" + registry_ref.artifact_digest
    admission = BuildAdmission(receipts, store).admit(
        "adm-001",
        lock.receipt_ref,
        ("act-001",),
        subject,
        build_spec=spec(invocation()),
        package_lock=lock,
    )
    assert admission.authorized_tool_ids == ("pytest-quiet",)
    assert admission.tool_registry_ref == registry_ref
    with pytest.raises(BuildAdmissionError, match="unknown action"):
        BuildAdmission(receipts, store).admit(
            "adm-bad",
            lock.receipt_ref,
            ("act-999",),
            subject,
            build_spec=spec(invocation()),
            package_lock=lock,
        )
    with pytest.raises(BuildAdmissionError, match="Package Lock required"):
        BuildAdmission(receipts, store).admit(
            "adm-unbound",
            lock.receipt_ref,
            ("act-001",),
            subject,
            build_spec=spec(invocation()),
        )
    with pytest.raises(BuildAdmissionError, match="frozen BuildSpecification mismatch"):
        BuildAdmission(receipts, store).admit(
            "adm-forged",
            lock.receipt_ref,
            ("act-001",),
            subject,
            build_spec=spec(invocation(path="somewhere-else")),
            package_lock=lock,
        )


def test_preflight_refuses_missing_registered_executable(tmp_path) -> None:
    from agent.runtime.tool_registry import verify_executable

    cmd = resolve_invocation(catalog(), invocation(), "build", frozenset())
    executable = tmp_path / "uv"
    executable.write_bytes(b"not the pinned uv")
    with pytest.raises(ToolRegistryError, match="digest"):
        verify_executable(cmd, executable)
