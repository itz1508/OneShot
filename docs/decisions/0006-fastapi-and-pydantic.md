# ADR 0006 — FastAPI + Pydantic for the Daemon HTTP Transport

**Status:** NEW. Binding.

The daemon exposes its HTTP transport with FastAPI (`fastapi[standard]`,
0.142.x) and models canonical payloads with Pydantic 2.13.x. Install:

```
python -m pip install "fastapi[standard]" pydantic
```

### Rationale

- FastAPI's typed-models story aligns with the canonical bucket model.
- Pydantic 2 enforces `additionalProperties: False` via `extra="forbid"`,
  which is how A2's unknown-key rejection is realised at load time.
