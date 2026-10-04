"""Loading boundary — stages external source material and lines up files for the Reader.

Deliberately NOT a durable-messaging queue, broker, workflow engine, or
competing-consumer system. See ADR 0017 non-goals and the Phase-1A audit.
"""
from .runtime_dirs import (
    DEFAULT_ATTACHMENT_DIR,
    DEFAULT_STORE_DIR,
    RuntimeDirError,
    ensure_runtime_dirs,
)
from .attachment import (
    StagedAttachment,
    stage_attachment_bytes,
    stage_attachment_path,
)
from .archive import (
    ArchiveManifestEntry,
    ArchiveManifest,
    ArchiveSafetyError,
    enumerate_zip,
)

__all__ = [
    "DEFAULT_ATTACHMENT_DIR",
    "DEFAULT_STORE_DIR",
    "RuntimeDirError",
    "ensure_runtime_dirs",
    "StagedAttachment",
    "stage_attachment_bytes",
    "stage_attachment_path",
    "ArchiveManifestEntry",
    "ArchiveManifest",
    "ArchiveSafetyError",
    "enumerate_zip",
]
