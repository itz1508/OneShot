"""Read-only PRE and POST Discovery modes around the existing Research stage.

These are Host services, not new role stages. Neither mode chooses Build
actions or advances stages. Durable artifacts use the existing ArtifactStore.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from agent.contracts.common import ArtifactRef
from agent.contracts.discovery_sandwich import (
    DiscoveryPost,
    DiscoveryPre,
    DiscoveryResearchRequest,
    DiscoverySource,
    InspectionStatus,
    ReconciledResearchItem,
)
from agent.contracts.research import CatalogMatchStatus, ResearchIntent, ResearchRecord
from agent.research_catalog import ResearchCatalog
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.controller import Stage, TransitionError

if TYPE_CHECKING:
    from agent.runtime.controller import HostController


class DiscoveryError(ValueError):
    """A required input, source observation, or stage binding is missing."""


def extractive_summary(text: str) -> str:
    """Deterministic local fallback; not a model-authored summary."""
    result = " ".join(text.split())
    if not result:
        raise DiscoveryError("user intent is empty")
    return result[:360].rstrip()


def inspect_scoped_workspace(root: Path | None, max_files: int = 500) -> DiscoverySource:
    """Read-only bounded inventory: skips symlinks and hidden directories.

    This is Discovery context, not a complete Git source checkpoint.
    """
    if root is None:
        return DiscoverySource(
            status=InspectionStatus.UNAVAILABLE,
            root_label="no_trusted_workspace",
            manifest_digest=hashlib.sha256(b"no_trusted_workspace").hexdigest(),
            limitations=("No registered trusted workspace; repository claims are unavailable",),
        )
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise DiscoveryError("trusted workspace is not a directory")
    manifest: list[str] = []
    incomplete = False
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".")
            and d not in {"node_modules", "__pycache__", "dist", "build"}
            and not (Path(directory) / d).is_symlink()
        )
        for filename in sorted(files):
            path = Path(directory) / filename
            if filename.startswith(".") or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if len(manifest) >= max_files:
                incomplete = True
                break
            try:
                size = path.stat().st_size
                if size > 2_000_000:
                    incomplete = True
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                incomplete = True
                continue
            manifest.append(f"{relative}:{size}:{digest}")
        if incomplete and len(manifest) >= max_files:
            break
    digest = hashlib.sha256("\n".join(sorted(manifest)).encode()).hexdigest()
    return DiscoverySource(
        status=InspectionStatus.PARTIAL if incomplete else InspectionStatus.CAPTURED,
        root_label="trusted_workspace",
        manifest_digest=digest,
        inspected_paths=tuple(row.split(":", 1)[0] for row in sorted(manifest)),
        limitations=("Bounded inventory; not a complete Git source lock",)
        + (("File budget, size, or read limitation encountered",) if incomplete else ()),
    )


class DiscoverySandwich:
    """One Host, two inspection modes, and no competing execution controller."""

    def __init__(self, host: HostController) -> None:
        self.host = host

    def _verified(self, ref: ArtifactRef) -> bytes:
        digest = self.host.artifact_store.get_digest(ref.artifact_id, ref.artifact_revision)
        if digest != ref.artifact_digest:
            raise DiscoveryError("artifact identity/digest mismatch")
        return self.host.artifact_store.get_verified(ref.artifact_id, ref.artifact_revision)

    def _store(self, model: BaseModel, artifact_id: str, revision: int, contract_id: str) -> ArtifactRef:
        digest = self.host.artifact_store.put_immutable(model, artifact_id, revision, contract_id, "1.0")
        return ArtifactRef(
            artifact_id=artifact_id,
            artifact_revision=revision,
            artifact_digest=digest,
            contract_id=contract_id,
            contract_version="1.0",
            serializer_profile=SERIALIZER_PROFILE,
        )

    def pre_scan(
        self,
        *,
        task_id: str,
        thread_message_id: str,
        input_ref: ArtifactRef,
        user_intent: str,
        source: DiscoverySource,
        summary: Callable[[str], str] = extractive_summary,
        summary_method: str = "extractive",
        template_id: str | None = None,
        template_version: str | None = None,
        research_questions: tuple[str, ...] = (),
    ) -> tuple[DiscoveryResearchRequest, ArtifactRef, ArtifactRef]:
        state = self.host.get_state(task_id)
        if state is None or state.current_stage is not Stage.RESEARCH:
            raise TransitionError("PRE requires active Research stage")
        if state.active_work_artifact_id is not None:
            raise TransitionError("Research already assigned; reconcile before re-dispatch")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", thread_message_id):
            raise DiscoveryError("invalid authenticated message identifier")
        raw = json.loads(self._verified(input_ref))
        if raw.get("task_id") != task_id or raw.get("text") != user_intent:
            raise DiscoveryError("message does not match verified task input")
        if raw.get("thread_message_id") != thread_message_id:
            raise DiscoveryError("thread message identity not verified by task input")
        if not user_intent.strip():
            raise DiscoveryError("empty user intent")
        summarized = summary(user_intent).strip()
        if not summarized:
            raise DiscoveryError("summary provider returned empty output")
        # Catalog contributes synthetic investigation guidance, never evidence.
        catalog = ResearchCatalog()
        words = tuple(sorted(set(re.findall(r"[a-z0-9_]+", user_intent.lower()))))
        match = catalog.match(ResearchIntent.INVESTIGATE_QUESTION, words)
        sample = (
            catalog.get_sample(match.catalog_id)
            if match.match_status in {CatalogMatchStatus.MATCHED, CatalogMatchStatus.EXACT}
            else None
        )
        if sample is not None:
            template_id = sample.catalog_id
            template_version = sample.version
        else:
            template_id = "NONE"
            template_version = catalog.version
        questions = tuple(q.strip() for q in research_questions if q.strip()) or (
            sample.research_checklist
            if sample is not None
            else (
                "Identify evidence, constraints and open questions required to satisfy the original intent.",
                "Investigate compatibility with observed repository components.",
                "Identify source-grounded fixture and verification guidance without claiming execution.",
            )
        )
        source_ref = self._store(source, f"discovery-source:{task_id}", input_ref.artifact_revision, "discovery_source")
        pre = DiscoveryPre(
            task_id=task_id,
            run_id=state.run_id,
            thread_message_id=thread_message_id,
            message_revision=input_ref.artifact_revision,
            user_intent_ref=input_ref,
            source_ref=source_ref,
            intent_summary=summarized,
            summary_method=summary_method,
            template_id=template_id,
            template_version=template_version,
            research_questions=questions,
            provisional_success_criteria=sample.success_criteria if sample is not None else (),
        )
        pre_ref = self._store(pre, f"discovery-pre:{task_id}", pre.message_revision, "discovery_pre")
        # Preserve original text even when a model-generated summary is supplied.
        info = "\n".join(
            (
                f"Original user intent: {user_intent}",
                f"Intent summary ({summary_method}): {summarized}",
                f"Catalog guidance (synthetic): {template_id}@{template_version}",
                "Discovery research questions:",
                *(f"- {q}" for q in questions),
                f"Repository inventory status: {source.status.value}",
                f"Repository inventory digest: {source.manifest_digest}",
            )
        )
        request = DiscoveryResearchRequest(
            task_id=task_id,
            run_id=state.run_id,
            thread_message_id=thread_message_id,
            request_revision=input_ref.artifact_revision,
            user_intent_ref=input_ref,
            discovery_pre_ref=pre_ref,
            information_needed=info,
        )
        request_ref = self._store(
            request,
            f"discovery-research-request:{task_id}",
            input_ref.artifact_revision,
            "discovery_research_request",
        )
        self.host.event_store.append(task_id, "discovery_pre_created", pre_ref.artifact_id)
        return request, pre_ref, request_ref

    def normalize_ingest(
        self,
        *,
        task_id: str,
        pre_ref: ArtifactRef,
        research_ref: ArtifactRef,
        source: DiscoverySource,
    ) -> tuple[DiscoveryPost, ArtifactRef]:
        state = self.host.get_state(task_id)
        if state is None or state.current_stage is not Stage.AUDIT_DISCOVERY:
            raise TransitionError("POST requires active Audit Discovery stage")
        pre = DiscoveryPre.model_validate_json(self._verified(pre_ref))
        research = ResearchRecord.model_validate_json(self._verified(research_ref))
        if pre.task_id != task_id or pre.run_id != state.run_id:
            raise DiscoveryError("PRE belongs to another task/run")
        if research.task_id != task_id or research.run_id != state.run_id:
            raise DiscoveryError("Research belongs to another task/run")
        before = DiscoverySource.model_validate_json(self._verified(pre.source_ref))
        source_ref = self._store(source, f"discovery-post-source:{task_id}", pre.message_revision, "discovery_source")
        stable = before.manifest_digest == source.manifest_digest and before.status == source.status
        valid_evidence = {e.evidence_id for e in research.evidence if e.status.value == "valid"}
        items = tuple(
            ReconciledResearchItem(
                claim_id=claim.claim_id,
                statement=claim.statement,
                evidence_refs=claim.evidence_refs,
                evidence_status=claim.status.value,
                repository_applicability="unassessed",
                limitations=("Research evidence not independently mapped to repository",)
                + (
                    ("Referenced verified evidence is missing",)
                    if any(ref not in valid_evidence for ref in claim.evidence_refs)
                    else ()
                ),
            )
            for claim in research.claims
        )
        post = DiscoveryPost(
            task_id=task_id,
            run_id=state.run_id,
            thread_message_id=pre.thread_message_id,
            discovery_pre_ref=pre_ref,
            research_ref=research_ref,
            source_at_pre_ref=pre.source_ref,
            source_at_post_ref=source_ref,
            source_stable=stable,
            research_items=items,
            contradictions=("Repository changed between PRE and POST",) if not stable else (),
            unresolved=research.unknowns,
        )
        post_ref = self._store(post, f"discovery-post:{task_id}", pre.message_revision, "discovery_post")
        self.host.event_store.append(task_id, "discovery_post_created", post_ref.artifact_id)
        return post, post_ref
