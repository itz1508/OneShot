"""Unit tests for `rsm.assessment` — Source Assessment surface.

Freezes the architectural contract from the §14 "RSM-first" rule:
assessment is a pure, read-only function of the frozen Bucket. It never
performs network I/O, never mutates the Bucket, never calls an LLM. Its
output tells a host application whether to proceed through RSM's
observation + preparation pipeline or to hand the request directly to
the Agent.
"""

from __future__ import annotations

from pathlib import Path

from rsm.assessment import (
    SourceAssessment,
    SourceAssessmentReason,
    assess_source,
)
from rsm.bucket.serializer import canonical_dumps
from rsm.extraction.folder import extract_folder
from rsm.extraction.opaque import extract_opaque
from rsm.extraction.text import extract_text


# ---- Shape ----------------------------------------------------------------


def test_assessment_schema_version_is_1():
    b = extract_text("hi", source_uri="demo.txt")
    a = assess_source(b)
    assert a.schema_version == "1"
    # DTO is strict (extra='forbid') — a safeguard that assertions below
    # cannot silently stop checking a field.
    assert isinstance(a, SourceAssessment)


# ---- requires_observation / requires_vision -------------------------------


def test_text_bucket_requires_observation_but_not_vision():
    b = extract_text("hello world", source_uri="demo.txt")
    a = assess_source(b)
    assert a.requires_observation is True
    assert a.requires_vision is False
    assert SourceAssessmentReason.SOURCE_PRESENT in a.reasons
    assert SourceAssessmentReason.TEXT_SOURCE in a.reasons
    # Scalar fields reflect the Bucket exactly.
    assert a.source_size_bytes == len("hello world".encode("utf-8"))
    assert a.source_size_chars == len("hello world")
    assert a.origin == "text"


def test_empty_text_bucket_does_not_require_observation():
    """An empty Bucket is honestly 'nothing to observe'."""
    b = extract_text("", source_uri="empty.txt")
    a = assess_source(b)
    assert a.requires_observation is False
    assert SourceAssessmentReason.SOURCE_EMPTY in a.reasons
    # Reasons/limitations do NOT leak misleading "folder has readable
    # files" from the SCAN artefact (one FileRef per simple-source).
    assert SourceAssessmentReason.FOLDER_HAS_READABLE_FILES not in a.reasons
    assert a.limitations == []


def test_markdown_bucket_is_text_source():
    b = extract_text("# Title", source_uri="doc.md", kind="pasted")
    a = assess_source(b)
    assert a.requires_observation is True
    assert SourceAssessmentReason.TEXT_SOURCE in a.reasons


def test_folder_with_image_requires_vision(tmp_path: Path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.txt").write_text("x")
    (root / "cat.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    bucket = extract_folder(root).parent

    a = assess_source(bucket)
    assert a.requires_observation is True
    assert a.requires_vision is True
    assert a.files.discovered == 2
    assert a.files.readable == 1
    assert a.files.opaque == 1
    assert a.files.unreadable == 0
    assert SourceAssessmentReason.IMAGE_SOURCE in a.reasons
    # Honest limitation that image bytes must be supplied by the caller.
    assert any("VisionProvider" in lim for lim in a.limitations)


def test_folder_with_unsupported_file_lists_limitation(tmp_path: Path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "weird.xyz").write_text("x")
    bucket = extract_folder(root).parent

    a = assess_source(bucket)
    assert a.files.unreadable == 1
    assert SourceAssessmentReason.FOLDER_HAS_UNREADABLE_FILES in a.reasons
    assert any("unsupported_extension" in lim for lim in a.limitations)


def test_opaque_bucket_lists_vision_limitation():
    """A simple-origin opaque Bucket (image bytes with no filesystem
    manifest) still cannot be observed without Vision — the assessment
    records that honestly."""
    b = extract_opaque(b"\x89PNG\r\n\x1a\n", source_uri="raw.png", media_type="image/png")
    a = assess_source(b)
    # No image File in the SCAN manifest (simple-origin opaque Bucket),
    # so `requires_vision` is False — but the limitation is explicit.
    assert a.origin == "opaque"
    assert any("Vision reader is required" in lim for lim in a.limitations)


# ---- Purity ---------------------------------------------------------------


def test_assess_source_does_not_mutate_bucket():
    b = extract_text("don't touch me")
    before = b.model_dump(mode="json")
    before_bytes = canonical_dumps(before)
    _ = assess_source(b)
    assert b.model_dump(mode="json") == before
    assert canonical_dumps(b.model_dump(mode="json")) == before_bytes
    assert b.hash.value == before["hash"]["value"]


def test_assessment_integrity_matches_bucket_hash():
    b = extract_text("hashcheck")
    a = assess_source(b)
    assert a.integrity["algorithm"] == b.hash.algorithm
    assert a.integrity["value"] == b.hash.value


def test_assessment_is_deterministic(tmp_path: Path):
    """Same Bucket → identical assessment (pure function)."""
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.txt").write_text("alpha")
    (root / "cat.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    bucket = extract_folder(root).parent

    a1 = assess_source(bucket)
    a2 = assess_source(bucket)
    assert a1.model_dump(mode="json") == a2.model_dump(mode="json")


# ---- Dependency boundary --------------------------------------------------


def test_rsm_assessment_imports_only_approved_packages():
    """Assessment stays as narrow as rsm.reader. It never imports an
    Agent SDK, Snapshot, Replay, or any provider."""
    import ast
    import inspect
    import rsm.assessment.assess as m
    import rsm.assessment.model as m2

    forbidden_frameworks = {
        "openai", "anthropic", "langchain", "langgraph", "llama_index",
        "crewai", "autogen", "pydantic_ai", "strands", "mcp",
    }
    forbidden_rsm_packages = {"rsm.snapshot", "rsm.replay",
                              "rsm.classification", "rsm.execution"}
    # Walk AST imports — comments / docstrings may mention these words.
    for mod in (m, m2):
        tree = ast.parse(inspect.getsource(mod))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module.split(".")[0])
                    # Also catch relative "..snapshot" style via module name.
                    imported.add(node.module)
        # No forbidden framework imports.
        bad = imported & forbidden_frameworks
        assert bad == set(), f"{mod.__name__} imports {bad!r}"
        # Snapshot / Replay / Classification / Execution are forbidden
        # from assessment (keeps the assessment pure and read-only).
        for pkg in forbidden_rsm_packages:
            assert pkg not in imported, (
                f"{mod.__name__} imports {pkg!r}; assessment must stay "
                "framework-independent at the SCAN+Reader level"
            )
