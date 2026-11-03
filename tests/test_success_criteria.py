#!/usr/bin/env python3
"""Tests for SuccessCriteria models, canonical digest, and typed artifact validation.

Covers:
  * SuccessCriteria construction with model_validator digest enforcement
  * canonical_criteria_digest (dict and model produce identical digests)
  * validate_success_criteria_artifact (schema, identity, provenance, coverage)
  * Negative cases: wrong digest, tamper, missing fields, duplicates, uncovered
"""

from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from models import (
    SuccessCriteria,
    Criterion,
    CoverageEntry,
    EvidenceType,
    InsufficientEvidenceDisposition,
    CriterionPriority,
    canonical_criteria_digest,
    validate_success_criteria_artifact,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _criterion(cid="C001", **kw):
    """Build a minimal valid Criterion dict with sensible defaults."""
    defaults = dict(
        criterion_id=cid,
        statement="No vendor SDK in core deps",
        observable_outcome="git grep returns zero matches",
        priority="blocking",
        required_evidence_types=["repository_observation"],
        pass_condition="Zero matches",
        fail_condition="Any match",
        insufficient_evidence_disposition="block_handoff",
    )
    defaults.update(kw)
    return defaults


def _sc_dict(criteria=None, coverage=None, **kw):
    """Build a minimal valid SuccessCriteria dict with digest computed."""
    defaults = dict(
        success_criteria_id="SC001",
        operation_id="OP001",
        input_reference="input-001-r1",
        criteria_revision=1,
        authority_ref="AGENTS.md",
        source_revision="e2b86638",
        criteria=criteria or [_criterion()],
        coverage=coverage or [{"outcome_id": "OUT001", "criterion_ids": ["C001"]}],
    )
    defaults.update(kw)
    # Compute the correct digest so the model_validator passes.
    defaults["content_digest"] = canonical_criteria_digest(defaults)
    return defaults


# ---------------------------------------------------------------------------
# SuccessCriteria model_validator tests
# ---------------------------------------------------------------------------


class TestSuccessCriteriaValidator(unittest.TestCase):
    """The @model_validator automatically checks content_digest at construction."""

    def test_valid_construction(self):
        """Correct digest -> model_validator passes."""
        data = _sc_dict()
        sc = SuccessCriteria(**data)
        self.assertEqual(sc.success_criteria_id, "SC001")
        self.assertEqual(sc.criteria_revision, 1)
        self.assertEqual(sc.authority_ref, "AGENTS.md")
        self.assertEqual(len(sc.criteria), 1)
        self.assertEqual(len(sc.coverage), 1)

    def test_wrong_digest_rejected(self):
        """Incorrect digest -> model_validator raises ValidationError."""
        data = _sc_dict()
        data["content_digest"] = "a" * 64  # wrong but valid format
        with self.assertRaises(ValidationError):
            SuccessCriteria(**data)

    def test_missing_digest_rejected(self):
        """Missing content_digest -> required field raises ValidationError."""
        data = _sc_dict()
        del data["content_digest"]
        with self.assertRaises(ValidationError):
            SuccessCriteria(**data)

    def test_invalid_digest_format_rejected(self):
        """Non-SHA-256 format -> Field(pattern) raises ValidationError."""
        data = _sc_dict()
        data["content_digest"] = "too_short"
        with self.assertRaises(ValidationError):
            SuccessCriteria(**data)

    def test_tamper_detection(self):
        """Digest computed for original content fails after content change."""
        data = _sc_dict()
        original_digest = data["content_digest"]
        # Tamper: change criterion statement but keep old digest
        data["criteria"][0]["statement"] = "TAMPERED"
        data["content_digest"] = original_digest
        with self.assertRaises(ValidationError):
            SuccessCriteria(**data)

    def test_digest_updates_with_content(self):
        """Changed content with re-computed digest passes model_validator."""
        data = _sc_dict()
        data["criteria"][0]["statement"] = "Updated statement"
        data["content_digest"] = canonical_criteria_digest(data)
        sc = SuccessCriteria(**data)
        self.assertEqual(sc.criteria[0].statement, "Updated statement")

    def test_criteria_revision_minimum(self):
        """criteria_revision must be >= 1."""
        data = _sc_dict(criteria_revision=0)
        with self.assertRaises(ValidationError):
            SuccessCriteria(**data)

    def test_placeholder_rejection(self):
        """Placeholder strings in required fields are rejected."""
        data = _sc_dict()
        data["success_criteria_id"] = "<placeholder>"
        data["content_digest"] = canonical_criteria_digest(data)
        with self.assertRaises(ValidationError):
            SuccessCriteria(**data)


# ---------------------------------------------------------------------------
# canonical_criteria_digest tests
# ---------------------------------------------------------------------------


class TestCanonicalDigest(unittest.TestCase):
    """canonical_criteria_digest computes the digest the model_validator enforces."""

    def test_dict_and_model_produce_same_digest(self):
        """Digest from raw dict == digest from constructed model."""
        data = _sc_dict()
        sc = SuccessCriteria(**data)
        self.assertEqual(
            canonical_criteria_digest(data),
            canonical_criteria_digest(sc),
        )

    def test_digest_is_64_hex_chars(self):
        """Digest is a valid SHA-256 hex string."""
        digest = canonical_criteria_digest(_sc_dict())
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))

    def test_digest_changes_with_content(self):
        """Different content -> different digest."""
        d1 = _sc_dict()
        d2 = _sc_dict(success_criteria_id="SC999")
        self.assertNotEqual(
            canonical_criteria_digest(d1),
            canonical_criteria_digest(d2),
        )

    def test_digest_stable_for_same_content(self):
        """Same content -> same digest (deterministic)."""
        d1 = _sc_dict()
        d2 = _sc_dict()
        self.assertEqual(
            canonical_criteria_digest(d1),
            canonical_criteria_digest(d2),
        )

    def test_digest_includes_authority_and_source(self):
        """Changing authority_ref or source_revision changes the digest."""
        d1 = _sc_dict()
        d2 = _sc_dict(authority_ref="DIFFERENT.md")
        self.assertNotEqual(
            canonical_criteria_digest(d1),
            canonical_criteria_digest(d2),
        )

    def test_dict_criteria_coerced_through_pydantic(self):
        """Criterion dicts with defaults filled in produce same digest as models."""
        minimal = {
            "success_criteria_id": "SC001",
            "operation_id": "OP001",
            "input_reference": "input-001-r1",
            "criteria_revision": 1,
            "authority_ref": "AGENTS.md",
            "source_revision": "abc",
            "criteria": [
                {"criterion_id": "C1", "statement": "A", "observable_outcome": "B",
                 "required_evidence_types": ["source_document"],
                 "pass_condition": "ok", "fail_condition": "bad"},
            ],
            "coverage": [{"outcome_id": "O1", "criterion_ids": ["C1"]}],
        }
        digest_from_dict = canonical_criteria_digest(minimal)
        minimal["content_digest"] = digest_from_dict
        sc = SuccessCriteria(**minimal)
        self.assertEqual(canonical_criteria_digest(sc), digest_from_dict)


