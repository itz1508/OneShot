# OneShot Model Bridge — Security Boundaries

This repository is public.

- Do not commit plaintext API keys, provider tokens, secrets, env files, or personal data.
- Do not submit private prompts or code through the current `bridge/requests` JSON channel: only the provider credential is RSA-encrypted; prompts are not encrypted.
- Do not treat the ephemeral RSA key exchange as a substitute for access control, complete end-to-end message encryption, or secure result storage.
- GitHub Actions output may include model responses, error bodies and token usage. Do not send confidential content without a private authenticated result channel.
- Do not automatically execute model-generated code or grant the model repository write authority.
- Keep providers independent: Baseten uses exactly `meta-models/muse-spark-open-1026`; Modal/Qwen has its own authentication and verification requirements.
- Preserve evidence of actual provider HTTP status, model identity, result, and failure. Do not call DNS checks authenticated inference.
- Before using this bridge for proprietary OneShot tasks, use a private execution repository or implement encrypted prompt/result transport with a verified authority boundary.

The backup branch holds historical OneShot material for rollback; it does not establish that historical source was accepted or releasable.
