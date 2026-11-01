# Prompt Authoring

OneShot's **development** capability for generating, evaluating, revising, and versioning reusable prompt definitions.

> Prompt Authoring is NOT a workflow stage. Nothing in this package mutates `TaskManager` rows, calls a provider adapter, or participates in Research / Plan / Build at runtime. It produces versioned candidate prompts and an immutable `EvaluationReceipt`; the authorized owner activates a revision via `PromptStore.activate` once evaluation passes.

## Architecture

```
PromptSpec → PromptAuthor → PromptDefinition (revision=1, UNEVALUATED)
                                 │
                                 ▼
                         PromptEvaluator (9 axes × fixtures)
                                 │
                                 ▼
                         EvaluationReceipt (EVALUATED | BLOCKED)
                                 │
                                 ▼ (authorized owner only)
                           PromptStore.activate(...)
                                 │
                                 ▼
                       PromptDefinition (status = ACTIVE)
```

## Status machine

```
UNEVALUATED  → EVALUATED | BLOCKED
BLOCKED      → EVALUATED
EVALUATED    → ACTIVE | SUPERSEDED | ARCHIVED
ACTIVE       → SUPERSEDED | ARCHIVED
SUPERSEDED   → (terminal)
ARCHIVED     → (terminal)
```

A revision **never** jumps directly from `UNEVALUATED` to `ACTIVE`. Activation is `PromptStore.activate(prompt_id, revision, actor)`; it supersedes the current `ACTIVE` revision (if any) and appends an `AuditEntry` — history is never rewritten.

## Required-fields map

Every `PromptDefinition` carries the exact fields the spec lists:

- `prompt_id`
- `revision` (≥ 1)
- `content_digest` (sha-256 of the canonical serialisation of stable fields)
- `stage` (`research` / `plan` / `build` / `discovery` / `handoff` / `provider_adapter`)
- `owner` (kind + identifier; four boundaries from the spec)
- `runtime_inputs` (minimal, non-overlapping)
- `stable_instructions`
- `required_capabilities` — reuses `agent.providers.types.ProviderCapabilities` so prompts cannot ask for a capability the registry does not know how to express
- `output_contract` (non-empty JSON Schema)
- `evaluation_rules`
- `recovery_behavior`
- `fixture_refs`
- `evaluation_receipt_ref`
- `supersedes`
- `status`

## Ownership boundaries

| Owner | Owns |
| --- | --- |
| **Prompt Authoring** | generation, template refinement, examples, prompt fixtures, evaluation definitions, candidate revisions |
| **Main Agent / Handoff Evaluator** | stage assignment, prompt revision selection, workflow state, handoff validation, routing |
| **Builder Discovery** | read-only repository inspection, request-flow tracing, implementation pattern discovery, code-quality findings, population of the accepted Discovery artifact |
| **Provider Adapter** | model selection, API translation, capability negotiation, structured-output implementation, streaming, caching, batching, provider-specific errors |
| **Planner** | architecture, implementation strategy, file actions, dependencies, implementation Plan |

## Invariants

1. No new mandatory workflow stages.
2. No per-task regeneration of accepted role prompts.
3. No provider-specific implementation inside reusable prompt definitions — the `_tool_selection_accuracy` evaluator axis fails any `stable_instructions` that mention `openai`, `anthropic`, `claude`, `gpt-`, or a vendor endpoint.
4. No caching or runtime handoff execution inside Prompt Authoring.
5. No duplicate schema or persistence system without inspecting existing ownership — this package REUSES `ProviderCapabilities` and the G03 `expected_rejection` pattern.
6. No generated prompt becomes authoritative without validation and authorized activation.
7. No fabricated tests, receipts, approvals, or execution outcomes.
8. No hidden reasoning or scratchpad persistence.

## Usage

```python
from agent.prompt_authoring import (
    PromptAuthor, PromptSpec, PromptStore, PromptEvaluator,
    PromptFixtureRegistry, OwnerRef, RuntimeInputSpec,
)
from agent.prompt_authoring.types import Stage
from agent.providers.types import ProviderCapabilities

author = PromptAuthor()
spec = PromptSpec(
    prompt_id="research-counter",
    stage=Stage.RESEARCH,
    owner=OwnerRef(kind="prompt_authoring", identifier="core-team"),
    stage_specification="Research stage for the context_counter demo.",
    task_class="summarise",
    runtime_inputs=[RuntimeInputSpec(name="objective", meaning="user task text")],
    output_contract={"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
    required_capabilities=ProviderCapabilities(structured_outputs=True),
    stable_instructions=[
        "Reason about the user objective and emit a status.",
        "If the objective is unknown or blocked, say so explicitly.",
    ],
    evaluation_rules=["Status must be one of ok, blocked, unknown."],
    recovery_behavior="Preserve prior evidence refs across resumption.",
)

candidate = author.author_candidate(spec)
receipt = PromptEvaluator().evaluate(candidate, PromptFixtureRegistry.default().all())
candidate = author.apply_receipt(candidate, receipt)   # UNEVALUATED → EVALUATED / BLOCKED

store = PromptStore()
store.register(candidate, actor="core-team")
if candidate.status == candidate.status.EVALUATED:
    store.activate("research-counter", 1, actor="owner-handle")
```

## Where this plugs into OneShot

`OneShotController.prompt_store` is a lazy-constructed `PromptStore` so future workflow callers can look up an ACTIVE revision by `(prompt_id, stage)` without inventing a second seam. Today, zero workflow stages reach into the store — scenarios S1–S5 and the G01–G11 gap closures remain deterministic and are unaffected by this capability.
