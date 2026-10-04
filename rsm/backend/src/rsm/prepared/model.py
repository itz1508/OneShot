"""`PreparedRepresentation` — typed assembler.

Pure composition: given a Bucket, an already-built Snapshot, a
ReadResult, and a classification/replay envelope, return the typed
Prepared Representation. No I/O, no mutation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..assessment.model import SourceAssessment
from ..bucket.model import Bucket
from ..reader.model import ReadResult
from ..snapshot.model import Snapshot


class PreparedRepresentation(BaseModel):
    """Named envelope at the Processor → Replay boundary.

    `schema_version` is independent of the Bucket's; this is a stable
    boundary record. All referenced DTOs retain their own schema_version
    fields so they can evolve independently.

    Field semantics:

      * `bucket_id` / `integrity`        — identity of the authoritative
                                            Source (same as the inner
                                            Bucket's A1 hash).
      * `assessment`                      — SourceAssessment (why RSM is
                                            participating).
      * `coverage`                        — ReaderTrace from this
                                            observation pass (what was
                                            observed, what failed per
                                            File, trace completeness).
      * `snapshot`                        — bounded derived content.
      * `replay`                          — stable release envelope.

    Invariants:
      * Prepared != Source. Provenance in the envelope links back to the
        Source; the Prepared Representation never claims to BE the
        Source.
      * `coverage.bucket_id == bucket_id == snapshot.bucket_id ==
        replay["bucket_id"]`.
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    bucket_id: str = Field(..., min_length=1)
    integrity: dict[str, Any]

    assessment: SourceAssessment
    coverage: dict[str, Any]
    snapshot: dict[str, Any]
    replay: dict[str, Any]


def build_prepared_representation(
    *,
    bucket: Bucket,
    assessment: SourceAssessment,
    read_result: ReadResult,
    snapshot: Snapshot,
    replay_envelope: dict[str, Any],
) -> PreparedRepresentation:
    """Assemble a PreparedRepresentation. Pure, no I/O.

    All callers already have each ingredient. This function only enforces
    the typed boundary (and the trivial bucket_id consistency check that
    guarantees provenance is not accidentally crossed).
    """
    if assessment.bucket_id != bucket.bucket_id:
        raise ValueError(
            "assessment.bucket_id does not match bucket.bucket_id; "
            "a Prepared Representation would cross provenance boundaries."
        )
    if read_result.bucket_id != bucket.bucket_id:
        raise ValueError(
            "read_result.bucket_id does not match bucket.bucket_id."
        )
    if snapshot.bucket_id != bucket.bucket_id:
        raise ValueError(
            "snapshot.bucket_id does not match bucket.bucket_id."
        )
    if replay_envelope.get("bucket_id") != bucket.bucket_id:
        raise ValueError(
            "replay envelope bucket_id does not match bucket.bucket_id."
        )

    return PreparedRepresentation(
        bucket_id=bucket.bucket_id,
        integrity={
            "algorithm": bucket.hash.algorithm,
            "value": bucket.hash.value,
        },
        assessment=assessment,
        coverage=read_result.trace.model_dump(mode="json"),
        snapshot=snapshot.model_dump(mode="json"),
        replay=replay_envelope,
    )
