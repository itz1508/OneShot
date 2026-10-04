"""OneShot entrypoint — Phase 2 placeholder.

The real OneShot shell is empty on this build. This file exists so
`uv run oneshot --version` resolves and the workspace is discoverable.
The next OneShot build task will fill it in.
"""

from __future__ import annotations


def main() -> int:
    print("oneshot 0.0.0 (shell placeholder)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
