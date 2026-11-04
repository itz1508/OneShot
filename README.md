# OneShot — Clean Rebuild

A host-owned workflow harness for Research, Audit Discovery, Planning, Fixture Validation, Build, and Build Validation stages with explicit host gates between them.

## Quick start

```sh
# Install dependencies
uv sync --locked --extra meta

# Run environment check
uv run --no-sync python scripts/doctor.py

# Run tests
uv run --no-sync pytest -q

# CLI
uv run --no-sync python -m agent doctor
uv run --no-sync python -m agent run task-001
uv run --no-sync python -m agent status task-001
uv run --no-sync python -m agent resume task-001
uv run --no-sync python -m agent verify task-001
```

## Architecture

Six stages with host-owned gates:

```
Research → Audit Discovery → Planning → [host freeze] → Fixture Validation → [host lock + admission] → Build → Build Validation
```

### Key design decisions

- **Provider configuration**: Meta Muse Spark is the default profile; its model can be overridden with `META_MODEL_ID`. Other OpenAI-compatible profiles are supported by the capability probe adapter. Echo is a test double. SDK-specific Claude/Codex adapters are not implemented.
- **RFC 8785/JCS canonical serialization** with SHA-256 for all digest-bearing artifacts
- **Content-addressed artifact store** with immutable revision tracking
- **CAS-based checkpoint store** for interruption recovery
- **Default-deny authorization** with path containment and symlink escape prevention
- **Bounded recovery** with no-progress detection
- **Two CodeIntent origins**: `existing_implementation_gap` and `new_feature`

### File structure

```
agent/
  contracts/       # Pydantic v2 typed contracts (no runtime imports)
    common.py      # Shared primitives
    host.py        # Receipt types (host-only)
    research.py    # Research stage
    audit_discovery.py  # Audit Discovery stage
    planning.py    # Planning stage with BuildAction types
    scanner.py     # Scanner capability shapes
    fixture_validation.py
    build.py
    build_validation.py
    validation/    # Pure semantic validators
  runtime/         # Host kernel
    canonical_serialization.py  # RFC 8785/JCS + SHA-256
    artifact_store.py    # Content-addressed storage
    receipt_store.py     # Host-only receipts
    event_store.py       # Append-only events
    checkpoint_store.py  # CAS checkpoints
    authorization.py     # Default-deny enforcement
    controller.py        # Single transition authority
    specification_freezer.py
    package_lock.py
    build_admission.py
    effect_executor.py
    recovery.py
    scanner_gateway.py
    providers/     # Provider adapters
      base.py      # Protocol and types
      echo.py      # Deterministic test double
      meta.py      # Meta Muse Spark
      registry.py  # Provider-neutral registry
  cli.py           # Thin host entrypoint
tests/             # Contract, boundary, artifact, authorization, scanner, E2E tests
settings/config.yaml  # Runtime configuration
scripts/doctor.py     # Environment diagnostics
```

Run the checks in `AGENTS.md` against the current checkout for verification results.
The historical connected MCP claim is scoped in `audit/e2e-verification-correction-2026-11-04.md`.
