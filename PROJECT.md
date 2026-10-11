# OneShot project charter

## Purpose

OneShot helps a single operator turn a written objective and selected source files into a traceable, reviewable result. It preserves original sources, records which versions and capabilities were used, keeps incomplete work inspectable, and changes a target only after explicit approval and readback verification.

The System owns source scope, execution, evidence, policy, and completion. Agent Chat is optional and does not control the System workflow.

This charter describes the intended integrated product. It does not claim that every capability or release gate currently passes.

## Desired outcomes

1. **Controlled input:** the user chooses the objective, source scope, and saved source versions used by a run.
2. **Traceable results:** each result identifies its objective, sources, versions, coverage, result type, and limitations.
3. **Truthful status:** completed, partial, failed, rejected, interrupted, and unavailable outcomes remain distinct.
4. **Safe changes:** drafting, review, and Apply remain separate; no target changes before approval and verified readback.
5. **Recoverable work:** conversations, sources, drafts, jobs, events, artifacts, and Apply records survive supported restart and recovery scenarios.

## Success conditions

OneShot succeeds for an approved release scope when:

- System source preparation works without an Agent or model.
- A run uses the exact persisted objective and selected source versions accepted at admission.
- Source intake, revision, inspection, and scope removal preserve original identity and bytes.
- Progress and terminal status come from persisted execution events, not timers or simulated activity.
- Results preserve source provenance and never present an evidence packet, unfetched reference, or unsupported input as completed semantic work.
- Invalid requests, empty results, stale versions, provider failures, reconnects, and retries produce defined behavior without duplicate work or false success.
- Apply verifies authority, target, and baseline before writing, then records readback evidence or an explicit failure.
- The supported browser layouts preserve work and remain usable with keyboard navigation, visible focus, accessible status, and reduced motion.
- Existing browser and bearer-token clients retain their protected contract behavior.
- Semantic claims are demonstrated with an approved live provider and labeled source-grounded evaluation.
- Release claims include clean locked installation, authenticated browser-to-service journeys, restart and recovery evidence, compatibility checks, and actual deployment-runtime proof when deployment is in scope.

## Scope

- Separate System Chat, optional Agent Chat, Sources, and Editor/Review responsibilities.
- Temporary Process Display driven by actual accepted work and persisted events.
- Direct input, local import, existing-source inclusion, retained references, and removal from active scope without deleting the original.
- Immutable source bytes, source versions, working drafts, and source-specific metadata.
- Local scanning, reading, viewing, context preparation, coverage assessment, and explicit limitations.
- Deterministic evidence output without a model.
- Validated generation or summarization when an approved provider is configured.
- Persisted jobs, events, artifacts, review, explicit Apply, readback, and final-difference evidence.
- Optional advisory background evaluation that cannot block or alter foreground work.
- Exportable recovery of the former browser-only workspace without fabricating server history.

## Non-goals

- Agent, model, tool, or UI ownership of System policy, source mutation, or Apply.
- Simulated progress, citations, source coverage, model activity, or completion.
- Automatic source deletion, generated-content application, or model-directed tool execution.
- Automatic web retrieval, image understanding, OCR, PDF extraction, or semantic claims without a connected and verified capability.
- Direct public or multi-tenant operation under the current single-operator design.
- Implicit fallback between model providers.
- Conversion of browser-only history into server jobs, events, artifacts, or model results.
- Treating every result as `output.json` without an approved consumer and contract.
- Repository restructuring, framework adoption, or new integrations without a verified need and explicit approval.

## Technical and operational constraints

