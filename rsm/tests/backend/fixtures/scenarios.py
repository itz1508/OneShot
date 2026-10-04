"""RSM V3 — release-validation fixture matrix (TEST-ONLY).

Each entry declares:

    scenario_id         stable id
    category            Source | Files | Reader | Content | Processor | Security
    description         one-sentence intent
    builder             callable(tmp_path) -> Bucket (bytes-faithful; deterministic)
    expected_files      int or None (SCAN output size)
    expected_observed   int or None (Reader observed_count)
    expected_failed     int or None (Reader failed_count)
    expected_failure_reasons   set[str] or None (per-File failure reason strings)
    expected_latest     int or None (ReaderTrace.latest_index)
    expected_hash_stable       bool (hash unchanged after scan/read/snapshot/replay)
    expected_snapshot_text     str or None (preserved-mode content equality)
    expected_opaque_file_names set[str] or None (names reported as opaque by SCAN)

A field left None is treated as "not applicable" and is not asserted.

The matrix is intentionally built from the existing extractors (`rsm.extraction`)
and existing primitives — no new production domain object is introduced. The
`builder` callables are plain closures over `tmp_path` or in-process state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from rsm.bucket.model import Bucket, Hash, Provenance
from rsm.bucket.serializer import canonical_dumps
from rsm.extraction.folder import extract_folder
from rsm.extraction.text import extract_text
from rsm.integrity.sha256 import sha256_bytes


BucketBuilder = Callable[[Path], Bucket]


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    category: str
    description: str
    builder: BucketBuilder
    expected_files: Optional[int] = None
    expected_observed: Optional[int] = None
    expected_failed: Optional[int] = None
    expected_failure_reasons: Optional[frozenset[str]] = None
    expected_latest: Optional[int] = None
    expected_hash_stable: bool = True
    expected_snapshot_text: Optional[str] = None
    expected_opaque_file_names: Optional[frozenset[str]] = None


# ------------------------------- helpers -------------------------------------


def _synthetic_folder_bucket(
    *,
    supported: list[str],
    opaque: list[str] | None = None,
    unsupported: list[str] | None = None,
    source_uri: str = "synthetic:/matrix",
) -> Bucket:
    """Build a folder-origin Bucket from a synthetic manifest without touching disk.

    The scanner reads `entries.{supported,opaque,unsupported}` directly out of
    `Bucket.full_content`, so a canonical JSON manifest is enough to drive the
    full SCAN/Reader pipeline deterministically — and is the lever that makes
    the 10,000-file scenario possible without materialising 10,000 real files.
    """
    opaque = opaque or []
    unsupported = unsupported or []
    manifest = {
        "root": "synthetic",
        "deterministic_ordering": "sorted_posix_path_ascending",
        "source_count": len(supported),
        "unsupported_count": len(unsupported),
        "opaque_count": len(opaque),
        "skipped_permission_denied": 0,
        "max_depth_observed": 1,
        "entries": {
            "supported": sorted(supported),
            "opaque": sorted(opaque),
            "unsupported": sorted(unsupported),
        },
    }
    canonical = canonical_dumps(manifest)
    bid = "bkt_" + sha256_bytes(canonical)[:32]
    produced_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Bucket(
        schema_version="1",
        bucket_id=bid,
        hash=Hash(algorithm="sha256", value=sha256_bytes(canonical)),
        provenance=Provenance(
            origin="folder",
            source_uri=source_uri,
            derived_from=None,
            produced_at=produced_at,
        ),
        full_content=canonical.decode("utf-8"),
        metadata={
            "source_count": manifest["source_count"],
            "unsupported_count": manifest["unsupported_count"],
            "opaque_count": manifest["opaque_count"],
            "skipped_permission_denied": 0,
            "max_depth_observed": 1,
            "deterministic_ordering": "sorted_posix_path_ascending",
        },
    )


def _real_folder_bucket(tmp_path: Path, files: dict[str, bytes]) -> Bucket:
    root = tmp_path / "root"
    root.mkdir()
    for name, content in files.items():
        (root / name).write_bytes(content)
    return extract_folder(root).parent


# ----------------------------- scenario builders -----------------------------
# (Builders accept tmp_path and return a Bucket; builders that do not need the
#  filesystem simply ignore the argument.)


def _b_simple_text(_tmp: Path) -> Bucket:
    return extract_text("hello world", source_uri="simple.txt")


def _b_markdown(_tmp: Path) -> Bucket:
    body = "# Title\n\nSome prose and a `code span`.\n"
    return extract_text(body, source_uri="doc.md", kind="pasted")


def _b_empty(_tmp: Path) -> Bucket:
    return extract_text("", source_uri="empty.txt")


def _b_whitespace(_tmp: Path) -> Bucket:
    return extract_text("   \n\t  \n\n", source_uri="whitespace.txt")


def _b_unicode(_tmp: Path) -> Bucket:
    body = "Привет 🌍 — élève · 日本語 · emoji 🚀"
    return extract_text(body, source_uri="unicode.txt")


def _b_tiny(_tmp: Path) -> Bucket:
    return extract_text("a")


def _b_two_readable_files(tmp_path: Path) -> Bucket:
    return _real_folder_bucket(
        tmp_path,
        {"a.txt": b"alpha", "b.md": b"# beta"},
    )


def _b_mixed_readable_unsupported(tmp_path: Path) -> Bucket:
    return _real_folder_bucket(
        tmp_path,
        {
            "ok.txt": b"readable",
            "weird.xyz": b"not supported",
        },
    )


def _b_canonical_ordering(tmp_path: Path) -> Bucket:
    # Reversed insertion order; expected order is sorted ascending by posix name.
    return _real_folder_bucket(
        tmp_path,
        {"c.txt": b"3", "a.txt": b"1", "b.txt": b"2"},
    )


def _b_duplicate_looking_names(tmp_path: Path) -> Bucket:
    return _real_folder_bucket(
        tmp_path,
        {"a.txt": b"same", "A.txt": b"same"},
    )


def _b_large_manifest(_tmp: Path) -> Bucket:
    supported = [f"file_{i:05d}.txt" for i in range(1, 10001)]
    return _synthetic_folder_bucket(supported=supported, source_uri="synthetic:/large")


def _b_unusual_metadata(_tmp: Path) -> Bucket:
    # text extractor + bucket metadata default — the custom metadata path exercises
    # the bucket model's `extra="forbid"` guard elsewhere. Here we only need a
    # Bucket with page-count-like metadata to exercise the SCAN hint path.
    bucket = extract_text("page one\npage two\npage three", source_uri="doc.txt")
    # Metadata is immutable after STORED but Buckets created by the text extractor
    # are RECEIVED; we can set metadata directly on the model instance before any
    # store write.
    bucket.metadata["page_count"] = 3
    return bucket


def _b_opaque_image_only(tmp_path: Path) -> Bucket:
    return _real_folder_bucket(
        tmp_path, {"only.png": b"\x89PNG\r\n\x1a\n"}
    )


def _b_malformed(tmp_path: Path) -> Bucket:
    return _real_folder_bucket(tmp_path, {"strange.doesnotexist": b"xx"})


def _b_table_like(_tmp: Path) -> Bucket:
    body = "name\tvalue\nalpha\t1\nbeta\t2\n"
    return extract_text(body, source_uri="table.tsv")


def _b_vision_required(tmp_path: Path) -> Bucket:
    return _real_folder_bucket(
        tmp_path,
        {"photo.jpg": b"\xff\xd8\xff\xe0", "text.txt": b"caption"},
    )


def _b_oversized_text(_tmp: Path) -> Bucket:
    body = "x" * (16 * 1024)  # 16 KiB — exercises the budget-overflow path
    return extract_text(body, source_uri="oversized.txt")


# -------------------------------- matrix ------------------------------------

SCENARIOS: list[Scenario] = [
    # ---- Source ----
    Scenario(
        scenario_id="src-simple-text",
        category="Source",
        description="Simple ASCII text source",
        builder=_b_simple_text,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
        expected_snapshot_text="hello world",
    ),
    Scenario(
        scenario_id="src-markdown",
        category="Source",
        description="Markdown with structure (headings, inline code)",
        builder=_b_markdown,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="src-empty",
        category="Source",
        description="Empty source body",
        builder=_b_empty,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
        expected_snapshot_text="",
    ),
    Scenario(
        scenario_id="src-whitespace",
        category="Source",
        description="Whitespace-heavy source",
        builder=_b_whitespace,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="src-unicode",
        category="Source",
        description="Unicode / multilingual source",
        builder=_b_unicode,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="src-tiny",
        category="Source",
        description="One-byte source",
        builder=_b_tiny,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
        expected_snapshot_text="a",
    ),

    # ---- Files ----
    Scenario(
        scenario_id="files-two-readable",
        category="Files",
        description="Folder with two readable Files",
        builder=_b_two_readable_files,
        expected_files=2,
        expected_observed=2,
        expected_failed=0,
        expected_latest=2,
    ),
    Scenario(
        scenario_id="files-mixed-unsupported",
        category="Files",
        description="Folder with one readable + one unsupported-extension File",
        builder=_b_mixed_readable_unsupported,
        expected_files=2,
        expected_observed=1,
        expected_failed=1,
        expected_failure_reasons=frozenset({"unsupported_extension"}),
        expected_latest=2,
    ),
    Scenario(
        scenario_id="files-canonical-ordering",
        category="Files",
        description="File ordering is sorted-ascending by posix path",
        builder=_b_canonical_ordering,
        expected_files=3,
        expected_observed=3,
        expected_failed=0,
        expected_latest=3,
    ),
    Scenario(
        scenario_id="files-duplicate-looking-names",
        category="Files",
        description="Names that look duplicated are preserved verbatim",
        builder=_b_duplicate_looking_names,
        expected_files=2,
        expected_observed=2,
        expected_failed=0,
        expected_latest=2,
    ),
    Scenario(
        scenario_id="files-large-manifest",
        category="Files",
        description="10,000-file synthetic folder manifest (no disk I/O)",
        builder=_b_large_manifest,
        expected_files=10_000,
        expected_observed=10_000,
        expected_failed=0,
        expected_latest=10_000,
    ),
    Scenario(
        scenario_id="files-unusual-metadata",
        category="Files",
        description="Bucket metadata carries a page_count hint",
        builder=_b_unusual_metadata,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),

    # ---- Reader ----
    Scenario(
        scenario_id="reader-single-success",
        category="Reader",
        description="Reader observes a single File",
        builder=_b_simple_text,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="reader-one-failure-with-success",
        category="Reader",
        description="Image failure is isolated to its File (reader completes)",
        builder=_b_vision_required,
        expected_files=2,
        expected_observed=1,
        expected_failed=1,
        expected_failure_reasons=frozenset({"vision_unavailable"}),
        expected_latest=2,
    ),
    Scenario(
        scenario_id="reader-multiple-isolated-failures",
        category="Reader",
        description="Multiple failures remain isolated",
        builder=lambda tmp: _real_folder_bucket(
            tmp,
            {
                "ok.txt": b"ok",
                "image.png": b"\x89PNG\r\n\x1a\n",
                "weird.xyz": b"nope",
            },
        ),
        expected_files=3,
        expected_observed=1,
        expected_failed=2,
        expected_failure_reasons=frozenset(
            {"vision_unavailable", "unsupported_extension"}
        ),
        expected_latest=3,
    ),
    Scenario(
        scenario_id="reader-opaque-partial",
        category="Reader",
        description="Opaque-only folder yields a single isolated opaque failure",
        builder=_b_opaque_image_only,
        expected_files=1,
        expected_observed=0,
        expected_failed=1,
        expected_failure_reasons=frozenset({"vision_unavailable"}),
        expected_latest=1,
    ),
    Scenario(
        scenario_id="reader-reaches-final-file",
        category="Reader",
        description="latest_index reaches the final File",
        builder=lambda tmp: _real_folder_bucket(
            tmp, {f"a_{i}.txt": b"x" for i in range(1, 6)}
        ),
        expected_files=5,
        expected_observed=5,
        expected_failed=0,
        expected_latest=5,
    ),

    # ---- Content ----
    Scenario(
        scenario_id="content-table-like",
        category="Content",
        description="Table-like source (TSV)",
        builder=_b_table_like,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="content-vision-required",
        category="Content",
        description="Image File requires Vision and is failed-isolated",
        builder=_b_vision_required,
        expected_files=2,
        expected_observed=1,
        expected_failed=1,
        expected_failure_reasons=frozenset({"vision_unavailable"}),
        expected_latest=2,
    ),
    Scenario(
        scenario_id="content-opaque-binary",
        category="Content",
        description="Opaque binary File handled as isolated failure",
        builder=_b_opaque_image_only,
        expected_files=1,
        expected_observed=0,
        expected_failed=1,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="content-malformed",
        category="Content",
        description="Malformed extension yields unsupported_extension (isolated)",
        builder=_b_malformed,
        expected_files=1,
        expected_observed=0,
        expected_failed=1,
        expected_failure_reasons=frozenset({"unsupported_extension"}),
        expected_latest=1,
    ),

    # ---- Processor / Replay ----
    Scenario(
        scenario_id="proc-preserved",
        category="Processor",
        description="Source fits budget and Snapshot kind=preserved",
        builder=_b_simple_text,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
        expected_snapshot_text="hello world",
    ),
    Scenario(
        scenario_id="proc-overflow-reduction-unavailable",
        category="Processor",
        description="Source exceeds budget without a provider → SummaryUnavailable",
        builder=_b_oversized_text,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="proc-provenance-retained",
        category="Processor",
        description="Snapshot provenance.derived_from.bucket_hash == Bucket.hash.value",
        builder=_b_simple_text,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="proc-source-immutable-through-pipeline",
        category="Processor",
        description="A1: Bucket hash unchanged after scan/read/snapshot/replay-envelope",
        builder=_b_markdown,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
        expected_hash_stable=True,
    ),
    Scenario(
        scenario_id="proc-replay-identical-to-prepared",
        category="Processor",
        description="Replay delivers the prepared representation unchanged",
        builder=_b_simple_text,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),

    # ---- Security ----
    Scenario(
        scenario_id="sec-interaction-isolation",
        category="Security",
        description="Interaction A does not receive Interaction B's content",
        builder=_b_simple_text,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="sec-rsm-off-fail-closed",
        category="Security",
        description="RSM OFF rejects /stream with 409 RSM_DISABLED",
        builder=_b_simple_text,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
    Scenario(
        scenario_id="sec-unknown-interaction",
        category="Security",
        description="Unknown interaction returns fail-closed default (no release)",
        builder=_b_simple_text,
        expected_files=1,
        expected_observed=1,
        expected_failed=0,
        expected_latest=1,
    ),
]


# A compile-time contract on matrix size — the mission requires 20–30 scenarios.
assert 20 <= len(SCENARIOS) <= 30, f"fixture matrix size out of range: {len(SCENARIOS)}"
