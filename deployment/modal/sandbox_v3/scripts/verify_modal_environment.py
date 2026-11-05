"""Read-only Modal readiness check. Never print token values or create resources."""

from __future__ import annotations

import importlib.util
import os
import sys


def main() -> int:
    if sys.version_info < (3, 11) or sys.version_info >= (3, 14):
        print("BLOCKED: required Python version is 3.11–3.13")
        return 2
    print(f"Python {sys.version.split()[0]}")
    installed = bool(importlib.util.find_spec("modal"))
    creds = bool(os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET"))
    image = bool(os.getenv("ONESHOT_MODAL_IMAGE_ID"))
    print(f"Modal SDK: {'present' if installed else 'missing'}")
    print(f"Workspace credentials: {'present' if creds else 'missing'}")
    print(f"Prebuilt image ID: {'present' if image else 'missing'}")
    print("No Modal operations attempted; SDK credentials and image ID need an authorized live probe")
    return 0 if installed and creds and image else 2


if __name__ == "__main__":
    raise SystemExit(main())
