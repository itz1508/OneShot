# V8 Gap Report

This document tracks gaps identified during the v8→v9 clean rebuild process.

## Closed gaps
- All 6 status enums added to common.py (DiagnosticStatus, ProposalState, OperationState, SpecificationState, CoverageStatus, CriteriaStatus)
- Enhanced EvidenceRef with observation, receipt_ref, artifact_ref, EVD- pattern
- Enhanced StepResult with blocker, recovery_ref, resume_point
- 6 new contract files: observability, guardrails, interrupts, repository, provider, config
- Full Checkpoint model with artifact_refs, delegation_refs, operation refs
- Runtime infrastructure: streaming, guardrails, interrupts, context_projection
- Provider infrastructure: provider_config, provider_factory, provider_interface
- OpenAI-compatible adapter with chat, stream, structured_output, tool_roundtrip, vision, response
- api_fundamentals with 10 probes and run_probe CLI
- .agents config: agent.yaml, 6 role definitions, 2 provider configs, market practices
- 6 workflow YAML files for all stages
- Cross-stage validation: audit lineage, build specification, acyclicity
- InMemoryCheckpointStore and StaleCheckpointError for testing
- AppendOnlyEventStore with hash-chained events
- PathAuthorizer and RolePolicy for role-based authorization

## Remaining
- Live provider integration tests (require API keys)
- Full E2E pipeline execution with real model calls
- Claude adapter implementation (placeholder)
- OpenAI Agents SDK adapter implementation (placeholder)
