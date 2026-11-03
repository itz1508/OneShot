"""Read-only resolver protocols — no IO implementation."""

from __future__ import annotations

from typing import Protocol

from agent.contracts.common import ArtifactRef
from agent.contracts.host import ReceiptRef


class ArtifactResolver(Protocol):
    def resolve(self, ref: ArtifactRef) -> bytes: ...


class ReceiptVerifier(Protocol):
    def verify(self, ref: ReceiptRef, subject_digest: str) -> bool: ...


class RepositoryIdentityReader(Protocol):
    def read_identity(self, source: str) -> str: ...


class EvidenceResolver(Protocol):
    def resolve_evidence(self, evidence_id: str) -> bytes: ...
