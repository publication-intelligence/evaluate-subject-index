from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dimension_score_v8_cli as v8  # noqa: E402
from policy_cli import CRITICAL_GATES  # noqa: E402


def defect(defect_id: str, kind: str, affected_item_id: str, *, code: str = "XRF") -> dict:
    return {
        "defect_id": defect_id,
        "code": code,
        "defect_kind": kind,
        "severity": "major",
        "severity_basis": "blocked_retrieval",
        "retrieval_consequence": "blocks",
        "dimension_owner": "findability_navigation",
        "affected_item_ids": [affected_item_id],
    }


def gate_outcomes(*, nodes: list[dict], reference_ids: list[str], defects: list[dict]) -> dict[str, dict]:
    policy = {
        "audit_design": {"uninspectable_locator_rate_tolerance": 0.01},
        "critical_gates": [
            {"gate_id": gate_id, "description": description}
            for gate_id, description in CRITICAL_GATES
        ],
    }
    structure = {
        "candidate_denominator": {"nodes": nodes, "cross_reference_ids": reference_ids},
        "defects": defects,
        "full_scope_attestation": {"complete": True},
    }
    calculation = {
        "dimensions": [{
            "dimension_id": "page_reference_reliability",
            "reliability_provenance": {
                "original_locator_denominator": 1,
                "uninspectable_locator_count": 0,
            },
        }],
    }
    return {
        item["gate_id"]: item
        for item in v8._critical_gate_outcomes(policy, structure, calculation)
    }


class CriticalGateTests(unittest.TestCase):
    def test_depth_gate_uses_actual_heading_depth_not_hed_defect_severity(self) -> None:
        major_first_lookup_defect = defect(
            "DEFECT-HED-FIRST-LOOKUP", "generic", "NODE-002", code="HED"
        )
        shallow = gate_outcomes(
            nodes=[{"node_id": "NODE-002", "heading_path": ["Main", "Sub"]}],
            reference_ids=[],
            defects=[major_first_lookup_defect],
        )
        deep = gate_outcomes(
            nodes=[{"node_id": "NODE-003", "heading_path": ["Main", "Sub", "Third"]}],
            reference_ids=[],
            defects=[],
        )

        self.assertNotIn("GATE-DEPTH", shallow)
        self.assertNotIn("GATE-DEPTH", deep)

    def test_cross_reference_gate_excludes_missing_warranted_route(self) -> None:
        outcomes = gate_outcomes(
            nodes=[{"node_id": "NODE-001", "heading_path": ["Main"]}],
            reference_ids=["XREF-001"],
            defects=[defect("DEFECT-XRF-MISSING-ROUTE", "misleading_access_route", "TASK-001")],
        )

        self.assertFalse(outcomes["GATE-CROSS-REFERENCE"]["triggered"])
        self.assertEqual([], outcomes["GATE-CROSS-REFERENCE"]["defect_ids"])

    def test_cross_reference_gate_keeps_each_typed_existing_reference_failure(self) -> None:
        cases = {
            "unresolved": "unsupported_reference",
            "self-referential": "circular_or_chained_reference",
            "circular": "circular_or_chained_reference",
            "chained": "circular_or_chained_reference",
        }
        for label, kind in cases.items():
            with self.subTest(label=label):
                outcomes = gate_outcomes(
                    nodes=[{"node_id": "NODE-001", "heading_path": ["Main"]}],
                    reference_ids=["XREF-001"],
                    defects=[defect("DEFECT-XRF-001", kind, "XREF-001")],
                )

                self.assertTrue(outcomes["GATE-CROSS-REFERENCE"]["triggered"])
                self.assertEqual(
                    ["DEFECT-XRF-001"],
                    outcomes["GATE-CROSS-REFERENCE"]["defect_ids"],
                )


if __name__ == "__main__":
    unittest.main()
