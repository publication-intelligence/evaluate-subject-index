from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCHEMAS = ROOT / "references" / "schemas"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from structure_audit import (  # noqa: E402
    StructureAuditError,
    id_set_hash,
    materialize_structure_records,
    validate_structure_audit_semantics,
)


SHA = "a" * 64
THRESHOLDS = {
    "long_displayed_locator_string": {"operator": ">", "displayed_locator_count": 6},
    "long_continuous_range": {"operator": ">", "inclusive_range_span": 10},
    "numeric_trigger_is_automatic_defect": False,
}


def component(status: str = "not_measured") -> dict:
    return {"status": status, "summary": status.replace("_", " "), "evidence_ids": []}


def audit(node_count: int = 3, *, mode: str = "full") -> dict:
    node_ids = [f"NODE-{index:05d}" for index in range(1, node_count + 1)]
    reference_ids = ["XREF-00001", "XREF-00002"]
    path_ids = ["PATH-00001"] if node_ids else []
    full = mode == "full"
    return {
        "schema_version": "structure-audit-v5",
        "evaluation_id": "EVAL-NATIVE-STRUCTURE",
        "candidate_sha256": SHA,
        "audit_mode": mode,
        "candidate_denominator": {
            "nodes": [
                {"node_id": node_id, "heading_path": [f"Heading {index}"], "role": "main_heading"}
                for index, node_id in enumerate(node_ids, start=1)
            ],
            "cross_reference_ids": reference_ids,
            "locator_bearing_path_ids": path_ids,
            "node_count": len(node_ids),
            "cross_reference_count": len(reference_ids),
            "locator_bearing_path_count": len(path_ids),
            "node_id_set_sha256": id_set_hash(node_ids),
            "cross_reference_id_set_sha256": id_set_hash(reference_ids),
            "locator_bearing_path_id_set_sha256": id_set_hash(path_ids),
        },
        "full_scope_attestation": {
            "complete": full,
            "all_nodes_reviewed": full,
            "all_cross_references_reviewed": full,
            "all_locator_bearing_paths_checked_for_triggers": full,
            "unlisted_node_disposition": "passes" if full else "not_measured",
            "unlisted_cross_reference_disposition": "supported" if full else "not_measured",
            "pilot_pass_node_ids": [],
            "pilot_supported_cross_reference_ids": [],
            "evidence_ids": ["EVID-SCOPE-0001"],
        },
        "metrics": {
            "page_bearing_paths": len(path_ids),
            "expanded_locators": 0,
            "cross_references": len(reference_ids),
            "total_paths": len(path_ids),
            "total_nodes": len(node_ids),
        },
        "density": {
            "policy_status": "scored",
            "measurement_level": "chapter_or_approved_intellectual_unit",
            "targets": [{}, {}],
            "chapter_measurements": [{"chunk_id": "CHUNK-0001", "indexable_source_words": 1, "locator_bearing_heading_paths": len(path_ids), "locator_occurrences": 0}],
            "maximum_score_contribution": 5,
            "distribution_findings": [],
        },
        "node_judgments": [],
        "cross_reference_judgments": [],
        "locator_architecture": {"thresholds": THRESHOLDS, "triggered_path_ids": [], "triggered_reviews": []},
        "defects": [],
        "strengths": [],
        "uncertainties": [],
        "scoring_context": {
            "candidate_attempt": {"status": "meaningful_attempt", "evidence_ids": []},
            "cross_reference_applicability": {},
            "optional_subject_scoring": [],
            "node_component_applicability": [],
        },
    }


def triggered_review(*, display_count: int = 7, range_span: int = 0, status: str = "reviewed_no_defect") -> dict:
    displays = []
    atomic_ids = []
    if range_span:
        owned = [f"LOC-{index:05d}" for index in range(1, range_span + 1)]
        atomic_ids.extend(owned)
        displays.append({
            "display_id": "DISPLAY-00001", "kind": "range", "range_id": "RANGE-00001",
            "expanded_atomic_locator_ids": owned, "atomic_assignment_count": len(owned),
            "range_endpoints": {"start": {"document_page": 1}, "end": {"document_page": range_span}},
            "inclusive_range_span": range_span,
        })
    else:
        for index in range(1, display_count + 1):
            locator_id = f"LOC-{index:05d}"
            atomic_ids.append(locator_id)
            displays.append({
                "display_id": f"DISPLAY-{index:05d}", "kind": "singleton", "range_id": None,
                "expanded_atomic_locator_ids": [locator_id], "atomic_assignment_count": 1,
                "range_endpoints": None, "inclusive_range_span": None,
            })
    unresolved = status == "not_reviewed"
    return {
        "review_id": "ARCHREV-00001", "path_id": "PATH-00001", "terminal_node_id": "NODE-00001",
        "displayed_locator_count": len(displays), "displayed_locators": displays,
        "expanded_atomic_locator_ids": atomic_ids, "atomic_assignment_count": len(atomic_ids),
        "maximum_range_span": range_span,
        "long_displayed_locator_string_review_trigger": len(displays) > 6,
        "long_continuous_range_review_trigger": range_span > 10,
        "review_status": status,
        "conceptually_distinguishable_treatments": None if unresolved else True,
        "meaningful_subheadings_or_access_routes": None if unresolved else False,
        "material_scanning_or_retrieval_impairment": None if unresolved else False,
        "subdivision_is_conceptual_not_trivial": None if unresolved else False,
        "evidence_ids": [] if unresolved else ["EVID-ARCH-0001"],
        "defect_ids": [],
    }


