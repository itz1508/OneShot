"""Recovery and progress tests — REC01-REC09."""

from agent.runtime.recovery import (
    BoundedRecovery,
    ErrorClass,
    RecoveryDecision,
    RetryPolicy,
)


class TestBoundedRecovery:
    def test_transient_error_retries(self):
        """REC01: Transient errors are retried."""
        recovery = BoundedRecovery(RetryPolicy(max_retries=3))
        decision = recovery.retry_disposition("ctx-1", TimeoutError("connection timeout"))
        assert decision == RecoveryDecision.RETRY

    def test_permanent_error_blocks(self):
        """REC02: Permanent errors block."""
        recovery = BoundedRecovery()
        decision = recovery.retry_disposition("ctx-1", PermissionError("unauthorized"))
        assert decision == RecoveryDecision.BLOCK

    def test_max_retries_exhausted(self):
        """REC03: Max retries exhausted blocks."""
        recovery = BoundedRecovery(RetryPolicy(max_retries=2))
        recovery.retry_disposition("ctx-1", TimeoutError("timeout"))
        recovery.retry_disposition("ctx-1", TimeoutError("timeout"))
        decision = recovery.retry_disposition("ctx-1", TimeoutError("timeout"))
        assert decision == RecoveryDecision.BLOCK

    def test_no_progress_same_error_blocks(self):
        """REC04: Same error repeated blocks (no progress)."""
        recovery = BoundedRecovery(RetryPolicy(max_retries=5))
        recovery.retry_disposition("ctx-1", ValueError("same"))
        recovery.retry_disposition("ctx-1", ValueError("same"))
        decision = recovery.retry_disposition("ctx-1", ValueError("same"))
        assert decision == RecoveryDecision.BLOCK

    def test_different_errors_allow_retry(self):
        """REC05: Different errors don't trigger no-progress block."""
        recovery = BoundedRecovery(RetryPolicy(max_retries=5))
        recovery.retry_disposition("ctx-1", TimeoutError("timeout 1"))
        recovery.retry_disposition("ctx-1", TimeoutError("timeout 2"))
        decision = recovery.retry_disposition("ctx-1", TimeoutError("timeout 3"))
        assert decision == RecoveryDecision.RETRY

    def test_uncertain_error_reconciles(self):
        """REC06: Uncertain errors trigger reconciliation."""
        recovery = BoundedRecovery()
        classification = recovery.classify(ValueError("unknown issue"), "ctx-1")
        assert classification.error_class == ErrorClass.UNCERTAIN
        assert classification.decision == RecoveryDecision.RECONCILE

    def test_reconcile_returns_result(self):
        """REC07: Reconciliation returns a result."""
        recovery = BoundedRecovery()
        result = recovery.reconcile("op-001", "some data")
        assert "reconciled" in result

    def test_reset_clears_state(self):
        """REC08: Reset clears retry state."""
        recovery = BoundedRecovery(RetryPolicy(max_retries=2))
        recovery.retry_disposition("ctx-1", TimeoutError("timeout"))
        recovery.reset("ctx-1")
        # After reset, retry count should be 0 again
        decision = recovery.retry_disposition("ctx-1", TimeoutError("timeout"))
        assert decision == RecoveryDecision.RETRY

    def test_context_independent_retry_counts(self):
        """REC09: Different contexts have independent retry counts."""
        recovery = BoundedRecovery(RetryPolicy(max_retries=2))
        recovery.retry_disposition("ctx-1", TimeoutError("timeout"))
        recovery.retry_disposition("ctx-2", TimeoutError("timeout"))
        recovery.retry_disposition("ctx-1", TimeoutError("timeout"))
        # ctx-2 should still have retries left
        decision = recovery.retry_disposition("ctx-2", TimeoutError("timeout"))
        assert decision == RecoveryDecision.RETRY
