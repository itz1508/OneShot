"""Canonical bucket model, schema, serializer, immutability (A1/A2)."""

from .model import Bucket, Hash, Provenance, LifecycleTimestamps
from .schema import canonical_schema, SCHEMA_VERSION
from .immutability import FROZEN_FIELDS, BucketImmutabilityViolation, check_mutation
from .serializer import canonical_dumps

__all__ = [
    "Bucket",
    "Hash",
    "Provenance",
    "LifecycleTimestamps",
    "canonical_schema",
    "SCHEMA_VERSION",
    "FROZEN_FIELDS",
    "BucketImmutabilityViolation",
    "check_mutation",
    "canonical_dumps",
]
