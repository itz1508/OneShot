"""A3 — folder ingestion.

Produces exactly ONE parent folder bucket containing a manifest and the
required count fields:

  source_count, unsupported_count, opaque_count,
  skipped_permission_denied, max_depth_observed,
  deterministic_ordering = "sorted_posix_path_ascending"

Each supported child file becomes its own bucket whose
provenance.derived_from equals the folder bucket's bucket_id.

The parent's hash.value is SHA-256 of the canonical JSON of the manifest.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from ..bucket.model import Bucket, Hash, Provenance
from ..integrity.sha256 import sha256_bytes
from ..bucket.serializer import canonical_dumps
from ._common import build_bucket, new_bucket_id, _utcnow

# File extensions treated as supported RSM sources (not exhaustive — the real
# routing is per-extractor; this is the folder-scan admission test).
SUPPORTED_SUFFIXES: frozenset[str] = frozenset({
    ".md", ".markdown", ".txt", ".json", ".pdf",
})

OPAQUE_SUFFIXES: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
    ".bin", ".dat", ".zip", ".tar", ".gz", ".7z",
})


@dataclass
class FolderExtractionResult:
    parent: Bucket
    children: list[Bucket] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


def _rel_posix(path: Path, root: Path) -> str:
    return str(PurePosixPath(path.relative_to(root).as_posix()))


def _scan(root: Path) -> tuple[list[Path], list[Path], list[Path], int, int]:
    """Walk `root` and return (supported, opaque, unsupported, skipped_perm,
    max_depth)."""
    supported: list[Path] = []
    opaque: list[Path] = []
    unsupported: list[Path] = []
    skipped_perm = 0
    max_depth = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        try:
            # Trigger EACCES early if present.
            os.listdir(dirpath)
        except PermissionError:
            skipped_perm += 1
            continue

        depth = len(Path(dirpath).relative_to(root).parts)
        if depth > max_depth:
            max_depth = depth

        # Deterministic traversal
        dirnames.sort()
        for name in sorted(filenames):
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except (PermissionError, FileNotFoundError):
                skipped_perm += 1
                continue
            if not os.path.isfile(p) or st.st_size < 0:
                continue
            sfx = p.suffix.lower()
            if sfx in SUPPORTED_SUFFIXES:
                supported.append(p)
            elif sfx in OPAQUE_SUFFIXES:
                opaque.append(p)
            else:
                unsupported.append(p)
    supported.sort(key=lambda p: _rel_posix(p, root))
    opaque.sort(key=lambda p: _rel_posix(p, root))
    unsupported.sort(key=lambda p: _rel_posix(p, root))
    return supported, opaque, unsupported, skipped_perm, max_depth


def _manifest_dict(
    *,
    root: Path,
    supported: Iterable[Path],
    opaque: Iterable[Path],
    unsupported: Iterable[Path],
    skipped_perm: int,
    max_depth: int,
) -> dict:
    supported_list = [_rel_posix(p, root) for p in supported]
    opaque_list = [_rel_posix(p, root) for p in opaque]
    unsupported_list = [_rel_posix(p, root) for p in unsupported]

    return {
        "root": str(PurePosixPath(root.name)),
        "deterministic_ordering": "sorted_posix_path_ascending",
        "source_count": len(supported_list),
        "unsupported_count": len(unsupported_list),
        "opaque_count": len(opaque_list),
        "skipped_permission_denied": skipped_perm,
        "max_depth_observed": max_depth,
        "entries": {
            "supported": supported_list,
            "opaque": opaque_list,
            "unsupported": unsupported_list,
        },
    }


def extract_folder(
    root_path: str | os.PathLike[str],
    *,
    child_extractor: Callable[[Path, str], Bucket] | None = None,
) -> FolderExtractionResult:
    """Ingest a folder as a parent bucket + per-child buckets.

    `child_extractor`, if supplied, is called as
    `child_extractor(child_path, parent_bucket_id)` and must return a Bucket.
    The default extractor produces placeholder text buckets to keep the
    extractor self-contained; the real daemon wires in per-suffix routing.
    """
    root = Path(root_path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    supported, opaque, unsupported, skipped_perm, max_depth = _scan(root)

    parent_id = new_bucket_id()
    manifest = _manifest_dict(
        root=root,
        supported=supported,
        opaque=opaque,
        unsupported=unsupported,
        skipped_perm=skipped_perm,
        max_depth=max_depth,
    )

    canonical = canonical_dumps(manifest)
    parent_hash = sha256_bytes(canonical)
    produced_at = _utcnow()

    parent = Bucket(
        schema_version="1",
        bucket_id=parent_id,
        hash=Hash(algorithm="sha256", value=parent_hash),
        provenance=Provenance(
            origin="folder",
            source_uri=str(root),
            derived_from=None,
            produced_at=produced_at,
        ),
        full_content=canonical.decode("utf-8"),
        metadata={
            "source_count": manifest["source_count"],
            "unsupported_count": manifest["unsupported_count"],
            "opaque_count": manifest["opaque_count"],
            "skipped_permission_denied": manifest["skipped_permission_denied"],
            "max_depth_observed": manifest["max_depth_observed"],
            "deterministic_ordering": manifest["deterministic_ordering"],
        },
    )

    # Children
    def _default_child(path: Path, parent_bid: str) -> Bucket:
        text = path.read_text(encoding="utf-8", errors="replace")
        return build_bucket(
            origin="text",
            full_content=text,
            source_uri=str(path),
            derived_from=parent_bid,
        )

    extractor = child_extractor or _default_child
    children: list[Bucket] = []
    for p in supported:
        children.append(extractor(p, parent_id))

    return FolderExtractionResult(parent=parent, children=children, manifest=manifest)
