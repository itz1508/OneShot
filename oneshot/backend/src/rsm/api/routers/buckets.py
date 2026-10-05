"""Bucket endpoints — read/create/transition + activate/release/replay/export,
plus classification & execution auxiliary records (spec §13, §14)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from ...bucket.serializer import canonical_dumps
from ...classification.model import WorkClassification
from ...daemon.service import DaemonService, get_daemon
from ...execution.model import ExecutionState
from ...replay.envelope import build_replay_envelope
from ...snapshot import (
    ContextBudget,
    BudgetUnit,
    build_snapshot,
    SummaryUnavailable,
    SnapshotBuildError,
    PrefixSummaryProvider,
    NullSummaryProvider,
)
from ..errors import RSMError, RsmDisabled

from ...transports.canonical import build_payload
from ...transports.http.view import http_view
from ..errors import BucketNotFound

router = APIRouter()


@router.get("/")
async def list_buckets(daemon: DaemonService = Depends(get_daemon)):
    return {"bucket_ids": daemon.list_bucket_ids()}


@router.post("/")
async def ingest(body: dict, daemon: DaemonService = Depends(get_daemon)):
    """POST /v1/buckets/ — multi-origin ingest dispatcher (Phase 8).

    Body:
      {
        "kind": "text"|"pasted"|"stdin"|"markdown"|"pdf"|"opaque"|"chatgpt_export"|"folder"|"zip",
        "content"?: str                     # text/pasted/stdin/markdown
        "content_base64"?: str              # pdf/opaque (base64 bytes)
        "filename"?: str                    # opaque
        "path"?: str                        # folder/zip (local path)
        "payload"?: object                  # chatgpt_export
        "source_uri"?: str                  # provenance only
        "expected_hash"?: str               # optional supplied SHA-256
      }

    Returns the canonical Bucket payload. For `folder`/`zip` the
    PARENT Bucket is returned; child Buckets are available via
    `/v1/buckets/` list.
    """
    import base64
    from ..errors import BucketFrozen
    kind = body.get("kind", "text")
    source_uri = body.get("source_uri")
    expected_hash = body.get("expected_hash")
    try:
        if kind in ("text", "pasted", "stdin"):
            bucket = daemon.ingest_text(
                body.get("content", ""),
                source_uri=source_uri,
                kind=kind,
                expected_hash=expected_hash,
            )
        elif kind == "markdown":
            bucket = daemon.ingest_markdown(
                body.get("content", ""),
                source_uri=source_uri,
                expected_hash=expected_hash,
            )
        elif kind == "pdf":
            data = base64.b64decode(body.get("content_base64", ""))
            bucket = daemon.ingest_pdf(
                data, source_uri=source_uri, expected_hash=expected_hash,
            )
        elif kind == "opaque":
            data = base64.b64decode(body.get("content_base64", ""))
            bucket = daemon.ingest_opaque(
                data,
                source_uri=source_uri,
                media_type=body.get("media_type"),
                expected_hash=expected_hash,
            )
        elif kind == "chatgpt_export":
            payload = body.get("payload") or {}
            bucket = daemon.ingest_chatgpt_export(
                payload, source_uri=source_uri, expected_hash=expected_hash,
            )
        elif kind == "folder":
            parent, _children = daemon.ingest_folder(
                body.get("path", ""), expected_hash=expected_hash,
            )
            bucket = parent
        elif kind == "zip":
            parent, _children = daemon.ingest_zip(
                body.get("path", ""), expected_hash=expected_hash,
            )
            bucket = parent
        else:
            from fastapi import HTTPException
            raise HTTPException(400, {"code": "UNSUPPORTED_KIND", "message": f"kind={kind!r}"})
    except __import__("rsm.integrity.verify", fromlist=["SuppliedHashMismatch"]).SuppliedHashMismatch as e:
        from fastapi import HTTPException
        raise HTTPException(422, {"code": "HASH_MISMATCH", "message": str(e),
                                   "details": {"bucket_id": e.bucket_id,
                                               "expected": e.expected,
                                               "actual": e.actual}})
    return http_view(build_payload(bucket))


@router.post("/upload-zip")
async def upload_zip(
    file: UploadFile | None = File(default=None),
    source_uri: str | None = Form(default=None),
    expected_hash: str | None = Form(default=None),
    daemon: DaemonService = Depends(get_daemon),
):
    """POST /v1/buckets/upload-zip — browser multipart ZIP upload.

    This is the browser-origin counterpart to the dispatcher's ``kind=zip``
    path, which only accepts a local filesystem path. The bytes are
    streamed into a temporary file, then handed to the existing
    ``daemon.ingest_zip`` (which uses ``rsm.loading.archive.enumerate_zip``
    + per-child extractor + the common accept path). The temp file is
    deleted in ``finally``; nothing persists on disk beyond the Bucket
    JSON files produced by ``FsStore``.

    Response: canonical parent-Bucket payload, augmented with
    ``children: [bucket_id, ...]``. Errors:

    * 400 ``MISSING_FILE``       — no file in the multipart body
    * 400 ``ARCHIVE_SAFETY``     — zip-slip / symlink / oversized / etc.
    * 422 ``HASH_MISMATCH``      — ``expected_hash`` did not match the
      canonical preimage of the parent Bucket.
    """
    import os as _os
    import tempfile as _tempfile
    from ...integrity.verify import SuppliedHashMismatch
    from ...loading.archive import ArchiveSafetyError

    if file is None:
        raise HTTPException(
            400,
            {"code": "MISSING_FILE", "message": "multipart 'file' field is required"},
        )

    tmp = _tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp_path = tmp.name
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
        tmp.close()
        try:
            parent, children = daemon.ingest_zip(tmp_path, expected_hash=expected_hash)
        except SuppliedHashMismatch as e:
            raise HTTPException(
                422,
                {
                    "code": "HASH_MISMATCH",
                    "message": str(e),
                    "details": {
                        "bucket_id": e.bucket_id,
                        "expected": e.expected,
                        "actual": e.actual,
                    },
                },
            )
        except ArchiveSafetyError as e:
            raise HTTPException(
                400,
                {"code": "ARCHIVE_SAFETY", "message": str(e)},
            )
    finally:
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass

    body = http_view(build_payload(parent))
    body["children"] = [c.bucket_id for c in children]
    return body


@router.get("/{bucket_id}")
async def read_bucket(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    b = daemon.store.read(bucket_id)
    if b is None:
        raise BucketNotFound(f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id})
    return http_view(build_payload(b))


@router.post("/{bucket_id}/transition")
async def transition(bucket_id: str, body: dict, daemon: DaemonService = Depends(get_daemon)):
    target = body.get("to")
    bucket = daemon.transition(bucket_id, target)
    return http_view(build_payload(bucket))


@router.post("/{bucket_id}/activate")
async def activate(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    """Sugar for 'transition to ACTIVATED'. Fails per lifecycle machine."""
    bucket = daemon.transition(bucket_id, "ACTIVATED")
    return http_view(build_payload(bucket))


@router.post("/{bucket_id}/release")
async def release(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    """Sugar for 'transition to RELEASED'. Fails per lifecycle machine."""
    bucket = daemon.transition(bucket_id, "RELEASED")
    return http_view(build_payload(bucket))


@router.get("/{bucket_id}/replay")
async def replay(
    bucket_id: str,
    interaction_id: str | None = None,
    daemon: DaemonService = Depends(get_daemon),
):
    """Replay envelope (spec §14). Read-only. Does not mutate the bucket.

    V3 (ADR 0009): when a caller supplies `interaction_id`, the request is
    gated on the interaction's `rsm_enabled` flag. Unknown or disabled
    interactions receive `409 RSM_DISABLED`. Legacy callers that omit
    `interaction_id` retain V1/V2 behaviour (no gate) — this compatibility
    boundary is explicit and documented in docs/rsm-v3-implementation.md.
    """
    if interaction_id is not None:
        rec = daemon.get_interaction(interaction_id)
        if not rec.rsm_enabled:
            raise RsmDisabled(
                "RSM is disabled for this interaction",
                details={"interaction_id": interaction_id},
            )
    b = daemon.store.read(bucket_id)
    if b is None:
        raise BucketNotFound(f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id})
    cls = daemon.get_classification(bucket_id)
    return build_replay_envelope(b, classification=cls)


@router.get("/{bucket_id}/export")
async def export_bucket(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    """Canonical JSON bytes export (the hash preimage)."""
    b = daemon.store.read(bucket_id)
    if b is None:
        raise BucketNotFound(f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id})
    body = canonical_dumps(b.model_dump(mode="json"))
    return Response(content=body, media_type="application/json")


# --- classification (independent of lifecycle) ---

@router.get("/{bucket_id}/classification")
async def get_classification(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    cls = daemon.get_classification(bucket_id)
    return {"bucket_id": bucket_id, "work_classification": cls.value}


@router.put("/{bucket_id}/classification")
async def put_classification(
    bucket_id: str, body: dict, daemon: DaemonService = Depends(get_daemon)
):
    cls = daemon.set_classification(bucket_id, body.get("work_classification"))
    return {"bucket_id": bucket_id, "work_classification": cls.value}


# --- execution state (independent of lifecycle, references bucket_id) ---

@router.get("/{bucket_id}/execution")
async def get_execution(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    return daemon.get_execution(bucket_id).to_envelope()


@router.put("/{bucket_id}/execution")
async def put_execution(bucket_id: str, body: dict, daemon: DaemonService = Depends(get_daemon)):
    # body is the ExecutionState payload (bucket_id must match path)
    body = {**body, "bucket_id": bucket_id}
    state = ExecutionState.model_validate(body)
    return daemon.put_execution(state).to_envelope()

class _SnapshotBuildFailed(RSMError):
    code = "SNAPSHOT_BUILD_FAILED"
    http_status = 422


class _SummaryUnavailable(RSMError):
    code = "SUMMARY_UNAVAILABLE"
    http_status = 409


class _InvalidBudget(RSMError):
    code = "INVALID_BUDGET"
    http_status = 422


@router.get("/{bucket_id}/snapshot")
async def snapshot(
    bucket_id: str,
    budget_unit: str = "characters",
    budget_value: int = 2000,
    reduce: str = "null",
    interaction_id: str | None = None,
    daemon: DaemonService = Depends(get_daemon),
):
    """Bounded, derived Snapshot projection of a Bucket (spec §3-§5).

    Query parameters:
      - budget_unit:  bytes | characters | tokens_estimate
      - budget_value: positive integer
      - reduce:       null (default) -> fail with SUMMARY_UNAVAILABLE if source
                      exceeds budget;
                      prefix -> use the deterministic PrefixSummaryProvider.
      - interaction_id: optional (V3). When supplied the request is gated on
                        the interaction's `rsm_enabled` flag (ADR 0009).
                        Legacy callers that omit it retain V1/V2 behaviour.
    """
    if interaction_id is not None:
        rec = daemon.get_interaction(interaction_id)
        if not rec.rsm_enabled:
            raise RsmDisabled(
                "RSM is disabled for this interaction",
                details={"interaction_id": interaction_id},
            )
    b = daemon.store.read(bucket_id)
    if b is None:
        raise BucketNotFound(f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id})
    try:
        unit = BudgetUnit(budget_unit)
        budget = ContextBudget(unit=unit, value=budget_value)
    except Exception as e:
        raise _InvalidBudget(f"Invalid budget: {e}", details={"budget_unit": budget_unit, "budget_value": budget_value})
    provider = {
        "null": NullSummaryProvider(),
        "prefix": PrefixSummaryProvider(),
    }.get(reduce)
    if provider is None:
        raise _InvalidBudget(f"Unknown reduce mode {reduce!r}", details={"reduce": reduce})
    try:
        snap = build_snapshot(b, budget=budget, summary_provider=provider)
    except SummaryUnavailable as e:
        raise _SummaryUnavailable(str(e), details={"bucket_id": bucket_id})
    except SnapshotBuildError as e:
        raise _SnapshotBuildFailed(str(e), details={"bucket_id": bucket_id})
    return snap.model_dump(mode="json")

