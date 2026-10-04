# ADR 0002 — Forbidden Dependencies

**Status:** Carried forward from spec §5.2.

RSM V1 does not install any AI/LLM/model-provider SDK or vector store client.
Enforcement: `backend/tools/check_forbidden_deps.py` and §12 E2E-10/E2E-12.
