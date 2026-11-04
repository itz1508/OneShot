# Modal Sandbox v3 — standalone source transfer

This folder transfers the **existing 25-file standalone v3 implementation** to the OneShot Builder. It is **not** the Modal ASGI app, not the health endpoint, and not an integrated or verified OneShot Build executor.

Source package: `standalone-v3.tar.xz.base64` (base64-encoded tar.xz)
Expected decoded SHA-256: `ff2a49c20c2e8d2113c826371d13a3ebd4d0e2881c9feedc9774e20cfa4201c4`
Contents: 25 files; the standalone `uv.lock` was not generated.

## Extract without replacing main's files

From repository root, in an execution-capable environment:

```sh
mkdir -p /tmp/oneshot-modal-v3
base64 -d deployment/modal/sandbox_v3_source/standalone-v3.tar.xz.base64 > /tmp/oneshot-modal-v3-source.tar.xz
sha256sum /tmp/oneshot-modal-v3-source.tar.xz
tar -tf /tmp/oneshot-modal-v3-source.tar.xz
tar -xJf /tmp/oneshot-modal-v3-source.tar.xz -C /tmp/oneshot-modal-v3
```

Before extraction inspect archive members. Confirm SHA-256 exactly matches the value above.

## Next Builder action

1. Audit the extracted standalone package against the accepted v3 plan; do not rebuild it.
2. Choose a nonconflicting package directory in OneShot. Preserve the root `uv.lock`, existing `modal_app.py`, `deployment/modal/app.py`, and FastAPI host.
3. Generate a **standalone-specific** `uv.lock` using its own `pyproject.toml`.
4. Run Python 3.11 and 3.12 tests, Ruff, mypy and dependency validation.
5. Run real Modal Sandbox GOOD/BAD E2E with admitted fixture changes, no network, evidence export, host digest verification and confirmed termination.
6. Only after standalone evidence, plan the separate host integration through existing Build Admission and receipt contracts.

Do **not** merge this transfer payload to main as the final implementation. Replace transfer artifact with the reviewed source tree on the implementation branch after tests pass.

Previously observed local fixture checks do not prove live Modal verification.