class NativeStructureAuditTests(unittest.TestCase):
    def test_full_scope_materializes_thousands_of_omitted_passes(self) -> None:
        document = audit(2000)
        validate_structure_audit_semantics(document)
        nodes, references, missing_nodes, missing_references = materialize_structure_records(document)
        self.assertEqual(2000, len(nodes))
        self.assertEqual(2, len(references))
        self.assertEqual(([], []), (missing_nodes, missing_references))
        self.assertEqual([], document["node_judgments"])

    def test_schema_accepts_native_exception_contract(self) -> None:
        document = audit()
        schema = json.loads((SCHEMAS / "structure-audit-v5.schema.json").read_text())
        jsonschema.validate(document, schema)

    def test_denominator_hash_and_count_tampering_fail_closed(self) -> None:
        for field, value in (("node_count", 99), ("node_id_set_sha256", "f" * 64)):
            document = audit()
            document["candidate_denominator"][field] = value
            with self.subTest(field=field), self.assertRaises(StructureAuditError):
                validate_structure_audit_semantics(document)

    def test_all_pass_exception_row_is_forbidden(self) -> None:
        document = audit()
        document["node_judgments"] = [{
            "node_id": "NODE-00001",
            "component_judgments": {
                "conceptual_stance_fidelity": component("passes"),
                "heading_access_architecture": component("passes"),
                "mechanics_consistency": component("passes"),
            },
            "summary": "boilerplate", "confidence": "high", "evidence_ids": [],
        }]
        with self.assertRaisesRegex(StructureAuditError, "exception"):
            validate_structure_audit_semantics(document)

    def test_pilot_keeps_explicit_passes_and_omissions_distinct(self) -> None:
        document = audit(mode="pilot")
        document["full_scope_attestation"]["pilot_pass_node_ids"] = ["NODE-00001"]
        document["full_scope_attestation"]["pilot_supported_cross_reference_ids"] = ["XREF-00001"]
        nodes, references, missing_nodes, missing_references = materialize_structure_records(document)
        self.assertEqual(["NODE-00001"], [item["node_id"] for item in nodes])
        self.assertEqual(["XREF-00001"], [item["reference_id"] for item in references])
        self.assertEqual(["NODE-00002", "NODE-00003"], missing_nodes)
        self.assertEqual(["XREF-00002"], missing_references)

    def test_exact_six_and_ten_are_not_triggers_but_seven_and_eleven_are(self) -> None:
        six = triggered_review(display_count=6)
        ten = triggered_review(display_count=1, range_span=10)
        self.assertFalse(six["long_displayed_locator_string_review_trigger"])
        self.assertFalse(ten["long_continuous_range_review_trigger"])
        for review in (triggered_review(display_count=7), triggered_review(display_count=1, range_span=11)):
            document = audit()
            document["locator_architecture"] |= {"triggered_path_ids": ["PATH-00001"], "triggered_reviews": [review]}
            validate_structure_audit_semantics(document)

    def test_numeric_trigger_can_be_reviewed_without_becoming_defect(self) -> None:
        document = audit()
        review = triggered_review()
        document["locator_architecture"] |= {"triggered_path_ids": ["PATH-00001"], "triggered_reviews": [review]}
        validate_structure_audit_semantics(document)
        self.assertEqual([], document["defects"])

    def test_full_rejects_unreviewed_trigger_and_pilot_propagates_uncertainty(self) -> None:
        full = audit()
        review = triggered_review(status="not_reviewed")
        full["locator_architecture"] |= {"triggered_path_ids": ["PATH-00001"], "triggered_reviews": [review]}
        with self.assertRaisesRegex(StructureAuditError, "Full mode"):
            validate_structure_audit_semantics(full)
        pilot = audit(mode="pilot")
        pilot["locator_architecture"] |= {"triggered_path_ids": ["PATH-00001"], "triggered_reviews": [copy.deepcopy(review)]}
        _, _, missing_nodes, _ = materialize_structure_records(pilot)
        self.assertIn("NODE-00001", missing_nodes)

    def test_display_to_atomic_binding_tamper_fails_closed(self) -> None:
        document = audit()
        review = triggered_review()
        review["expanded_atomic_locator_ids"] = list(reversed(review["expanded_atomic_locator_ids"]))
        document["locator_architecture"] |= {"triggered_path_ids": ["PATH-00001"], "triggered_reviews": [review]}
        with self.assertRaisesRegex(StructureAuditError, "ownership"):
            validate_structure_audit_semantics(document)


if __name__ == "__main__":
    unittest.main()
