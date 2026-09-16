from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import item_grade_v8_cli as item_grades  # noqa: E402
from locator_utility import assign_locator_utility  # noqa: E402
import web_projection  # noqa: E402


def target(record: str, path: str, node: str) -> dict[str, str]:
    return {"record_id": record, "path_id": path, "node_id": node}


def assessment(identity: str, *, judgment: str | None = None) -> dict:
    grade = {
        "score": 100,
        "rating": 5,
        "band": "excellent",
        "color_token": "grade_excellent",
        "status": "passes",
    }
    value = {
        "grade": grade,
        "grade_scope": "synthetic_item",
        "confidence": "high",
        "evidence_ids": [f"EVID-{identity}"],
        "summary": "Synthetic assessment.",
        "popover": {
            "title": "Synthetic assessment",
            "summary": "Synthetic assessment.",
            "grade": grade,
            "grade_scope": "synthetic_item",
            "confidence": "high",
            "factors": [],
            "evidence_ids": [f"EVID-{identity}"],
            "navigation": {},
        },
    }
    if judgment is not None:
        value["judgment"] = judgment
    return value


def locator_assessment() -> dict:
    value = {
        "locator_id": "LOC-001", "path_id": "PATH-SOURCE", "source_page_label": "7",
        "document_page": 9, "mapping_status": "resolved",
        **assessment("LOC-001", judgment="supported"),
    }
    assignment = assign_locator_utility({
        "locator_id": "LOC-001", "judgment": "supported", "treatment_class": "substantive",
        "complete_path_fit": "exact_fit", "source_scope_status": "indexable",
        "error_codes": [], "severity": "none",
    }).as_dict()
    explanation = item_grades._locator_explanation(
        value, assignment, {"evidence_summary": "Synthetic assessment."}
    )
    value.update({
        "dimension_reliability_credit": assignment["rating_credit"],
        "locator_utility": assignment,
        "locator_explanation": explanation,
    })
    value["popover"]["factors"] = item_grades._locator_factor(assignment, explanation)
    return value


class PublicScoringProjectionTests(unittest.TestCase):
    def test_scorecard_preserves_exact_values_with_adapter_aliases(self) -> None:
        canonical = [{
            "dimension_id": "editorial_selectivity",
            "dimension_percentage": "63.33333333333333333333333333",
            "weight": 15,
            "weighted_contribution": "9.499999999999999999999999999",
            "formula_id": "subject-index-dimension-calculation-v7:editorial_selectivity",
        }]

        projected = web_projection.scorecard_with_compatibility_aliases(canonical)

        self.assertTrue(canonical[0].items() <= projected[0].items())
        self.assertEqual(float(canonical[0]["dimension_percentage"]) / 20, projected[0]["rating"])
        self.assertEqual(float(canonical[0]["weighted_contribution"]), projected[0]["awarded_points"])
        self.assertEqual(canonical[0]["weight"], projected[0]["maximum_points"])

    def test_dimension_denominators_preserve_optional_subject_exclusions(self) -> None:
        denominator = {
            "component_id": "priority_weighted_subject_access",
            "original": 90,
            "applicable": 4,
            "measured": 4,
            "excluded": 86,
            "uninspectable": 0,
            "not_measured": 0,
            "exclusion_reasons": {"optional_not_frozen_as_scored": 86},
            "measurement_coverage": "1",
            "small_denominator_exception": False,
            "genuinely_inapplicable": False,
            "zero_due_to_non_attempt": False,
            "defined_zero_rule": None,
            "provisionally_scoreable": True,
        }
        calculation = {"dimensions": [{
            "dimension_id": "meaningful_coverage",
            "denominators": {"components": [denominator]},
        }]}

        disclosures = web_projection.dimension_denominator_disclosures(calculation)

        self.assertEqual([{
            "dimension_id": "meaningful_coverage",
            "components": [denominator],
        }], disclosures)


