"""Application configuration contracts -- typed config for providers, state, budgets, security."""

from __future__ import annotations

from pydantic import Field

from agent.contracts.common import ContractModel


class ProviderSelection(ContractModel):
    """Which provider profile to use."""

    profile: str = Field(min_length=1)


class StateConfig(ContractModel):
    """Where and how durable state is stored."""

    root_env: str = Field(min_length=1)
    serializer_profile: str = Field(min_length=1)


class BudgetConfig(ContractModel):
    """Execution budgets for requests, retries, and duration."""

    max_requests_per_run: int = Field(default=64, gt=0)
    max_retries_per_operation: int = Field(ge=0, default=3)
    max_duration_seconds: int = Field(gt=0, default=3600)


class SecurityConfig(ContractModel):
    """Security policy with default-deny and read-only source repository."""

    default_deny: bool = True
    source_repository: str = Field(pattern=r"^read_only$", default="read_only")


class AppConfig(ContractModel):
    """Top-level typed application configuration."""

    config_version: str = Field(min_length=1, default="1.0")
    provider: ProviderSelection
    state: StateConfig
    budgets: BudgetConfig = Field(default_factory=BudgetConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
