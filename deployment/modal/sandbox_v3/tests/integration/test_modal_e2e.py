"""Real Modal GOOD/BAD fixture gate. Never runs without explicit credentials/opt-in."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from modal_build_sandbox.contracts import Outcome
from modal_build_sandbox.modal_runtime import ModalRuntime
from modal_build_sandbox.recovery import AttemptStore
from modal_build_sandbox.runner import StandaloneRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_contracts import make_request

pytestmark = pytest.mark.modal_live


def test_real_modal_bad_then_good(tmp_path: Path):
    if os.environ.get("RUN_MODAL_E2E") != "1":
        pytest.skip("requires RUN_MODAL_E2E=1")
    if not all(
        os.environ.get(k)
        for k in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "ONESHOT_MODAL_IMAGE_ID", "ONESHOT_MODAL_APP_NAME")
    ):
        pytest.skip("requires Modal auth, existing App, pinned image")

    runtime = ModalRuntime(os.environ["ONESHOT_MODAL_APP_NAME"], create_app=False)
    runner = StandaloneRunner(runtime, AttemptStore(tmp_path / "attempts.sqlite"), tmp_path / "exports")
    # The explicit production-mode fixture constructor is used to ensure both attempts
    # use the exact prebuilt immutable image. It never grants OneShot host Build Admission.
    image_id = os.environ["ONESHOT_MODAL_IMAGE_ID"]
    from modal_build_sandbox.runner import profile_digest

    for attempt, replacement, expected in (
        ("attempt-1", "    return value.strip()\n", Outcome.FAILED),
        ("attempt-2", "    return value.strip().lower()\n", Outcome.COMPLETED),
    ):
        request = make_request(tmp_path / attempt, attempt=attempt, replacement=replacement)
        request = request.model_copy(update={"image_id": image_id})
        request = request.model_copy(update={"sandbox_profile_digest": profile_digest(request)})
        result = runner.execute(request)
        assert result.execution_status == expected
        assert result.cleanup_state == "confirmed"
        assert runner.attempts.get(request.operation_id, request.attempt_id)["state"] == "TERMINATION_RECORDED"
