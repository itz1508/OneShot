"""G07 — manifest binding on BuildRecord.

A completed Build must carry a `manifest_binding` with
(task_id, research_revision, plan_revision, scanner_identity,
detector_identities, fixture_oracle_sha, oracle_revision,
build_receipt_sha). validate_pipeline cross-checks the manifest's
plan_revision and research_revision against the Plan and Research
revisions on the same triple.

Red (baseline before this change) is already implicit — build_plan
would complete without a manifest_binding and validate_pipeline would
not refuse it. Green assertions:

  * build.manifest_binding is a non-empty dict after a successful
    run_workflow.
  * All required fields are present.
  * validate_pipeline refuses VERIFIED when manifest_binding is
    tampered with (plan_revision stale).
"""

from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for sub in ("agent", "agent/contracts", "tools"):
    sp = str(_REPO / sub)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from main import OneShotController  # noqa: E402
from models import validate_pipeline  # noqa: E402


class ManifestBindingPopulatedTest(unittest.TestCase):
    def setUp(self):
        os.environ["ONESHOT_TRUSTED_TEST_INPUT"] = "1"

    def tearDown(self):
        os.environ.pop("ONESHOT_TRUSTED_TEST_INPUT", None)

    def test_build_carries_manifest_binding(self):
        with tempfile.TemporaryDirectory(prefix="g07-pop-") as td:
            storage = Path(td) / "tasks.json"
            ctrl = OneShotController(storage_path=str(storage))
            result = ctrl.run_workflow(
                "g07-populated",
                str(_REPO),
                storage_path=str(storage),
                input_bundle={
                    "requirements": [
                        {
                            "id": "R1",
                            "statement": "Count characters",
                            "scope": "in_scope",
                            "authority_ref": "AGENTS.md",
                        }
                    ],
                    "findings": [
                        {
                            "id": "F1",
                            "claim": "bin/context_counter.py counts characters",
                            "evidence_refs": ["bin/context_counter.py"],
                            "assessment": "supported",
                            "limitations": "",
                        }
                    ],
                    "requirement_trace": [
                        {
                            "requirement_id": "R1",
                            "finding_ids": ["F1"],
                            "fixture_ids": ["bin/context_counter.py"],
                            "criterion_ids": ["agent/contracts/build.yaml"],
                            "disposition": "covered",
                        }
                    ],
                    "accepted_requirement_ids": ["R1"],
                    "plan_milestones": [
                        {
                            "id": "m1",
                            "goal": "x",
                            "files": [],
                            "steps": ["x"],
                            "commands": ["x"],
                            "expected_observations": ["x"],
                            "status": "pending",
                        }
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "c1",
                            "requirement_id": "R1",
                            "expected_result": "x",
                            "oracle_ref": "AGENTS.md",
                        }
                    ],
                    "claim_decisions": [
                        {
                            "id": "d1",
                            "source_finding_id": "F1",
                            "applicability": "USE",
                            "reason": "x",
                            "evidence_refs": ["bin/context_counter.py"],
                            "affected_step_ids": ["m1"],
                            "revision": 1,
                            "recorded_at": "2026-11-01T00:00:00Z",
                        }
                    ],
                    "gap_findings_mark_resolved": {
                        "fix_receipt_ref": "AGENTS.md",
                        "recheck_ref": "AGENTS.md",
                    },
                },
            )
            build = result["build"]
            manifest = build.get("manifest_binding")
            self.assertIsNotNone(manifest, "manifest_binding missing from Build")
            self.assertEqual(manifest["task_id"], build["task_id"])
            self.assertEqual(manifest["plan_revision"], result["plan"]["revision"])
            self.assertEqual(manifest["research_revision"], result["research"]["revision"])
            for key in (
                "scanner_identity",
                "detector_identities",
                "fixture_oracle_sha",
                "oracle_revision",
                "build_receipt_sha",
            ):
                self.assertIn(key, manifest)
                self.assertTrue(manifest[key], f"manifest.{key} must be non-empty")

    def test_stale_plan_revision_in_manifest_rejected(self):
        """Tampered manifest with wrong plan_revision must surface a
        cross-record error from validate_pipeline."""
        with tempfile.TemporaryDirectory(prefix="g07-stale-") as td:
            storage = Path(td) / "tasks.json"
            ctrl = OneShotController(storage_path=str(storage))
            result = ctrl.run_workflow(
                "g07-stale",
                str(_REPO),
                storage_path=str(storage),
                input_bundle={
                    "requirements": [
                        {
                            "id": "R1",
                            "statement": "Count",
                            "scope": "in_scope",
                            "authority_ref": "AGENTS.md",
                        }
                    ],
                    "findings": [
                        {
                            "id": "F1",
                            "claim": "x",
                            "evidence_refs": ["bin/context_counter.py"],
                            "assessment": "supported",
                            "limitations": "",
                        }
                    ],
                    "requirement_trace": [
                        {
                            "requirement_id": "R1",
                            "finding_ids": ["F1"],
                            "fixture_ids": ["bin/context_counter.py"],
                            "criterion_ids": ["agent/contracts/build.yaml"],
                            "disposition": "covered",
                        }
                    ],
                    "accepted_requirement_ids": ["R1"],
                    "plan_milestones": [
                        {
                            "id": "m1",
                            "goal": "x",
                            "files": [],
                            "steps": ["x"],
                            "commands": ["x"],
                            "expected_observations": ["x"],
                            "status": "pending",
                        }
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "c1",
                            "requirement_id": "R1",
                            "expected_result": "x",
                            "oracle_ref": "AGENTS.md",
                        }
                    ],
                    "claim_decisions": [
                        {
                            "id": "d1",
                            "source_finding_id": "F1",
                            "applicability": "USE",
                            "reason": "x",
                            "evidence_refs": ["bin/context_counter.py"],
                            "affected_step_ids": ["m1"],
                            "revision": 1,
                            "recorded_at": "2026-11-01T00:00:00Z",
                        }
                    ],
                    "gap_findings_mark_resolved": {
                        "fix_receipt_ref": "AGENTS.md",
                        "recheck_ref": "AGENTS.md",
                    },
                },
            )
            # Tamper with the build's manifest_binding.plan_revision.
            research = result["research"]
            plan = result["plan"]
            tampered = copy.deepcopy(result["build"])
            tampered["manifest_binding"]["plan_revision"] = 99
            # Re-build the hybrid resolver on the triple's evidence index.
            # The simplest way to prove the cross-record check fires is
            # to compare without a resolver — validate_pipeline still
            # runs the cross-record manifest check.
            errors = validate_pipeline(research, plan, tampered)
            self.assertTrue(
                any("plan_revision mismatch" in e for e in errors),
                f"expected 'plan_revision mismatch' error; got: {errors}",
            )


