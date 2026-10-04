"""Phase 2 — Runtime directory boundaries.

Two filesystem roots, both plain POSIX directories:

* ``attachment/`` — incoming external source material, byte-identical to what
  the caller handed us. NOT RSM state.
* ``store/`` — RSM-managed persistent state (one JSON file per Bucket under
  the existing :class:`rsm.daemon.store.FsStore`).

The default locations are ``./attachment`` and ``./store`` relative to the
process working directory. :class:`rsm.config.schema.Persistence.root`
remains the authoritative config key for the store; this module only
exposes a plain init helper so a caller can prepare both directories
without pulling in the full configuration machinery.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

DEFAULT_ATTACHMENT_DIR: str = "./attachment"
DEFAULT_STORE_DIR: str = "./store"


class RuntimeDirError(Exception):
    """Raised when a runtime directory cannot be initialized."""


def _ensure_one(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except FileExistsError as e:
        # path exists but is not a directory
        raise RuntimeDirError(
            f"Runtime path exists but is not a directory: {path}"
        ) from e
    except PermissionError as e:
        raise RuntimeDirError(
            f"Permission denied creating runtime directory: {path} ({e})"
        ) from e
    except OSError as e:
        if e.errno == errno.ENOTDIR:
            raise RuntimeDirError(
                f"A parent path component is not a directory: {path}"
            ) from e
        raise RuntimeDirError(f"Could not create runtime directory {path}: {e}") from e
    if not path.is_dir():
        raise RuntimeDirError(f"Runtime path is not a directory: {path}")
    # Verify writeable — a read-only mount is a fatal, explicit failure.
    if not os.access(path, os.W_OK):
        raise RuntimeDirError(f"Runtime directory is not writable: {path}")
    return path


def ensure_runtime_dirs(
    *,
    attachment_dir: str | os.PathLike[str] = DEFAULT_ATTACHMENT_DIR,
    store_dir: str | os.PathLike[str] = DEFAULT_STORE_DIR,
) -> tuple[Path, Path]:
    """Idempotently create both runtime directories.

    Returns the resolved ``(attachment, store)`` pair.

    Explicit failure modes:

    * `RuntimeDirError` on permission errors, read-only mounts, or a path
      component that is not a directory.
    * Never silently treats a stray file as a runtime directory.
    """
    a = Path(attachment_dir).expanduser()
    s = Path(store_dir).expanduser()
    if a.resolve() == s.resolve():
        raise RuntimeDirError(
            f"attachment_dir and store_dir must be distinct: both resolve to {a}"
        )
    return _ensure_one(a), _ensure_one(s)