# ---------------------------------------------------------------------------
# validate_success_criteria_artifact tests
# ---------------------------------------------------------------------------


class TestValidateArtifact(unittest.TestCase):
    """Typed validation at the Research -> Planner handoff boundary."""

    def test_valid_artifact_no_errors(self):
        """Valid artifact with all fields -> empty error list."""
        data = _sc_dict()
        errors = validate_success_criteria_artifact(data)
        self.assertEqual(errors, [])

    def test_valid_artifact_from_json_string(self):
        """JSON string content is accepted."""
        data = _sc_dict()
        errors = validate_success_criteria_artifact(json.dumps(data))
        self.assertEqual(errors, [])

    def test_invalid_json_returns_error(self):
        """Non-JSON content -> parse error."""
        errors = validate_success_criteria_artifact("not json at all")
        self.assertEqual(len(errors), 1)
        self.assertIn("not valid JSON", errors[0])

    def test_non_object_json_returns_error(self):
        """JSON array instead of object -> type error."""
        errors = validate_success_criteria_artifact("[1, 2, 3]")
        self.assertEqual(len(errors), 1)
        self.assertIn("must be a JSON object", errors[0])

    def test_wrong_trusted_digest_detected(self):
        """content_digest != trusted_digest -> identity mismatch error."""
        data = _sc_dict()
        errors = validate_success_criteria_artifact(
            data, trusted_digest="b" * 64,
        )
        self.assertTrue(any("does not match trusted" in e for e in errors))

    def test_correct_trusted_digest_no_identity_error(self):
        """content_digest == trusted_digest -> no identity error."""
        data = _sc_dict()
        errors = validate_success_criteria_artifact(
            data, trusted_digest=data["content_digest"],
        )
        self.assertTrue(not any("does not match trusted" in e for e in errors))

    def test_missing_authority_ref_detected(self):
        """Missing authority_ref -> provenance error."""
        data = _sc_dict(authority_ref=None)
        data["content_digest"] = canonical_criteria_digest(data)
        errors = validate_success_criteria_artifact(data)
        self.assertTrue(any("authority_ref is required" in e for e in errors))

    def test_missing_source_revision_detected(self):
        """Missing source_revision -> provenance error."""
        data = _sc_dict(source_revision=None)
        data["content_digest"] = canonical_criteria_digest(data)
        errors = validate_success_criteria_artifact(data)
        self.assertTrue(any("source_revision is required" in e for e in errors))

    def test_duplicate_criterion_ids_detected(self):
        """Two criteria with same ID -> duplicate error."""
        data = _sc_dict(
            criteria=[
                _criterion("CX"),
                _criterion("CX", statement="Different"),
            ],
            coverage=[{"outcome_id": "O1", "criterion_ids": ["CX"]}],
        )
        errors = validate_success_criteria_artifact(data)
        self.assertTrue(any("duplicate criterion_id" in e for e in errors))

    def test_uncovered_criterion_detected(self):
        """Criterion not in any CoverageEntry -> uncovered error."""
        data = _sc_dict(
            criteria=[_criterion("C1"), _criterion("C2")],
            coverage=[{"outcome_id": "O1", "criterion_ids": ["C1"]}],
        )
        errors = validate_success_criteria_artifact(data)
        self.assertTrue(any("not covered" in e for e in errors))

    def test_empty_coverage_entry_criterion_ids_detected(self):
        """CoverageEntry with empty criterion_ids -> error."""
        data = _sc_dict(
            coverage=[
                {"outcome_id": "O1", "criterion_ids": ["C001"]},
                {"outcome_id": "O2", "criterion_ids": []},
            ],
        )
        errors = validate_success_criteria_artifact(data)
        self.assertTrue(any("criterion_ids is empty" in e for e in errors))

    def test_empty_evidence_types_detected(self):
        """Criterion with no required_evidence_types -> error."""
        data = _sc_dict(
            criteria=[_criterion(required_evidence_types=[])],
        )
        errors = validate_success_criteria_artifact(data)
        self.assertTrue(any("required_evidence_types is empty" in e for e in errors))

    def test_missing_pass_condition_detected(self):
        """Criterion with empty pass_condition -> error."""
        data = _sc_dict(
            criteria=[_criterion(pass_condition="")],
        )
        errors = validate_success_criteria_artifact(data)
        self.assertTrue(any("pass_condition is empty" in e for e in errors))

    def test_missing_fail_condition_detected(self):
        """Criterion with empty fail_condition -> error."""
        data = _sc_dict(
            criteria=[_criterion(fail_condition="")],
        )
        errors = validate_success_criteria_artifact(data)
        self.assertTrue(any("fail_condition is empty" in e for e in errors))

    def test_schema_validation_failure_returns_errors(self):
        """Invalid schema (missing required field) -> validation error."""
        bad = {"success_criteria_id": "SC001"}  # missing many required fields
        errors = validate_success_criteria_artifact(bad)
        self.assertTrue(any("failed schema validation" in e for e in errors))

    def test_bytes_content_accepted(self):
        """Bytes content is decoded and validated."""
        data = _sc_dict()
        errors = validate_success_criteria_artifact(
            json.dumps(data).encode("utf-8"),
        )
        self.assertEqual(errors, [])


