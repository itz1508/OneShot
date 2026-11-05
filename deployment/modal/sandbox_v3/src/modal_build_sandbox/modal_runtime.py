"""Modal Sandbox mechanics only; host admission and authoritative promotion live elsewhere."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .contracts import SandboxExecutionRequest

WORKER_ENTRY = (
    "import sys; sys.path.insert(0, '/opt/oneshot-v3'); "
    "from modal_build_sandbox.runner import sandbox_worker; "
    "sandbox_worker('/input/request.json')"
)


class ModalRuntime:
    def __init__(self, app_name: str, *, create_app: bool = False):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,100}", app_name):
            raise ValueError("invalid Modal app name")
        self.app_name = app_name
        self.create_app = create_app

    @staticmethod
    def _modal() -> Any:
        try:
            import modal
        except ImportError as exc:
            raise RuntimeError("install modal extra to execute real Modal Sandboxes") from exc
        return modal

    def create(self, req: SandboxExecutionRequest, sandbox_name: str) -> Any:
        modal = self._modal()
        app = modal.App.lookup(self.app_name, create_if_missing=self.create_app)
        image = modal.Image.from_id(req.image_id)
        return modal.Sandbox.create(
            "sleep",
            "infinity",
            app=app,
            name=sandbox_name,
            image=image,
            block_network=True,
            workdir="/workspace",
            cpu=(req.limits.cpu_request, req.limits.cpu_limit),
            memory=(req.limits.ram_request_mib, req.limits.ram_limit_mib),
            timeout=req.limits.lifetime_seconds,
            idle_timeout=req.limits.idle_seconds,
            secrets=None,
            env={},
            volumes={},
            network_file_systems={},
            pty=False,
            include_oidc_identity_token=False,
        )

    def recover(self, sandbox_name: str, sandbox_id: str | None) -> Any:
        modal = self._modal()
        return modal.Sandbox.from_id(sandbox_id) if sandbox_id else modal.Sandbox.from_name(self.app_name, sandbox_name)

    def upload(self, sb: Any, req: SandboxExecutionRequest) -> None:
        sb.filesystem.make_directory("/workspace", create_parents=True)
        sb.filesystem.make_directory("/input", create_parents=True)
        sb.filesystem.make_directory("/output", create_parents=True)
        sb.filesystem.copy_from_local(req.source_snapshot_ref, "/input/source.tar")
        sb.filesystem.copy_from_local(req.candidate_bundle_ref, "/input/bundle.zip")
        # Copy only trusted runner source, never host credentials / authoritative repository.
        source = Path(__file__).parent
        for filename in (
            "__init__.py",
            "contracts.py",
            "policy.py",
            "snapshot.py",
            "applicator.py",
            "evidence.py",
            "runner.py",
        ):
            sb.filesystem.copy_from_local(source / filename, "/opt/oneshot-v3/modal_build_sandbox/" + filename)
        sb.filesystem.write_text(req.model_dump_json(), "/input/request.json")
        sb.filesystem.write_text(str(sb.object_id), "/input/sandbox-id.txt")

    def execute(self, sb: Any, timeout_seconds: int) -> int:
        p = sb.exec("python", "-c", WORKER_ENTRY, workdir="/workspace", timeout=timeout_seconds, text=True)
        p.wait()
        return int(p.returncode)

    def download(self, sb: Any, target: Path) -> tuple[Path, Path, Path]:
        target.mkdir(parents=True, exist_ok=True)
        files = (target / "result.json", target / "after.tar", target / "evidence.zip")
        for remote, local in zip(
            ("/output/result.json", "/output/after.tar", "/output/evidence.zip"), files, strict=True
        ):
            sb.filesystem.copy_to_local(remote, local)
        return files

    def terminate(self, sb: Any) -> None:
        sb.terminate(wait=True)
