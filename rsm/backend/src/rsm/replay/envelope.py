"""Replay envelope (spec §14).

Stable replay representation. The canonical bucket schema remains authoritative;
this envelope wraps a projection with classification + replayability so the
replay transport has one single shape.
"""

from __future__ import annotations

from typing import Any

from ..bucket.model import Bucket
from ..classification.model import WorkClassification
from .readiness import Replayability, derive_replayability


def build_replay_envelope(
    bucket: Bucket,
    *,
    classification: WorkClassification | str = WorkClassification.STORE,
) -> dict[str, Any]:
    classification = (
        WorkClassification(classification)
        if not isinstance(classification, WorkClassification)
        else classification
    )
    replayability = derive_replayability(bucket.state, classification)
    projected = bucket.model_dump(mode="json")
    return {
        "source": "rsm",
        "bucket_id": bucket.bucket_id,
        "schema_version": bucket.schema_version,
        "work_classification": classification.value,
        "replayability": replayability.value,
        "content": {
            "full_content": projected["full_content"],
            "metadata": projected["metadata"],
            "state": projected["state"],
        },
        "provenance": projected["provenance"],
        "integrity": {
            "algorithm": projected["hash"]["algorithm"],
            "value": projected["hash"]["value"],
        },
    }