# ---------------------------------------------------------------------------
# Criterion model tests
# ---------------------------------------------------------------------------


class TestCriterion(unittest.TestCase):
    """Criterion field validation and enum coverage."""

    def test_valid_criterion(self):
        c = Criterion(**_criterion())
        self.assertEqual(c.criterion_id, "C001")
        self.assertEqual(c.priority, CriterionPriority.BLOCKING)
        self.assertEqual(
            c.insufficient_evidence_disposition,
            InsufficientEvidenceDisposition.BLOCK_HANDOFF,
        )

    def test_placeholder_criterion_id_rejected(self):
        with self.assertRaises(ValidationError):
            Criterion(**_criterion(criterion_id="<placeholder>"))

    def test_empty_statement_rejected(self):
        with self.assertRaises(ValidationError):
            Criterion(**_criterion(statement=""))

    def test_empty_observable_outcome_rejected(self):
        with self.assertRaises(ValidationError):
            Criterion(**_criterion(observable_outcome=""))

    def test_all_evidence_types_valid(self):
        """All 11 EvidenceType enum values are usable."""
        for et in EvidenceType:
            c = Criterion(
                criterion_id=f"C_{et.value}",
                statement="test",
                observable_outcome="test",
                required_evidence_types=[et],
                pass_condition="ok",
                fail_condition="bad",
            )
            self.assertEqual(c.required_evidence_types[0], et)

    def test_all_dispositions_valid(self):
        """All 3 InsufficientEvidenceDisposition values are usable."""
        for disp in InsufficientEvidenceDisposition:
            c = Criterion(
                criterion_id=f"C_{disp.value}",
                statement="test",
                observable_outcome="test",
                insufficient_evidence_disposition=disp,
                pass_condition="ok",
                fail_condition="bad",
            )
            self.assertEqual(c.insufficient_evidence_disposition, disp)

    def test_all_priorities_valid(self):
        """All 3 CriterionPriority values are usable."""
        for pri in CriterionPriority:
            c = Criterion(
                criterion_id=f"C_{pri.value}",
                statement="test",
                observable_outcome="test",
                priority=pri,
                pass_condition="ok",
                fail_condition="bad",
            )
            self.assertEqual(c.priority, pri)

    def test_default_priority_is_major(self):
        c = Criterion(
            criterion_id="C1", statement="A", observable_outcome="B",
            pass_condition="ok", fail_condition="bad",
        )
        self.assertEqual(c.priority, CriterionPriority.MAJOR)

    def test_default_disposition_is_record_unknown(self):
        c = Criterion(
            criterion_id="C1", statement="A", observable_outcome="B",
            pass_condition="ok", fail_condition="bad",
        )
        self.assertEqual(
            c.insufficient_evidence_disposition,
            InsufficientEvidenceDisposition.RECORD_UNKNOWN,
        )


# ---------------------------------------------------------------------------
# CoverageEntry tests
# ---------------------------------------------------------------------------


class TestCoverageEntry(unittest.TestCase):

    def test_valid_coverage_entry(self):
        ce = CoverageEntry(outcome_id="OUT1", criterion_ids=["C1", "C2"])
        self.assertEqual(ce.outcome_id, "OUT1")
        self.assertEqual(ce.criterion_ids, ["C1", "C2"])

    def test_empty_criterion_ids_default(self):
        ce = CoverageEntry(outcome_id="OUT1")
        self.assertEqual(ce.criterion_ids, [])


if __name__ == "__main__":
    unittest.main()