"""Programmatic canonical JSON Schema for the V1 bucket.

A2: `schema_version` is `{"const": "1"}`. Reads of any other value raise
`UNSUPPORTED_SCHEMA_VERSION` (see rsm.api.errors).
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1"


def canonical_schema() -> dict[str, Any]:
    """Return the V1 canonical JSON Schema (Draft-07 subset)."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "RSM V1 Bucket",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "bucket_id",
            "hash",
            "provenance",
            "full_content",
            "state",
        ],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "bucket_id": {"type": "string", "minLength": 1},
            "hash": {
                "type": "object",
                "additionalProperties": False,
                "required": ["algorithm", "value"],
                "properties": {
                    "algorithm": {"const": "sha256"},
                    "value": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                },
            },
            "provenance": {
                "type": "object",
                "additionalProperties": False,
                "required": ["origin", "produced_at"],
                "properties": {
                    "origin": {
                        "enum": [
                            "markdown",
                            "text",
                            "pasted",
                            "stdin",
                            "chatgpt_export",
                            "pdf",
                            "folder",
                            "opaque",
                        ]
                    },
                    "source_uri": {"type": ["string", "null"]},
                    "derived_from": {"type": ["string", "null"]},
                    "produced_at": {"type": "string", "format": "date-time"},
                },
            },
            "full_content": {"type": "string"},
            "metadata": {"type": "object"},
            "integrity_status": {"enum": ["unverified", "verified", "corrupt"]},
            "state": {
                "enum": [
                    "RECEIVED",
                    "STAGED",
                    "STORED",
                    "ACTIVATED",
                    "REPLAYED",
                    "RELEASED",
                    "RETIRED",
                ]
            },
            "lifecycle": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "received_at":  {"type": ["string", "null"], "format": "date-time"},
                    "staged_at":    {"type": ["string", "null"], "format": "date-time"},
                    "stored_at":    {"type": ["string", "null"], "format": "date-time"},
                    "activated_at": {"type": ["string", "null"], "format": "date-time"},
                    "replayed_at":  {"type": ["string", "null"], "format": "date-time"},
                    "released_at":  {"type": ["string", "null"], "format": "date-time"},
                    "retired_at":   {"type": ["string", "null"], "format": "date-time"},
                    "release_count": {"type": "integer", "minimum": 0},
                },
            },
            "optional_summary": {"type": ["string", "null"]},
        },
    }
