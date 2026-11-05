"""Candidate validation, complete observed deltas and bounded command evidence."""

from __future__ import annotations

import hashlib
import os
import re
import selectors
import signal
import subprocess
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from .contracts import CandidateManifest, ChangedPath, CommandSpec, SandboxCommandResult, SandboxExecutionRequest
from .policy import canonical_digest, check_commands, normalize_path
from .snapshot import sha256_file


def validate_candidate(request: SandboxExecutionRequest) -> bytes:
    """Candidate bundle is data, never a source of authority."""
    check_commands(request)
    path = Path(request.candidate_bundle_ref)
    if (
        path.stat().st_size > request.limits.max_patch_bytes + 64 * 1024
        or sha256_file(path) != request.candidate_bundle_sha256
    ):
        raise ValueError("candidate bundle byte identity mismatch")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != 2 or set(names) != {"candidate.patch", "implementation-manifest.json"}:
            raise ValueError("candidate bundle contains unsupported entries")
        if any(z.getinfo(n).file_size > request.limits.max_patch_bytes for n in names):
            raise ValueError("candidate member exceeds limit")
        patch = z.read("candidate.patch")
        if not patch or len(patch) > request.limits.max_patch_bytes:
            raise ValueError("candidate patch exceeds limit")
        manifest = CandidateManifest.model_validate_json(z.read("implementation-manifest.json"))
    if (manifest.operation_id, manifest.attempt_id, manifest.work_item_id, manifest.task_revision) != (
        request.operation_id,
        request.attempt_id,
        request.work_item_id,
        request.task_revision,
    ) or manifest.source_snapshot_sha256 != request.source_snapshot_sha256:
        raise ValueError("candidate manifest assignment mismatch")
    if manifest.patch_bytes != len(patch) or manifest.patch_sha256 != hashlib.sha256(patch).hexdigest():
        raise ValueError("patch digest/size mismatch")
    from .applicator import parse_patch

    targets = tuple(p.path for p in parse_patch(patch))
    declared = tuple(normalize_path(p) for p in manifest.declared_paths)
    if (
        len(set(declared)) != len(declared)
        or set(targets) != set(declared)
        or not set(targets).issubset(request.authorized_paths)
    ):
        raise ValueError("candidate declared paths mismatch authorization")
    return patch


def build_candidate_bundle(path: Path, patch: bytes, manifest: CandidateManifest) -> str:
    if hashlib.sha256(patch).hexdigest() != manifest.patch_sha256 or len(patch) != manifest.patch_bytes:
        raise ValueError("candidate manifest digest mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        for name, data in (
            ("candidate.patch", patch),
            ("implementation-manifest.json", manifest.model_dump_json().encode()),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            z.writestr(info, data)
    return sha256_file(path)


def changed_paths(before: dict[str, dict[str, object]], after: dict[str, dict[str, object]]) -> tuple[ChangedPath, ...]:
    paths: list[ChangedPath] = []
    for p in sorted(before.keys() | after.keys()):
        a, b = before.get(p), after.get(p)
        if a == b:
            continue
        operation: Literal["create", "modify", "delete", "mode"] = (
            "create" if a is None else "delete" if b is None else "mode" if a["sha256"] == b["sha256"] else "modify"
        )
        paths.append(
            ChangedPath(
                path=p,
                operation=operation,
                before_sha256=cast(str, a["sha256"]) if a else None,
                after_sha256=cast(str, b["sha256"]) if b else None,
                before_mode=cast(int, a["mode"]) if a else None,
                after_mode=cast(int, b["mode"]) if b else None,
            )
        )
    return tuple(paths)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _redact(data: bytes) -> str:
    # Only UI excerpts. Raw retained bytes remain private evidence.
    s = data[:450].decode("utf-8", "replace")
    return re.sub(r"(?i)(token|api[_-]?key|password|secret)\s*[:=]\s*\S+", r"\1=[REDACTED]", s)


def run_command(
    cmd: CommandSpec, root: Path, output: Path, max_bytes: int
) -> tuple[SandboxCommandResult, bytes, bytes]:
    from .snapshot import _parent_fd  # trusted secure directory traversal

    if cmd.working_directory == ".":
        wd = root
    else:
        normalize_path(cmd.working_directory)
        # Validate directory hierarchy without following symlinks.
        with _parent_fd(root, cmd.working_directory + "/entry"):
            pass
        wd = root / cmd.working_directory
    started = _now()
    env = {
        k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR"}
    }
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": str(output / "pycache"), "PYTHONPATH": str(wd)})
    # Drain pipes while enforcing actual byte caps. Killing the full process group
    # prevents child processes from surviving a timed-out authorized check.
    proc = subprocess.Popen(
        cmd.argv,
        cwd=wd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,
    )
    buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    truncated = {"stdout": False, "stderr": False}
    timed_out = False
    deadline = time.monotonic() + cmd.timeout_seconds
    try:
        with selectors.DefaultSelector() as sel:
            for name, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr)):
                assert pipe is not None
                os.set_blocking(pipe.fileno(), False)
                sel.register(pipe, selectors.EVENT_READ, name)
            while sel.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                for key, _ in sel.select(timeout=min(remaining, 0.2)):
                    name = key.data
                    pipe_fd = key.fileobj if isinstance(key.fileobj, int) else key.fileobj.fileno()
                    chunk = os.read(pipe_fd, 65536)
                    if not chunk:
                        sel.unregister(key.fileobj)
                        continue
                    remaining_bytes = max_bytes - len(buffers[name])
                    buffers[name].extend(chunk[: max(0, remaining_bytes)])
                    if len(chunk) > remaining_bytes:
                        truncated[name] = True
                        break
                if any(truncated.values()):
                    break
        if timed_out or any(truncated.values()):
            os.killpg(proc.pid, signal.SIGKILL)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
    outbytes, errbytes = bytes(buffers["stdout"]), bytes(buffers["stderr"])
    exit_code, timeout = proc.returncode, timed_out
    return (
        SandboxCommandResult(
            command_id=cmd.command_id,
            argv_digest=canonical_digest(cmd.argv),
            working_directory=str(wd),
            started_at=started,
            ended_at=_now(),
            exit_code=exit_code,
            timed_out=timeout,
            stdout_sha256=hashlib.sha256(outbytes).hexdigest(),
            stderr_sha256=hashlib.sha256(errbytes).hexdigest(),
            stdout_size=len(outbytes),
            stderr_size=len(errbytes),
            stdout_truncated=truncated["stdout"],
            stderr_truncated=truncated["stderr"],
            stdout_excerpt=_redact(outbytes),
            stderr_excerpt=_redact(errbytes),
        ),
        outbytes,
        errbytes,
    )


def matches_oracle(cmd: CommandSpec, result: SandboxCommandResult) -> bool:
    if result.timed_out or result.stdout_truncated or result.stderr_truncated:
        return False
    if cmd.expected_error is not None:
        return result.exit_code not in (None, 0) and cmd.expected_error in (
            result.stdout_excerpt + result.stderr_excerpt
        )
    return result.exit_code in cmd.expected_exit_codes


def write_evidence_zip(output: Path, records: list[tuple[str, bytes, bytes]], result_json: bytes) -> tuple[str, str]:
    archive = output / "evidence.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("result.json", result_json)
        for key, stdout, stderr in records:
            z.writestr(f"commands/{key}.stdout", stdout)
            z.writestr(f"commands/{key}.stderr", stderr)
    return str(archive), sha256_file(archive)
