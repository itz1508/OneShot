# api_fundamentals

Provider capability probes for OneShot. Tests chat, streaming, tool calling,
structured output, prompt caching, reasoning, vision, long context, error
handling, and search grounding.

## Usage

```sh
python -m api_fundamentals.run_probe --config .agents/providers/meta.yaml --output /tmp/probe.json
```

The probe runner loads a ProviderConfig, builds the adapter, and runs each
capability probe. Results are written as a ProviderProbeRecord with token
accounting.
