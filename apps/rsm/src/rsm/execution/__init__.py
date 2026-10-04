"""Execution state — separate from bucket lifecycle and bucket content (spec §10).

Rules:
    - Bucket content remains authoritative.
    - Execution state is mutable.
    - Execution state references `bucket_id`.
    - Execution state MUST NOT rewrite `full_content`.
    - Execution completion does NOT automatically close the bucket.
    - RSM does not execute the work.
"""

from .model import ExecutionState, ExecutionStatus, ExecutionTask, TaskStatus

__all__ = ["ExecutionState", "ExecutionStatus", "ExecutionTask", "TaskStatus"]