class CrossReferenceResolverTests(unittest.TestCase):
    def test_existing_em_dash_resolution_is_preserved(self) -> None:
        destination = target("REC-001", "PATH-001", "NODE-001")
        index = {web_projection._canonical_target("Parent—Child"): [destination]}

        self.assertEqual(
            [destination],
            web_projection._resolved_targets(" parent – child ", index),
        )

    def test_see_under_resolves_only_the_first_colon_as_hierarchy(self) -> None:
        destination = target("REC-001", "PATH-001", "NODE-001")
        index = {
            web_projection._canonical_target(
                "Parent—Second Directory: executive supremacy and electoral control"
            ): [destination]
        }

        self.assertEqual(
            [destination],
            web_projection._resolved_targets(
                "under Parent: Second Directory: executive supremacy and electoral control",
                index,
            ),
        )

    def test_bare_colon_is_not_inferred_as_hierarchy(self) -> None:
        destination = target("REC-001", "PATH-001", "NODE-001")
        plain = target("REC-PLAIN", "PATH-PLAIN", "NODE-PLAIN")
        index = {
            web_projection._canonical_target("Parent—Child"): [destination],
            web_projection._canonical_target("Plain"): [plain],
        }

        self.assertEqual([], web_projection._resolved_targets("Parent: Child", index))
        self.assertEqual([], web_projection._resolved_targets("Plain; Parent: Child", index))

    def test_see_under_context_applies_to_the_full_semicolon_list(self) -> None:
        first = target("REC-001", "PATH-001", "NODE-001")
        second = target("REC-002", "PATH-002", "NODE-002")
        third = target("REC-003", "PATH-003", "NODE-003")
        index = {
            web_projection._canonical_target("Parent—Child one"): [first],
            web_projection._canonical_target("Parent—Child two: detail"): [second],
            web_projection._canonical_target("Parent—Child three (and four)"): [third],
        }

        self.assertEqual(
            [first, second, third],
            web_projection._resolved_targets(
                "under Parent: Child one; Parent: Child two: detail; "
                "Parent: Child three (and four)",
                index,
            ),
        )

    def test_multiple_targets_preserve_target_and_record_order(self) -> None:
        first = target("REC-001", "PATH-001", "NODE-001")
        second = target("REC-002", "PATH-002", "NODE-002")
        index = {
            web_projection._canonical_target("Parent—Child"): [first],
            web_projection._canonical_target("Other"): [second],
        }

        self.assertEqual(
            [first, second],
            web_projection._resolved_targets("under Parent: Child; Other", index),
        )

    def test_records_sharing_a_node_are_all_resolved(self) -> None:
        container = target("REC-CONTAINER", "PATH-CONTAINER", "NODE-SHARED")
        cross_reference = target("REC-XREF", "PATH-XREF", "NODE-SHARED")
        index = {
            web_projection._canonical_target("Shared heading"): [
                container,
                cross_reference,
            ]
        }

        self.assertEqual(
            [container, cross_reference],
            web_projection._resolved_targets("Shared heading", index),
        )

    def test_conflicting_or_missing_destinations_remain_unresolved(self) -> None:
        index = {
            web_projection._canonical_target("Ambiguous"): [
                target("REC-001", "PATH-001", "NODE-001"),
                target("REC-002", "PATH-002", "NODE-002"),
            ],
            web_projection._canonical_target("Present"): [
                target("REC-003", "PATH-003", "NODE-003")
            ],
        }

        self.assertEqual([], web_projection._resolved_targets("Ambiguous", index))
        self.assertEqual([], web_projection._resolved_targets("Missing", index))
        self.assertEqual([], web_projection._resolved_targets("Present; Missing", index))


