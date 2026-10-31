#!/usr/bin/env python3
"""
OneShot Context Counter CLI — demo build target.

Counts Unicode code points, UTF-8 bytes, and words in input text.
Built as part of the OneShot Workflow Harness E2E demo.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from text_metrics import count_text


def main():
    if len(sys.argv) < 2:
        print("Usage: context_counter.py <text>", file=sys.stderr)
        print("       context_counter.py --file <path>", file=sys.stderr)
        return 1

    if sys.argv[1] == "--file" and len(sys.argv) > 2:
        with open(sys.argv[2], encoding="utf-8") as f:
            text = f.read()
    elif sys.argv[1] == "--stdin":
        text = sys.stdin.read()
    else:
        text = sys.argv[1]

    result = count_text(text)
    for k, v in result.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
