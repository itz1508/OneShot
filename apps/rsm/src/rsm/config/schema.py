"""Fail-closed configuration schema (Pydantic 2)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ConfigValidationError(Exception):
    """Raised when configuration validation fails (fail-closed)."""


class Daemon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=1, le=65535)


class Persistence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: Literal["fs", "sqlite"] = "fs"
    root: str = "./.rsm-store"


class Boundaries(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_source_bytes: int = Field(default=128 * 1024 * 1024, ge=1)
    max_folder_depth: int = Field(default=16, ge=1)
    max_folder_file_count: int = Field(default=20_000, ge=1)
    archive_entry_bytes: int = Field(default=64 * 1024 * 1024, ge=1)
    archive_total_bytes: int = Field(default=512 * 1024 * 1024, ge=1)
    max_pdf_pages: int = Field(default=2000, ge=1)


class Transports(BaseModel):
    model_config = ConfigDict(extra="forbid")
    http_enabled: bool = True
    mcp_enabled: bool = False


class Logging(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class RSMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daemon: Daemon = Field(default_factory=Daemon)
    persistence: Persistence = Field(default_factory=Persistence)
    boundaries: Boundaries = Field(default_factory=Boundaries)
    transports: Transports = Field(default_factory=Transports)
    logging: Logging = Field(default_factory=Logging)

    @classmethod
    def validate_dict(cls, data: dict) -> "RSMConfig":
        try:
            return cls.model_validate(data)
        except ValidationError as e:
            raise ConfigValidationError(str(e)) from e