if __name__ == "__main__":
    unittest.main()


class ManifestPlaceholderRejectedTest(unittest.TestCase):
    """G07 reopen (reviewer finding on 9d2ce25):

    manifest INTEGRITY must refuse the specific placeholder literals the
    previous build_plan fallback emitted ('unknown' / 'no_oracle_module')
    and refuse detector_identities with empty values. These three red
    tests pin that policy.
    """

    def test_placeholder_scanner_identity_rejected(self):
        from models import ManifestBinding
        from pydantic import ValidationError

        base = {
            "task_id": "t1",
            "research_revision": 1,
            "plan_revision": 1,
            "scanner_identity": "unknown",
            "detector_identities": {"stub": "a" * 64},
            "fixture_oracle_sha": "a" * 64,
            "oracle_revision": 1,
            "build_receipt_sha": "a" * 64,
        }
        with self.assertRaises(ValidationError) as ctx:
            ManifestBinding.model_validate(base)
        self.assertIn("placeholder literal 'unknown'", str(ctx.exception))

    def test_placeholder_fixture_oracle_sha_rejected(self):
        from models import ManifestBinding
        from pydantic import ValidationError

        base = {
            "task_id": "t1",
            "research_revision": 1,
            "plan_revision": 1,
            "scanner_identity": "a" * 64,
            "detector_identities": {"stub": "a" * 64},
            "fixture_oracle_sha": "no_oracle_module",
            "oracle_revision": 1,
            "build_receipt_sha": "a" * 64,
        }
        with self.assertRaises(ValidationError) as ctx:
            ManifestBinding.model_validate(base)
        self.assertIn("placeholder literal 'no_oracle_module'", str(ctx.exception))

    def test_empty_detector_identity_rejected(self):
        from models import ManifestBinding
        from pydantic import ValidationError

        base = {
            "task_id": "t1",
            "research_revision": 1,
            "plan_revision": 1,
            "scanner_identity": "a" * 64,
            "detector_identities": {
                "ok": "a" * 64,
                "agent/adapters/source_comparison.py": "",
            },
            "fixture_oracle_sha": "a" * 64,
            "oracle_revision": 1,
            "build_receipt_sha": "a" * 64,
        }
        with self.assertRaises(ValidationError) as ctx:
            ManifestBinding.model_validate(base)
        self.assertIn("must be a non-empty sha", str(ctx.exception))

    def test_empty_detector_identities_dict_rejected(self):
        from models import ManifestBinding
        from pydantic import ValidationError

        base = {
            "task_id": "t1",
            "research_revision": 1,
            "plan_revision": 1,
            "scanner_identity": "a" * 64,
            "detector_identities": {},
            "fixture_oracle_sha": "a" * 64,
            "oracle_revision": 1,
            "build_receipt_sha": "a" * 64,
        }
        with self.assertRaises(ValidationError) as ctx:
            ManifestBinding.model_validate(base)
        self.assertIn(
            "detector_identities must bind at least one detector",
            str(ctx.exception),
        )


