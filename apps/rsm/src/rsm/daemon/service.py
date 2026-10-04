"""Authoritative daemon service — the sole state owner (Spec §3)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from ..api.errors import BucketNotFound, IllegalLifecycleTransition
from ..bucket.model import Bucket
from ..classification.model import WorkClassification, DEFAULT_CLASSIFICATION
from ..execution.model import ExecutionState
from ..extraction.text import extract_text
from ..lifecycle.events import event_log_entry
from ..lifecycle.states import State
from ..lifecycle.transitions import IllegalTransition, assert_legal
from .eventlog import EventLog
from .store import BucketStore, FsStore
from ..interaction.store import InteractionStore
from ..interaction.model import InteractionRecord, DEFAULT_INTERACTION


class DaemonService:
    def __init__(self, store: BucketStore, eventlog: EventLog, interactions: InteractionStore | None = None):
        self.store = store
        self.eventlog = eventlog
        # Classification + execution live in-memory keyed by bucket_id
        # (persistence of these auxiliary records is out of scope for V1).
        self._classification: dict[str, WorkClassification] = {}
        self._execution: dict[str, ExecutionState] = {}
        # V3: InteractionStore follows the same in-memory discipline.
        self.interactions: InteractionStore = interactions or InteractionStore()

    # ---------- ingestion ----------
    def ingest_text(
        self,
        content: str,
        *,
        source_uri: str | None = None,
        kind: Literal["text", "pasted", "stdin"] = "text",
        expected_hash: str | None = None,
    ) -> Bucket:
        bucket = extract_text(content, source_uri=source_uri, kind=kind)
        return self._accept(bucket, expected_hash=expected_hash)

    # ---------- additional ingestion surfaces (Phase 8) ----------
    def _accept(self, bucket, *, expected_hash: str | None):
        """Verify (optional) supplied hash, write to store, log RECEIVED."""
        from ..integrity.verify import verify_supplied_hash
        if expected_hash is not None:
            bucket = verify_supplied_hash(bucket, expected_hash)
        self.store.write(bucket)
        self._classification[bucket.bucket_id] = DEFAULT_CLASSIFICATION
        self.eventlog.append(
            event_log_entry(bucket.bucket_id, from_state=None, to_state=State.RECEIVED)
        )
        return bucket

    def ingest_markdown(
        self,
        text: str,
        *,
        source_uri: str | None = None,
        expected_hash: str | None = None,
    ) -> Bucket:
        from ..extraction.markdown import extract_markdown
        bucket = extract_markdown(text, source_uri=source_uri)
        return self._accept(bucket, expected_hash=expected_hash)

    def ingest_pdf(
        self,
        pdf_bytes: bytes,
        *,
        source_uri: str | None = None,
        expected_hash: str | None = None,
    ) -> Bucket:
        from ..extraction.pdf import extract_pdf
        bucket = extract_pdf(pdf_bytes, source_uri=source_uri)
        return self._accept(bucket, expected_hash=expected_hash)

    def ingest_opaque(
        self,
        content_bytes: bytes,
        *,
        source_uri: str | None = None,
        media_type: str | None = None,
        expected_hash: str | None = None,
    ) -> Bucket:
        from ..extraction.opaque import extract_opaque
        bucket = extract_opaque(content_bytes, source_uri=source_uri, media_type=media_type)
        return self._accept(bucket, expected_hash=expected_hash)

    def ingest_chatgpt_export(
        self,
        payload: dict,
        *,
        source_uri: str | None = None,
        expected_hash: str | None = None,
    ) -> Bucket:
        from ..extraction.chatgpt_export import extract_chatgpt_export
        bucket = extract_chatgpt_export(payload, source_uri=source_uri)
        return self._accept(bucket, expected_hash=expected_hash)

    def ingest_folder(
        self,
        root_path,
        *,
        expected_hash: str | None = None,
    ):
        """Ingest a folder (A3). Returns (parent_bucket, [child_buckets]).

        The parent manifest Bucket is persisted first; each child Bucket is
        then persisted with provenance.derived_from = parent.bucket_id.
        A single supplied hash, if any, is verified against the parent.
        """
        from ..extraction.folder import extract_folder
        result = extract_folder(root_path)
        parent = result.parent
        parent = self._accept(parent, expected_hash=expected_hash)
        children = []
        for child in result.children:
            self.store.write(child)
            self._classification[child.bucket_id] = DEFAULT_CLASSIFICATION
            self.eventlog.append(
                event_log_entry(child.bucket_id, from_state=None, to_state=State.RECEIVED)
            )
            children.append(child)
        return parent, children

    def ingest_zip(
        self,
        zip_path,
        *,
        expected_hash: str | None = None,
    ):
        """Ingest a ZIP archive (Phase 6). Enumerates entries safely and
        materialises each supported file as its own Bucket, with
        provenance.derived_from pointing at a parent "zip-manifest" Bucket.

        The parent Bucket's `full_content` is the canonical manifest JSON —
        same shape convention as folder ingestion.
        """
        import json as _json
        from pathlib import Path as _P
        from ..extraction._common import build_bucket
        from ..extraction.markdown import extract_markdown
        from ..extraction.text import extract_text
        from ..extraction.pdf import extract_pdf
        from ..extraction.opaque import extract_opaque
        from ..loading.archive import enumerate_zip
        manifest = enumerate_zip(zip_path)
        src_path = str(_P(zip_path).resolve())
        parent_doc = {
            "deterministic_ordering": manifest.deterministic_ordering,
            "entries": [
                {"posix_path": e.posix_path, "size_bytes": e.size_bytes}
                for e in manifest.entries
            ],
            "total_bytes": manifest.total_bytes,
            "source_zip": src_path,
        }
        parent = build_bucket(
            origin="opaque",
            full_content=_json.dumps(parent_doc, sort_keys=True, separators=(",", ":")),
            source_uri=src_path,
            metadata={"archive_kind": "zip", "entry_count": len(manifest.entries)},
        )
        parent = self._accept(parent, expected_hash=expected_hash)
        children: list[Bucket] = []
        for e in manifest.entries:
            data = manifest.read_entry(e)
            lower = e.posix_path.lower()
            if lower.endswith((".md", ".markdown")):
                child = extract_markdown(data.decode("utf-8", errors="replace"),
                                         source_uri=f"{src_path}!{e.posix_path}")
            elif lower.endswith(".pdf"):
                child = extract_pdf(data, source_uri=f"{src_path}!{e.posix_path}")
            elif lower.endswith((".txt", ".json", ".log", ".html", ".xml")):
                child = extract_text(data.decode("utf-8", errors="replace"),
                                     source_uri=f"{src_path}!{e.posix_path}",
                                     kind="text")
            else:
                child = extract_opaque(data, source_uri=f"{src_path}!{e.posix_path}",
                                       media_type=None)
            # Replace provenance.derived_from — rebuild the Bucket because
            # Bucket is frozen past STORED; we never reach STORED here.
            new_prov = child.provenance.model_copy(update={"derived_from": parent.bucket_id})
            child_rebuilt = build_bucket(
                origin=child.provenance.origin,
                full_content=child.full_content,
                source_uri=child.provenance.source_uri,
                derived_from=parent.bucket_id,
                metadata=dict(child.metadata),
            )
            self.store.write(child_rebuilt)
            self._classification[child_rebuilt.bucket_id] = DEFAULT_CLASSIFICATION
            self.eventlog.append(
                event_log_entry(child_rebuilt.bucket_id, from_state=None, to_state=State.RECEIVED)
            )
            children.append(child_rebuilt)
        return parent, children

    # ---------- listing ----------
    def list_bucket_ids(self) -> list[str]:
        return list(self.store.iter_ids())

    # ---------- transitions ----------
    def transition(self, bucket_id: str, to: str) -> Bucket:
        bucket = self.store.read(bucket_id)
        if bucket is None:
            raise BucketNotFound(f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id})
        try:
            src = State(bucket.state)
            dst = State(to)
            assert_legal(src, dst)
        except (IllegalTransition, ValueError) as e:
            raise IllegalLifecycleTransition(str(e), details={"from": bucket.state, "to": to})

        now = datetime.now(timezone.utc)
        bucket.state = dst  # type: ignore[assignment]
        ts_field = {
            State.STAGED: "staged_at",
            State.STORED: "stored_at",
            State.ACTIVATED: "activated_at",
            State.REPLAYED: "replayed_at",
            State.RELEASED: "released_at",
            State.RETIRED: "retired_at",
        }.get(dst)
        if ts_field:
            setattr(bucket.lifecycle, ts_field, now)
        if src == State.RELEASED and dst == State.ACTIVATED:
            bucket.lifecycle.release_count += 1
        self.store.write(bucket)
        self.eventlog.append(event_log_entry(bucket_id, from_state=src, to_state=dst))
        return bucket

    # ---------- classification (independent of lifecycle) ----------
    def get_classification(self, bucket_id: str) -> WorkClassification:
        if self.store.read(bucket_id) is None:
            raise BucketNotFound(f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id})
        return self._classification.get(bucket_id, DEFAULT_CLASSIFICATION)

    def set_classification(
        self, bucket_id: str, classification: WorkClassification | str
    ) -> WorkClassification:
        if self.store.read(bucket_id) is None:
            raise BucketNotFound(f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id})
        cls = (
            WorkClassification(classification)
            if not isinstance(classification, WorkClassification)
            else classification
        )
        self._classification[bucket_id] = cls
        return cls

    # ---------- execution state (independent of lifecycle/content) ----------
    def get_execution(self, bucket_id: str) -> ExecutionState:
        if self.store.read(bucket_id) is None:
            raise BucketNotFound(f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id})
        return self._execution.get(bucket_id, ExecutionState(bucket_id=bucket_id))

    def put_execution(self, state: ExecutionState) -> ExecutionState:
        if self.store.read(state.bucket_id) is None:
            raise BucketNotFound(
                f"No bucket with id {state.bucket_id!r}", details={"bucket_id": state.bucket_id}
            )
        self._execution[state.bucket_id] = state
        return state


    # ---------- V3: interaction records (ADR 0009) ----------
    def get_interaction(self, interaction_id: str) -> InteractionRecord:
        """Return the stored interaction record or a fail-closed default.

        Reading does NOT persist a default record.
        """
        return self.interactions.get(interaction_id)

    def put_interaction(self, record: InteractionRecord) -> InteractionRecord:
        """Validate `selected_bucket_id` (if any) exists, then persist."""
        if record.selected_bucket_id is not None:
            if self.store.read(record.selected_bucket_id) is None:
                raise BucketNotFound(
                    f"No bucket with id {record.selected_bucket_id!r}",
                    details={"bucket_id": record.selected_bucket_id},
                )
        return self.interactions.put(record)

# ---- FastAPI dependency wiring ----

_default_daemon: DaemonService | None = None


def _default_root() -> Path:
    # Active config (see rsm.config.runtime); "./.rsm-store" is the default,
    # preserving the pre-wiring behaviour when no config file is present.
    from ..config import get_active_config

    root = Path(get_active_config().persistence.root)
    return root if root.is_absolute() else Path.cwd() / root


def get_daemon() -> DaemonService:
    global _default_daemon
    if _default_daemon is None:
        root = _default_root()
        _default_daemon = DaemonService(
            store=FsStore(root / "buckets"),
            eventlog=EventLog(root / "events.log"),
        )
    return _default_daemon