- The integrated candidate targets Python 3.11 with its reviewed `uv` lock and Node.js 22 or later.
- The browser frontend and FastAPI service are one compatibility unit.
- Request bodies are closed contracts. Invalid identifiers, empty required values, unknown fields, stale source versions, and unsupported actions are rejected.
- The service is authoritative for new integrated conversations, sources, drafts, jobs, events, artifacts, and Apply records.
- Jobs use persisted System objectives and selected immutable source versions. Message text does not automatically become a source.
- Evidence mode remains available without provider credentials.
- Model execution requires explicit server-side provider, model, endpoint, credential, and data-transfer approval.
- Provider errors are explicit; no provider fallback is implicit.
- The current deployment design is one operator, one service worker, local binding by default, and persistent local data.
- Stored references remain unfetched until an approved retrieval path records acquired content and provenance.
- Source checks, unit tests, HTTP integration, browser journeys, live-provider evaluation, and deployment evidence prove different things and remain separately reported.

## Security, reliability, and recovery expectations

### Security

- Credentials remain server-side and are not returned to the browser, stored in repository files, or recorded in events and logs.
- Remote provider traffic uses an approved secure endpoint; local unencrypted provider traffic is restricted to an explicit loopback endpoint.
- Sending selected sources to a third-party provider requires an approved data-processing policy.
- Sources, objectives, history, and model output are untrusted data and cannot grant authority or become executable markup.
- Browser-cookie authentication, request-forgery protection, and explicit bearer-token authentication remain distinct.
- Unknown provider output, redirects, unsupported tool calls, stale baselines, and unauthorized writes fail closed.
- Redaction is not encryption; encryption-at-rest and external secret-storage requirements require a deployment decision.

### Reliability and recovery

- Objective identity, source hashes and versions, event order, result type, and Apply outcome remain traceable.
- Supported writes and schema upgrades are atomic at their declared boundary and retry without reporting false success.
- Admission and retry behavior prevents duplicate work where repeated requests are possible.
- Pause, stop, cancel, and reconnect states are shown only after service acknowledgement.
- Optional providers, telemetry, Agent Chat, and background evaluation cannot corrupt committed foreground state.
- Originals remain recoverable while drafts, revisions, and applied outputs keep separate identities.
- Interrupted, partial, failed, and stopped work retains completed evidence and limitations.
- Restart and reconnect restore persisted state without rerunning a model or inventing events.
- Backup and restore verify referenced source digests and reject malformed or incomplete recovery data.
- Import into an active repository requires an identified baseline, rollback material, a changed-file inventory, and verification of the resulting target.

## Decisions requiring human input

| Blocks | Decision required |
| --- | --- |
| Implementation | Whether message-only processing is allowed without a selected source. |
| Implementation | Reference-retrieval authority, permitted domains, freshness rules, and whether retrieved content becomes a retained source. |
| Implementation | Supported image, PDF, OCR, and other modalities, including size and privacy limits. |
| Implementation | Create, Rewrite, overwrite, conflict, destination, and Apply semantics. |
| Implementation | Export-only preservation versus a source-only legacy-workspace importer. |
| Semantic validation | Approved System and Agent providers, models, credentials, data-transfer policy, cost limits, and fallback policy. |
| Semantic validation | Labeled evaluation fixtures, expected grounding, quality thresholds, and acceptable failures. |
| Output compatibility | The `output.json` consumer, schema, version, destination, and retention policy. |
| Deployment | Supported host, Docker requirement, networking, TLS, authentication, backups, retention, monitoring, and recovery objectives. |
| Deployment | Whether multi-user operation is required; identity, authorization, isolation, and concurrency are not defined. |
| Operations | Background-evaluation enablement, fixtures, scheduling, retries, privacy, retention, and review ownership. |
| Operations | Telemetry destination, permitted metadata, retention, access, and deletion policy. |
| Promotion | Authoritative target baseline, required acceptance journeys, final candidate, and rollback point. |

## Source basis

This charter consolidates supported intent from [Architecture.md](Architecture.md), [the UI acceptance map](ui/REQUIREMENTS.md), [the browser-workspace boundary](ui/README.md), [the integration plan](INTEGRATION-PLAN-2026-10-10.md), and the consolidated candidate's product, compatibility, model-integration, context-preparation, import, and acceptance documents.

Where those sources describe different implementation states, this charter records the intended outcome and leaves unresolved choices explicit rather than treating candidate behavior as current production capability.
