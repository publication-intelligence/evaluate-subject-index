from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCHEMAS = ROOT / "references" / "schemas"
sys.path.insert(0, str(SCRIPTS))

from heading_access_provenance import (  # noqa: E402
    HeadingAccessProvenanceError,
    build_structure_causal_projection,
    causal_provenance_by_node,
    validate_causal_projection_source,
    validate_heading_access_provenance,
)
from item_grade_v8_cli import build_v8_assessments  # noqa: E402


def finding(
    finding_id: str,
    kind: str,
    source_id: str,
    evidence_id: str,
    reason_code: str,
) -> dict:
    return {
        "finding_id": finding_id,
        "kind": kind,
        "source_ids": [source_id],
        "reason_codes": [reason_code],
        "severity": "minor",
        "evidence_ids": [evidence_id],
        "summary": f"{kind} is evidenced by {source_id}.",
    }


def structure(findings: list[dict] | None = None) -> dict:
    return {
        "schema_version": "structure-audit-v6",
        "evaluation_id": "EVAL-1",
        "candidate_sha256": "a" * 64,
        "node_judgments": [
            {
                "node_id": "NODE-1",
                "evidence_ids": ["EVID-NODE"],
                "component_judgments": {
                    "heading_access_architecture": {
                        "status": "minor_issues",
                        "summary": "Generic summary cannot stand alone.",
                        "evidence_ids": ["EVID-NODE"],
                        "causal_findings": list(findings or []),
                    }
                },
            }
        ],
        "cross_reference_judgments": [],
        "v7_architecture_review_decisions": [],
        "v5_scoring_context": {"defects": []},
    }


LOCATORS = [
    {
        "judgments": [
            {
                "locator_id": "LOC-1",
                "path_id": "PATH-1",
                "error_codes": ["HED"],
                "severity": "minor",
                "evidence_ids": ["EVID-LOC"],
            }
        ]
    }
]

MISSING = [
    {
        "subject_judgments": [
            {
                "subject_id": "SUBJ-1",
                "matched_path_ids": ["PATH-1"],
                "error_codes": ["COV"],
                "severity": "minor",
                "evidence_ids": ["EVID-SUBJ"],
            }
        ],
        "reader_task_results": [],
        "treatment_judgments": [],
    }
]