class ManifestDigestRecomputationTest(unittest.TestCase):
    """G07 reopen (reviewer finding on 9d2ce25):

    validate_pipeline must INDEPENDENTLY recompute fixture_oracle_sha
    and build_receipt_sha and refuse the manifest when the stored
    value doesn't match the recomputation. These red tests pin that
    policy — before the fix, no cross-record error fires.
    """

    def setUp(self):
        os.environ["ONESHOT_TRUSTED_TEST_INPUT"] = "1"

    def tearDown(self):
        os.environ.pop("ONESHOT_TRUSTED_TEST_INPUT", None)

    def _one_shot(self):
        """Run run_workflow once and return (research, plan, build)."""
        with tempfile.TemporaryDirectory(prefix="g07-digest-") as td:
            storage = Path(td) / "tasks.json"
            ctrl = OneShotController(storage_path=str(storage))
            result = ctrl.run_workflow(
                "g07-digest-recompute",
                str(_REPO),
                storage_path=str(storage),
                input_bundle={
                    "requirements": [
                        {
                            "id": "R1",
                            "statement": "Count characters",
                            "scope": "in_scope",
                            "authority_ref": "AGENTS.md",
                        }
                    ],
                    "findings": [
                        {
                            "id": "F1",
                            "claim": "bin/context_counter.py counts characters",
                            "evidence_refs": ["bin/context_counter.py"],
                            "assessment": "supported",
                            "limitations": "",
                        }
                    ],
                    "requirement_trace": [
                        {
                            "requirement_id": "R1",
                            "finding_ids": ["F1"],
                            "fixture_ids": ["bin/context_counter.py"],
                            "criterion_ids": ["agent/contracts/build.yaml"],
                            "disposition": "covered",
                        }
                    ],
                    "accepted_requirement_ids": ["R1"],
                    "plan_milestones": [
                        {
                            "id": "m1",
                            "goal": "x",
                            "files": [],
                            "steps": ["x"],
                            "commands": ["x"],
                            "expected_observations": ["x"],
                            "status": "pending",
                        }
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "c1",
                            "requirement_id": "R1",
                            "expected_result": "x",
                            "oracle_ref": "AGENTS.md",
                        }
                    ],
                    "claim_decisions": [
                        {
                            "id": "d1",
                            "source_finding_id": "F1",
                            "applicability": "USE",
                            "reason": "x",
                            "evidence_refs": ["bin/context_counter.py"],
                            "affected_step_ids": ["m1"],
                            "revision": 1,
                            "recorded_at": "2026-11-01T00:00:00Z",
                        }
                    ],
                    "gap_findings_mark_resolved": {
                        "fix_receipt_ref": "AGENTS.md",
                        "recheck_ref": "AGENTS.md",
                    },
                },
            )
            return (
                copy.deepcopy(result["research"]),
                copy.deepcopy(result["plan"]),
                copy.deepcopy(result["build"]),
            )

    def test_tampered_fixture_oracle_sha_rejected(self):
        """A manifest whose fixture_oracle_sha doesn't match the
        independent sha of agent/contracts/oracles.py MUST surface a
        cross-record error."""
        research, plan, build = self._one_shot()
        # Replace the real digest with a different valid sha value so
        # the Pydantic placeholder rejection doesn't catch it first.
        tampered_sha = "f" * 64
        build["manifest_binding"]["fixture_oracle_sha"] = tampered_sha
        errors = validate_pipeline(research, plan, build)
        self.assertTrue(
            any(
                "fixture_oracle_sha mismatch" in e for e in errors
            ),
            f"expected fixture_oracle_sha mismatch; got: {errors}",
        )

    def test_tampered_build_receipt_sha_rejected(self):
        """A manifest whose build_receipt_sha doesn't match the independent
        sha-256 of execution.command_receipts MUST surface a cross-record
        error."""
        research, plan, build = self._one_shot()
        tampered_sha = "d" * 64
        build["manifest_binding"]["build_receipt_sha"] = tampered_sha
        errors = validate_pipeline(research, plan, build)
        self.assertTrue(
            any(
                "build_receipt_sha mismatch" in e for e in errors
            ),
            f"expected build_receipt_sha mismatch; got: {errors}",
        )
