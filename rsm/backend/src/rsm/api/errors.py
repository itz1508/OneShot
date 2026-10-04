"""Structured error codes (Spec §34)."""

from __future__ import annotations

from typing import Any


class RSMError(Exception):
    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class UnsupportedSchemaVersion(RSMError):
    code = "UNSUPPORTED_SCHEMA_VERSION"
    http_status = 400


class BucketNotFound(RSMError):
    code = "BUCKET_NOT_FOUND"
    http_status = 404


class IllegalLifecycleTransition(RSMError):
    code = "ILLEGAL_LIFECYCLE_TRANSITION"
    http_status = 409


class BucketFrozen(RSMError):
    code = "BUCKET_FROZEN"
    http_status = 409


class ValidationFailed(RSMError):
    code = "VALIDATION_FAILED"
    http_status = 422


class BoundaryViolation(RSMError):
    code = "BOUNDARY_VIOLATION"
    http_status = 413


class RsmDisabled(RSMError):
    code = "RSM_DISABLED"
    http_status = 409


class NoSourceSelected(RSMError):
    code = "NO_SOURCE_SELECTED"
    http_status = 409


class UnknownInteraction(RSMError):
    code = "UNKNOWN_INTERACTION"
    http_status = 404