class HeadingAccessProvenanceTests(unittest.TestCase):
    def test_schema_rejects_generic_only_adverse_component(self) -> None:
        schema = json.loads((SCHEMAS / "structure-audit-v6.schema.json").read_text())
        resolver = jsonschema.RefResolver.from_schema(schema)
        validator = jsonschema.Draft202012Validator(
            schema["$defs"]["headingAccessComponent"], resolver=resolver
        )
        component = structure()["node_judgments"][0]["component_judgments"][
            "heading_access_architecture"
        ]
        self.assertFalse(validator.is_valid(component))

    def test_semantics_reject_generic_only_adverse_component(self) -> None:
        with self.assertRaisesRegex(
            HeadingAccessProvenanceError, "generic_only_adverse_heading_access"
        ):
            validate_heading_access_provenance(structure(), LOCATORS, MISSING)

    def test_overlap_is_preserved_without_guessing_a_primary_cause(self) -> None:
        causes = [
            finding("HAF-FIT", "heading_fit", "LOC-1", "EVID-LOC", "HED"),
            finding(
                "HAF-ACCESS",
                "benchmark_access",
                "SUBJ-1",
                "EVID-SUBJ",
                "COV",
            ),
        ]
        document = structure(causes)
        validate_heading_access_provenance(document, LOCATORS, MISSING)
        projected = causal_provenance_by_node(document)
        self.assertEqual(["HAF-FIT", "HAF-ACCESS"], [item["finding_id"] for item in projected[0]["causal_findings"]])
        self.assertNotIn("primary_finding_id", projected[0])

    def test_referenced_source_and_evidence_ids_must_exist(self) -> None:
        cause = finding("HAF-FIT", "heading_fit", "LOC-MISSING", "EVID-LOC", "HED")
        with self.assertRaisesRegex(
            HeadingAccessProvenanceError, "unknown_heading_access_source_id"
        ):
            validate_heading_access_provenance(structure([cause]), LOCATORS, MISSING)

        cause = finding("HAF-FIT", "heading_fit", "LOC-1", "EVID-MISSING", "HED")
        with self.assertRaisesRegex(
            HeadingAccessProvenanceError, "unknown_heading_access_evidence_id"
        ):
            validate_heading_access_provenance(structure([cause]), LOCATORS, MISSING)

    def test_primary_must_name_a_local_finding_with_explicit_basis(self) -> None:
        document = structure(
            [finding("HAF-FIT", "heading_fit", "LOC-1", "EVID-LOC", "HED")]
        )
        component = document["node_judgments"][0]["component_judgments"][
            "heading_access_architecture"
        ]
        component["primary_finding_id"] = "HAF-OTHER"
        component["primary_basis"] = {
            "basis": "deterministic_rule",
            "basis_id": "RULE-1",
        }
        with self.assertRaisesRegex(
            HeadingAccessProvenanceError, "heading_access_primary_finding_mismatch"
        ):
            validate_heading_access_provenance(document, LOCATORS, MISSING)

    def test_item_projection_carries_node_findings_without_score_input(self) -> None:
        cause = finding(
            "HAF-ARCH",
            "confirmed_subdivision_architecture",
            "NODE-1",
            "EVID-NODE",
            "SUB",
        )
        document = structure([cause])
        grade = {
            "score": 70,
            "rating": 3.5,
            "band": "mixed",
            "color_token": "grade_mixed",
            "status": "needs_review",
        }
        base = {
            "schema_version": "subject-index-item-assessments-v3",
            "evaluation_id": "EVAL-1",
            "evidence_identity": {},
            "locator_assessments": [],
            "path_assessments": [],
            "heading_node_assessments": [
                {"node_id": "NODE-1", "grade": grade, "popover": {"grade": grade}}
            ],
            "cross_reference_assessments": [],
            "source_subject_assessments": [],
        }
        calculation = {
            "schema_version": "subject-index-dimension-calculations-v5",
            "evaluation_id": "EVAL-1",
            "evidence_identity": {},
            "dimensions": [
                {
                    "dimension_id": "page_reference_reliability",
                    "reliability_provenance": {
                        "locator_utility_assignments": [],
                        "counts_by_treatment_tier": {},
                        "counts_by_fit_tier": {},
                        "counts_by_diagnostic_credit_value": {},
                        "counts_by_rating_credit_value": {},
                    },
                }
            ],
        }
        review = {
            "schema_version": "subject-index-structure-locator-review-v1",
            "review_id": "STRUCTREV-AAAAAAAAAAAA",
            "review_sha256": "a" * 64,
            "path_reviews": [],
        }
        projected = build_v8_assessments(base, calculation, review, document)
        self.assertEqual(
            [cause], projected["heading_node_assessments"][0]["heading_access_causal_findings"]
        )
        self.assertEqual([cause], projected["heading_access_causal_provenance"][0]["causal_findings"])
        self.assertFalse(
            projected["explanation_contract"]["causal_provenance_used_in_scoring"]
        )

    def test_frozen_v5_audit_can_receive_a_score_free_projection(self) -> None:
        cause = finding(
            "HAF-ARCH",
            "confirmed_subdivision_architecture",
            "NODE-1",
            "EVID-NODE",
            "SUB",
        )
        frozen = structure([])
        frozen["schema_version"] = "structure-audit-v5"
        component = frozen["node_judgments"][0]["component_judgments"][
            "heading_access_architecture"
        ]
        component.pop("causal_findings")
        frozen["unchanged_scoring_marker"] = {"rating": "3.5"}
        projection = {
            "evaluation_id": frozen.get("evaluation_id"),
            "candidate_sha256": frozen.get("candidate_sha256"),
            "node_causal_provenance": [
                {"node_id": "NODE-1", "status": "minor_issues", "causal_findings": [cause]}
            ],
        }
        projected = build_structure_causal_projection(frozen, projection)
        self.assertEqual("structure-audit-v5", frozen["schema_version"])
        self.assertNotIn("causal_findings", component)
        self.assertEqual("structure-audit-v6", projected["schema_version"])
        self.assertEqual(
            frozen["unchanged_scoring_marker"], projected["unchanged_scoring_marker"]
        )
        self.assertEqual(
            "minor_issues",
            projected["node_judgments"][0]["component_judgments"][
                "heading_access_architecture"
            ]["status"],
        )
        projected["causal_projection"] = {
            "source_schema_version": "structure-audit-v5"
        }
        validate_causal_projection_source(projected, frozen)
        projected["unchanged_scoring_marker"] = {"rating": "4"}
        with self.assertRaisesRegex(
            HeadingAccessProvenanceError, "causal_projection_changed_scoring_fields"
        ):
            validate_causal_projection_source(projected, frozen)


if __name__ == "__main__":
    unittest.main()
