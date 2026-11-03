"""CLI for running provider capability probes."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from agent.contracts.provider import CapabilityResult, CapabilityState, ProbeStatus, ProviderProbeRecord
from agent.runtime.provider_config import load_provider_config, resolve_model
from agent.runtime.provider_factory import build_provider
from api_fundamentals.probes.all import PROBES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = load_provider_config(args.config)
    adapter = build_provider(config)
    results: list[CapabilityResult] = []
    for name, state in config.capabilities.items():
        started = time.perf_counter()
        if state is CapabilityState.DISABLED:
            results.append(
                CapabilityResult(
                    capability=name,
                    status=ProbeStatus.NOT_RUN,
                    observation="disabled",
                    duration_ms=0,
                )
            )
            continue
        probe = PROBES.get(name)
        if probe is None:
            results.append(
                CapabilityResult(
                    capability=name,
                    status=ProbeStatus.UNSUPPORTED,
                    observation="no probe implementation",
                    duration_ms=0,
                )
            )
            continue
        try:
            observation = probe(adapter, config.options.get(name, {}))
            results.append(
                CapabilityResult(
                    capability=name,
                    status=ProbeStatus.PASSED,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    **observation,
                )
            )
        except Exception as exc:
            results.append(
                CapabilityResult(
                    capability=name,
                    status=ProbeStatus.FAILED,
                    observation=str(exc),
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error_class=type(exc).__name__,
                )
            )
    record = ProviderProbeRecord(
        provider_id=config.provider_id,
        model_id=resolve_model(config),
        protocol=config.protocol,
        results=results,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    print(record.model_dump_json(indent=2))
    return 1 if record.failed_required(config) else 0


if __name__ == "__main__":
    raise SystemExit(main())
