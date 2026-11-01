"""Oracle authority identity + fault-injection separation (G01 + G04).

These tests enforce that:

* Every acceptance oracle has a stable identity (sha) at module import.
* An oracle mutated after authorisation is REJECTED on next access.
* The oracle module does NOT import any fault-injector module (they
  must live in a separate test-only module so that the oracle cannot
  silently materialise the DUT's expected outcome).
* Catalog revision is monotonic.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for sub in ("agent", "agent/contracts"):
    sp = str(_REPO / sub)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import oracles  # noqa: E402  — path setup above


class OracleIdentityTest(unittest.TestCase):
    def test_catalog_has_known_ids(self):
        ids = oracles.CATALOG.ids()
        for required in (
            "S1.plan_correction.bad_case",
            "S2.do_not_use.bad_case",
            "S2.do_not_use.good_case",
            "S3.validate_first.bad_case",
            "S5.crash_restart.bad_case",
        ):
            self.assertIn(required, ids)

    def test_every_case_has_stable_sha(self):
        for cid in oracles.CATALOG.ids():
            c = oracles.CATALOG.get(cid)
            self.assertEqual(len(c.self_sha), 64)
            self.assertEqual(c.oracle_revision, 1, f"{cid} rev")

    def test_mutation_is_rejected_on_next_access(self):
        cat = oracles.CATALOG
        case = cat.get("S2.do_not_use.bad_case")
        original = case.oracle_revision
        try:
            object.__setattr__(case, "oracle_revision", 999)
            with self.assertRaises(ValueError) as cm:
                cat.get("S2.do_not_use.bad_case")
            self.assertIn("identity mismatch", str(cm.exception))
        finally:
            object.__setattr__(case, "oracle_revision", original)

    def test_good_case_has_no_expected_findings(self):
        good = oracles.CATALOG.get("S2.do_not_use.good_case")
        self.assertEqual(good.expected_findings, ())
        # And has forbidden findings so false positives still fail.
        self.assertGreater(len(good.forbidden_findings), 0)

    def test_bad_case_has_expected_decision_block(self):
        for cid in oracles.CATALOG.ids():
            case = oracles.CATALOG.get(cid)
            if case.polarity == "bad":
                self.assertEqual(
                    case.expected_decision,
                    "block",
                    f"{cid}: bad case must expect block",
                )
                self.assertGreater(
                    len(case.expected_findings),
                    0,
                    f"{cid}: bad case must enumerate expected findings",
                )

    def test_bad_case_lists_forbidden_side_effects(self):
        for cid in oracles.CATALOG.ids():
            case = oracles.CATALOG.get(cid)
            if case.polarity == "bad":
                self.assertGreater(
                    len(case.forbidden_side_effects),
                    0,
                    f"{cid}: bad case must list forbidden side effects",
                )


class OracleFaultInjectorSeparationTest(unittest.TestCase):
    """G04: the oracle module cannot import a fault injector.

    `fault_injector_ref` is a STRING name, not an importable object.
    Allowing the oracle to call a fault injector lets a sloppy SUT
    change the oracle's expectation at the moment the fault is applied.
    """

    def test_oracle_module_does_not_import_fault_injectors(self):
        """The oracle module must not import or reference any fault
        injector in a way that could execute it. The oracle is pure
        data; fault injection is a test-time concern."""
        import ast

        src = (_REPO / "agent" / "contracts" / "oracles.py").read_text()
        tree = ast.parse(src)
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    if "fault_injector" in n.name:
                        bad.append(n.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if "fault_injector" in mod:
                    bad.append(mod)
        self.assertEqual(
            bad,
            [],
            msg=f"oracles.py must not import fault injectors; got {bad!r}",
        )
        # Also forbid callable fields on the frozen dataclasses.
        self.assertNotIn("Callable", src, "oracle fields must not carry callables")

    def test_fault_injector_ref_is_string_only(self):
        for cid in oracles.CATALOG.ids():
            case = oracles.CATALOG.get(cid)
            if case.fault_injector_ref is not None:
                self.assertIsInstance(case.fault_injector_ref, str)


class OracleCatalogRevisionTest(unittest.TestCase):
    def test_module_level_revision_is_positive_int(self):
        self.assertIsInstance(oracles.ORACLE_CATALOG_REVISION, int)
        self.assertGreaterEqual(oracles.ORACLE_CATALOG_REVISION, 1)

    def test_reimport_gives_same_catalog_identity(self):
        before = sorted((c, oracles.CATALOG.get(c).self_sha) for c in oracles.CATALOG.ids())
        importlib.reload(oracles)
        after = sorted((c, oracles.CATALOG.get(c).self_sha) for c in oracles.CATALOG.ids())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
