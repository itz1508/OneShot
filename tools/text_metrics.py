#!/usr/bin/env python3
"""
OneShot Active Tool: Text Metrics

Deterministic local text counting — no model/provider call.
Counts Unicode code points, UTF-8 bytes, and words (whitespace-separated).
"""

import sys


def count_text(text: str) -> dict:
    """Count characters (Unicode code points), UTF-8 bytes, and words.

    Args:
        text: Input string (must be valid Python str).

    Returns:
        dict with keys: characters, bytes, words
    """
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")

    characters = len(text)
    utf8_bytes = len(text.encode("utf-8"))
    words = len(text.split()) if text else 0

    return {
        "characters": characters,
        "bytes": utf8_bytes,
        "words": words,
    }


def count_file(filepath: str) -> dict:
    """Count text metrics for a file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return count_text(f.read())


def main():
    if len(sys.argv) < 2:
        print("Usage: python text_metrics.py <text>", file=sys.stderr)
        print("       python text_metrics.py --file <path>", file=sys.stderr)
        return 1

    if sys.argv[1] == "--file" and len(sys.argv) > 2:
        result = count_file(sys.argv[2])
    else:
        result = count_text(sys.argv[1])

    for k, v in result.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
