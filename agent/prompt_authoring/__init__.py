"""OneShot Prompt Authoring — generate, evaluate, refine, version prompts.

Prompt Authoring is a DEVELOPMENT capability, not a workflow stage.
Nothing in this package mutates runtime state (`TaskManager`,
`OneShotController`, provider registry); it produces versioned
candidate prompts, immutable evaluation receipts, and a read-only
`PromptStore` that OneShot's existing workflow modules can look up
BY ID + REVISION once the authorized owner activates a revision.

Reused OneShot vocabulary (no duplicated schemas):

* `agent.providers.types.ProviderCapabilities` — the matrix a prompt
  declares as its required capabilities. Prompts do not pick
  providers; they declare the capabilities an adapter must advertise
  for the prompt to be usable.
* `agent.providers.types.ProviderConfig.credential_ref` style — any
  env-ref inside a prompt is a NAME, never a secret.
* `tools.fixtures.FixtureCase` and the G03 `expected_rejection`
  shape — the evaluator reuses that pattern via `PromptFixture`.

See `agent/prompt_authoring/README.md` and the "Prompt Authoring"
section in [AGENTS.md] for the full contract.
"""

from agent.prompt_authoring.author import (
    ImmutableRevisionError,
    PromptAuthor,
    StatusTransitionError,
)
from agent.prompt_authoring.evaluator import (
    CheckResult,
    EvaluationReceipt,
    PromptEvaluator,
)
from agent.prompt_authoring.fixtures import (
    PromptFixture,
    PromptFixtureKind,
    PromptFixtureRegistry,
)
from agent.prompt_authoring.store import (
    AuditEntry,
    PromptStore,
    PromptStoreError,
)
from agent.prompt_authoring.types import (
    OwnerRef,
    PromptDefinition,
    PromptSpec,
    PromptStatus,
    RuntimeInputSpec,
)

__all__ = [
    "AuditEntry",
    "CheckResult",
    "EvaluationReceipt",
    "ImmutableRevisionError",
    "OwnerRef",
    "PromptAuthor",
    "PromptDefinition",
    "PromptEvaluator",
    "PromptFixture",
    "PromptFixtureKind",
    "PromptFixtureRegistry",
    "PromptSpec",
    "PromptStatus",
    "PromptStore",
    "PromptStoreError",
    "RuntimeInputSpec",
    "StatusTransitionError",
]