class IndexRecordProjectionTests(unittest.TestCase):
    def test_projection_preserves_literal_target_and_shared_record_identities(self) -> None:
        grade = {
            "score": 100,
            "rating": 5,
            "band": "excellent",
            "color_token": "grade_excellent",
            "status": "passes",
        }
        candidate = {
            "records": [
                self.record("REC-PARENT", "PATH-PARENT", ["Parent"]),
                self.record("REC-DEST-1", "PATH-DEST-1", ["Parent", "Child"]),
                self.record("REC-DEST-2", "PATH-DEST-2", ["Parent", "Child"]),
                self.record(
                    "REC-SOURCE",
                    "PATH-SOURCE",
                    ["Source"],
                    references=[{
                        "reference_id": "XREF-001",
                        "type": "see",
                        "target": "under Parent: Child",
                    }],
                ),
            ]
        }
        inventory = {
            "paths": [
                {"path_id": "PATH-PARENT", "node_ids": ["NODE-PARENT"]},
                {"path_id": "PATH-DEST-1", "node_ids": ["NODE-PARENT", "NODE-CHILD"]},
                {"path_id": "PATH-DEST-2", "node_ids": ["NODE-PARENT", "NODE-CHILD"]},
                {"path_id": "PATH-SOURCE", "node_ids": ["NODE-SOURCE"]},
            ],
            "heading_nodes": [
                {"node_id": "NODE-PARENT", "parent_node_id": None},
                {"node_id": "NODE-CHILD", "parent_node_id": "NODE-PARENT"},
                {"node_id": "NODE-SOURCE", "parent_node_id": None},
            ],
        }
        items = {
            "locator_assessments": [],
            "path_assessments": [
                {"path_id": row["path_id"], "grade": grade}
                for row in inventory["paths"]
            ],
            "heading_node_assessments": [
                {"node_id": row["node_id"], "grade": grade}
                for row in inventory["heading_nodes"]
            ],
            "cross_reference_assessments": [{"reference_id": "XREF-001", "judgment": "supported", "grade": grade}],
        }

        projected = web_projection.build_index_records(candidate, inventory, items)
        reference = projected["items"][-1]["cross_references"][0]

        self.assertEqual("under Parent: Child", reference["target_display"])
        self.assertEqual("resolved", reference["resolution"]["status"])
        self.assertEqual(
            ["REC-DEST-1", "REC-DEST-2"],
            [row["record_id"] for row in reference["resolution"]["targets"]],
        )
        self.assertEqual(grade, reference["assessment"]["grade"])

    def test_index_records_match_full_generic_consumer_contract(self) -> None:
        candidate = {"records": [
            self.record("REC-DEST", "PATH-DEST", ["Destination"]),
            {
                **self.record(
                    "REC-SOURCE",
                    "PATH-SOURCE",
                    ["Source", "Detail"],
                    references=[{
                        "reference_id": "XREF-001",
                        "type": "see",
                        "target": "Destination",
                    }],
                ),
                "record_type": "mixed",
                "locator_displays": [{
                    "display_id": "DISPLAY-001",
                    "displayed_locator": "7",
                    "kind": "point",
                    "mapping_status": "resolved",
                    "locator_ids": ["LOC-001"],
                }],
                "locator_assignments": [{
                    "locator_id": "LOC-001",
                    "source_page_label": "7",
                    "document_page": 9,
                    "mapping_status": "resolved",
                }],
            },
        ]}
        inventory = {
            "paths": [
                {"path_id": "PATH-DEST", "node_ids": ["NODE-DEST"]},
                {"path_id": "PATH-SOURCE", "node_ids": ["NODE-SOURCE", "NODE-DETAIL"]},
            ],
            "heading_nodes": [
                {"node_id": "NODE-DEST", "parent_node_id": None},
                {"node_id": "NODE-SOURCE", "parent_node_id": None},
                {"node_id": "NODE-DETAIL", "parent_node_id": "NODE-SOURCE"},
            ],
        }
        items = {
            "locator_assessments": [locator_assessment()],
            "path_assessments": [
                {"path_id": row["path_id"], **assessment(row["path_id"])}
                for row in inventory["paths"]
            ],
            "heading_node_assessments": [
                {"node_id": row["node_id"], **assessment(row["node_id"])}
                for row in inventory["heading_nodes"]
            ],
            "cross_reference_assessments": [{
                "reference_id": "XREF-001",
                **assessment("XREF-001", judgment="supported"),
            }],
        }

        projected = web_projection.build_index_records(candidate, inventory, items)
        source = projected["items"][1]
        locator = source["displayed_locators"][0]["atomic_locators"][0]
        reference = source["cross_references"][0]

        self.assertEqual([0, 1], [row["delivered_order"] for row in projected["items"]])
        self.assertEqual(source["heading_path"], source["delivered_heading_path"])
        self.assertEqual(source["heading_path"], source["display_heading_path"])
        self.assertEqual([], source["corrected_heading_path"])
        self.assertIsNone(source["adjusted_heading_assessment"])
        self.assertIsNone(locator["adjusted_assessment"])
        self.assertEqual("7", locator["source_page_label"])
        self.assertEqual(9, locator["document_page"])
        self.assertEqual("grade_excellent", locator["assessment"]["grade"]["color_token"])
        self.assertEqual("supported", reference["adjusted_judgment"])
        self.assertIsNone(reference["adjusted_assessment"])
        self.assertEqual(reference["resolution"], reference["adjusted_resolution"])
        self.assertEqual(
            [{"record_id": "REC-DEST", "path_id": "PATH-DEST", "node_id": "NODE-DEST"}],
            reference["adjusted_resolution"]["targets"],
        )
        self.assertEqual(
            {"record_id": "REC-SOURCE", "path_id": "PATH-SOURCE", "node_id": "NODE-DETAIL", "heading_path": ["Source", "Detail"]},
            reference["source"],
        )
        for value in (source["heading_assessment"], source["path_assessment"], locator["assessment"], reference["assessment"]):
            self.assertTrue({"grade", "summary", "popover"} <= set(value))
            self.assertTrue({"title", "summary", "grade", "factors"} <= set(value["popover"]))

    @staticmethod
    def record(
        record_id: str,
        path_id: str,
        heading_path: list[str],
        *,
        references: list[dict[str, str]] | None = None,
    ) -> dict:
        references = references or []
        return {
            "record_id": record_id,
            "record_type": "cross_reference" if references else "container",
            "path_id": path_id,
            "heading_path": heading_path,
            "original_displayed_form": heading_path[-1],
            "locator_displays": [],
            "locator_assignments": [],
            "cross_references": references,
        }


if __name__ == "__main__":
    unittest.main()
