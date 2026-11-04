"""Provider contracts for typed configuration and capability probe records."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from agent.contracts.common import ContractModel


class ProviderProtocol(StrEnum):
    """Wire protocol for provider communication."""

    OPENAI_COMPATIBLE = "openai_compatible"


class CapabilityState(StrEnum):
    """Whether a capability is required, optional, or disabled."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    DISABLED = "disabled"


class ProbeStatus(StrEnum):
    """Result of a capability probe."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"
    UNSUPPORTED = "unsupported"


class ProviderConfig(ContractModel):
    """Typed provider configuration loaded from YAML.

    The model is supplied directly or through the configured environment variable.
    """

    provider_id: str = Field(min_length=1)
    protocol: ProviderProtocol = ProviderProtocol.OPENAI_COMPATIBLE
    sdk: str = Field(min_length=1)
    api_key_env: str = Field(min_length=1)
    base_url: str | None = None
    base_url_env: str | None = None
    model: str | None = None
    model_env: str | None = None
    timeout_seconds: int = 60
    max_retries: int = Field(ge=0, le=10, default=0)
    capabilities: dict[str, CapabilityState] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_model_or_env(self) -> ProviderConfig:
        if not self.model and not self.model_env:
            raise ValueError("ProviderConfig requires model or model_env")
        return self


class CapabilityResult(ContractModel):
    """Result of probing a single provider capability."""

    capability: str = Field(min_length=1)
    status: ProbeStatus
    observation: str = ""
    duration_ms: int = Field(ge=0, default=0)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    request_id: str | None = None
    error_class: str | None = None


class ProviderProbeRecord(ContractModel):
    """Full probe record with all capability results for a provider."""

    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    protocol: ProviderProtocol
    results: list[CapabilityResult] = Field(default_factory=list)

    def failed_required(self, config: ProviderConfig) -> list[str]:
        """Return list of required capabilities that did not pass."""
        result_map = {r.capability: r.status for r in self.results}
        failed: list[str] = []
        for cap, state in config.capabilities.items():
            if state is CapabilityState.REQUIRED and result_map.get(cap) is not ProbeStatus.PASSED:
                failed.append(cap)
        return failed
