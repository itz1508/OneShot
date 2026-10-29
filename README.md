# OneShot — External Model Bridge

ChatGPT-operated external-model integration using GitHub Actions as the reachable execution environment.

## Status

- **Baseten**: verified model inference for `meta-models/muse-spark-open-1026`. Independent dynamic-prompt test returned `ONESHOT_DYNAMIC_PROMPT_OK` with HTTP 200 and `finish_reason=stop` in the source bridge repository.
- **Modal**: separate Qwen 3.8 configuration. The last test returned HTTP 401 because its proxy authentication was not established in this environment; do not treat it as verified.
- **This GitHub repository**: the bridge source has been transferred here. A model call from this new repository is **not yet independently verified**.
- **Coding-agent execution and ChatGPT MCP installation**: not implemented or verified. This repository currently provides model inference and network test workflows, not a complete autonomous build agent.

## Workflows

- `.github/workflows/oneshot-provider-probe.yml`: checks DNS and HTTPS reachability without credentials.
- `.github/workflows/oneshot-model-bridge.yml`: accepts an encrypted one-time credential submitted for a specific GitHub Actions run, calls the selected provider and records a bounded response in its job log.

The model bridge is deliberately bound to the exact Muse Spark model ID `meta-models/muse-spark-open-1026` for Baseten. Modal remains independent and must not silently fall back to or substitute for Baseten.

## How the bridge works

1. An operator starts the model bridge workflow.
2. The runner creates a temporary RSA private/public key pair and publishes the **public** key for that run.
3. The caller encrypts the provider's credential with that key and submits a request for the matching run.
4. The runner decrypts the credential in memory, sends the authenticated HTTPS inference request, records its observed response, and removes the temporary private key.

**Limitations:** Request prompts are currently plain JSON alongside the encrypted credential. This repository is public: **never submit a private prompt, internal OneShot source, user data or secret through `bridge/requests` here**. Do not commit plaintext credentials, tokens, `.env` files, or output containing secrets. GitHub Actions logs for this public repository may be visible publicly. Use the private source bridge for confidential tasks until the request body and result channel are protected.

The request-file/Actions bridge is an interim execution path, not a persistent MCP server and not an authorization mechanism for mutating OneShot source.

## Provenance and rollback

The replaced historical repository remains on branch [`backup/pre-agent-replacement-20261028`](../../tree/backup/pre-agent-replacement-20261028), anchored at commit `07f6f9c2a441cee8b4bf6393b89523bb28c4a1d7`. Replacing `main` does not delete Git history. Bridge source transferred from private `itz1508/.oneshot_agent` at commit `350c1c5a6e3fce2c9b73dce0ac8e981412176511`. Run-specific encrypted requests and ephemeral public keys were **not** transferred.

## Security

See [SECURITY.md](SECURITY.md). Credentials are deliberately absent from this repository. Do not place real provider secrets in GitHub commits, CI logs or issue text.
