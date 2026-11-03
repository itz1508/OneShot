# OneShot Clean Rebuild Plan

**Date:** 2026-11-03
**Status:** Implementation complete, verification in progress

## Architecture
- Python >=3.11, Pydantic v2, RFC 8785/JCS, SHA-256 digests
- Provider-neutral host with OpenAI-compatible as first adapter
- Six stage records: Research, Audit Discovery, Planning, Build, Build Validation, Fixture Validation
- Immutable artifact handoffs via content-addressed storage
- Host-owned security: default-deny, path authorization, CAS checkpoints

## Phases completed
1. Foundation types (status enums, enhanced EvidenceRef/StepResult)
2. Diagnostic structures (audit_discovery, planning enrichment)
3. Host operation records (OperationRecord, Checkpoint)
4. Contract files (observability, guardrails, interrupts, repository, provider, config)
5. Runtime + provider adapters
6. api_fundamentals probes
7. .agents config
8. Workflow YAML
9. Tests (adapted to clean rebuild conventions)
10. Other (docs, .env.example, scripts, V8_GAP_REPORT)
