"""A1 — bucket immutability enforcement.

Frozen fields do not mutate once a bucket has reached STORED. Content changes
require a brand-new bucket_id (and therefore a new hash).

Mutable fields: state, integrity_status, lifecycle.*_at timestamps,
lifecycle.release_count, optional_summary.
"""

from __future__ import annotations

from typing import Any


FROZEN_FIELDS: tuple[str, ...] = (
    "schema_version",
    "bucket_id",
    "hash",
    "provenance",
    "full_content",
    "metadata",
)

MUTABLE_LIFECYCLE_KEYS: tuple[str, ...] = (
    "received_at",
    "staged_at",
    "stored_at",
    "activated_at",
    "replayed_at",
    "released_at",
    "retired_at",
    "release_count",
)


class BucketImmutabilityViolation(Exception):
    """Raised when a frozen field is mutated after STORED."""


def _after_stored(state: str) -> bool:
    return state in {"STORED", "ACTIVATED", "REPLAYED", "RELEASED", "RETIRED"}


def check_mutation(before: dict[str, Any], after: dict[str, Any]) -> None:
    """Reject mutations of frozen fields once the bucket has reached STORED.

    `before` and `after` are canonical dict projections of the bucket (as from
    Bucket.model_dump(mode="json")).
    """
    # If the pre-image hasn't reached STORED yet, any field may change — the
    # bucket is still in the ingestion window.
    if not _after_stored(before.get("state", "RECEIVED")):
        return

    for field in FROZEN_FIELDS:
        if before.get(field) != after.get(field):
            raise BucketImmutabilityViolation(
                f"Frozen field '{field}' changed after STORED. "
                "Content changes require a NEW bucket_id (A1)."
            )
