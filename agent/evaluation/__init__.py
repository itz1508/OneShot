"""Completion evaluation subsystem.

The CompletionEvaluator grades a finished workflow run against
independent oracles. It is CALLED BY the agent after a Run finishes;
it does not run inside the deterministic Research / Plan / Build
code paths and it never mutates committed stage records.

Golden samples come from ``agent.contracts.oracles`` — never from
the candidate's own output. Reference-guided evaluation is used when
the oracle supplies a reference answer; otherwise the Judge grades
in single mode against the rubric alone.
"""

from agent.evaluation.completion import (
    CompletionEvaluator,
    CompletionReceipt,
    CompletionReceiptError,
)

__all__ = [
    "CompletionEvaluator",
    "CompletionReceipt",
    "CompletionReceiptError",
]
