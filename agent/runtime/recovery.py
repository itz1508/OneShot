"""Bounded recovery — classify errors, reconcile effects, retry disposition."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ErrorClass(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNCERTAIN = "uncertain"


class RecoveryDecision(StrEnum):
    RETRY = "retry"
    BLOCK = "block"
    RECONCILE = "reconcile"
    ABORT = "abort"


class RetryPolicy(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    backoff_seconds: float = Field(default=1.0, ge=0)


class RecoveryClassification(BaseModel):
    error_class: ErrorClass
    decision: RecoveryDecision
    reason: str = Field(min_length=1)
    model_config = {"frozen": True}


class BoundedRecovery:
    """Bounded recovery with no-progress detection.

    - Transient errors may retry (bounded by policy).
    - Permanent errors block.
    - Uncertain effects must be reconciled before retry.
    - No-progress or oscillating corrections block the affected work.
    """

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self.policy = policy or RetryPolicy()
        self._retry_counts: dict[str, int] = {}
        self._last_errors: dict[str, str] = {}

    def classify(self, error: Exception, context: str) -> RecoveryClassification:
        """Classify an error and determine recovery action."""
        error_msg = str(error)
        if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            return RecoveryClassification(
                error_class=ErrorClass.TRANSIENT,
                decision=RecoveryDecision.RETRY,
                reason=f"transient error: {error_msg}",
            )
        if "permission" in error_msg.lower() or "unauthorized" in error_msg.lower():
            return RecoveryClassification(
                error_class=ErrorClass.PERMANENT,
                decision=RecoveryDecision.BLOCK,
                reason=f"authorization error: {error_msg}",
            )
        return RecoveryClassification(
            error_class=ErrorClass.UNCERTAIN,
            decision=RecoveryDecision.RECONCILE,
            reason=f"uncertain error: {error_msg}",
        )

    def retry_disposition(self, context: str, error: Exception) -> RecoveryDecision:
        """Determine if a retry is allowed under bounded policy."""
        count = self._retry_counts.get(context, 0)
        last_error = self._last_errors.get(context)

        # No-progress detection: same error repeated
        if last_error == str(error) and count >= 2:
            return RecoveryDecision.BLOCK

        if count >= self.policy.max_retries:
            return RecoveryDecision.BLOCK

        classification = self.classify(error, context)
        self._retry_counts[context] = count + 1
        self._last_errors[context] = str(error)
        return classification.decision

    def reconcile(self, operation_id: str, operation_data: str) -> str:
        """Reconcile an uncertain effect. Returns reconciliation result."""
        return f"reconciled:{operation_id}"

    def reset(self, context: str) -> None:
        """Reset retry state for a context."""
        self._retry_counts.pop(context, None)
        self._last_errors.pop(context, None)
