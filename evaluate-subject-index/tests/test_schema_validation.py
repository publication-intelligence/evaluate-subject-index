from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_validation import schema_errors


class SharedSchemaValidationTests(unittest.TestCase):
    def test_v8_identity_contracts_reject_retired_identities(self) -> None:
        cases = [
            ("dimension-calculations-v5.schema.json", "subject-index-dimension-calculations-v5", "subject-index-dimension-calculations-v4"),
            ("item-assessments-v6.schema.json", "subject-index-item-assessments-v6", "subject-index-item-assessments-v5"),
            ("evaluation-result-v10.schema.json", "subject-index-evaluation-result-v10", "subject-index-evaluation-result-v9"),
            ("evaluation-state.schema.json", "subject-index-evaluation-state-v6", "subject-index-evaluation-state-v5"),
            ("web-report-v8.schema.json", "subject-index-web-report-v8", "subject-index-web-report-v7"),
            ("evaluation-policy-v4.schema.json", "subject-index-evaluation-policy-v4", "subject-index-evaluation-policy-v3"),
            ("dimension-calculation-input.schema.json", "subject-index-dimension-calculation-input-v2", "subject-index-dimension-calculation-input-v1"),
            ("v8-projection-metadata-v1.schema.json", "subject-index-v8-projection-metadata-v1", "subject-index-v7-projection-metadata-v2"),
            ("v8-locator-fit-preflight.schema.json", "subject-index-v8-locator-fit-preflight-v1", "subject-index-v7-locator-fit-preflight-v1"),
        ]
        schema_root = ROOT / "references" / "schemas"
        for filename, current, retired in cases:
            with self.subTest(filename=filename):
                schema = json.loads((schema_root / filename).read_text())
                validator = Draft202012Validator(schema["properties"]["schema_version"])
                self.assertTrue(validator.is_valid(current))
                self.assertFalse(validator.is_valid(retired))

    def test_v8_native_result_and_report_have_no_migration_requirement(self) -> None:
        schema_root = ROOT / "references" / "schemas"
        result_schema = json.loads((schema_root / "evaluation-result-v10.schema.json").read_text())
        report_schema = json.loads((schema_root / "web-report-v8.schema.json").read_text())
        self.assertNotIn("score_migration", result_schema["required"])
        self.assertNotIn("score_migration", result_schema["properties"])
        self.assertNotIn("migration_comparison", report_schema["required"])
        self.assertNotIn("migration_comparison", report_schema["properties"])

    def test_current_worker_schemas_do_not_publish_redundant_provenance_contracts(self) -> None:
        schema_root = ROOT / "references" / "schemas"
        policy = json.loads((schema_root / "evaluation-policy-v4.schema.json").read_text())
        locator = json.loads((schema_root / "locator-audit-v2.schema.json").read_text())
        missing = json.loads((schema_root / "missing-access-audit.schema.json").read_text())
        structure = json.loads((schema_root / "structure-audit-v5.schema.json").read_text())
        self.assertEqual(["id"], policy["properties"]["policy_profile"]["required"])
        self.assertNotIn("provenance", locator["properties"])
        self.assertNotIn("provenance", missing["properties"])
        self.assertNotIn("provenance", structure["required"])
        self.assertNotIn("item_inventory_sha256", structure["required"])

    def test_locator_audit_nested_shape_is_owned_by_schema(self) -> None:
        audit = {
            "schema_version": "locator-audit-v2",
            "evaluation_id": "EVAL-1",
            "candidate_sha256": "0" * 64,
            "chunk_id": "CHUNK-001",
            "expected_locator_ids": ["LOC-1"],
            "judgments": [{
                "locator_id": "LOC-1",
                "path_id": "PATH-1",
                "complete_heading_path": ["Subject"],
                "document_page": 1,
                "source_page_label": "1",
                "source_scope_status": "indexable",
                "treatment_class": "mixed",
                "judgment": "supported",
                "complete_path_fit": "exact_fit",
                "evidence_summary": "Supported with meaningful but mixed treatment.",
                "fit_rationale": "The complete heading path fits the independently useful fact exactly.",
                "evidence_ids": ["EVID-1"],
                "confidence": "high",
                "error_codes": [],
                "severity": "none",
            }],
            "completion": {"expected": 1, "judged": 1, "unique": True, "complete": True},
        }
        self.assertEqual(schema_errors(audit, "locator-audit-v2.schema.json"), [])
        del audit["judgments"][0]["evidence_ids"]
        self.assertTrue(any("evidence_ids" in error for error in schema_errors(audit, "locator-audit-v2.schema.json")))

    def test_current_structure_and_outputs_do_not_reference_cutover_schemas(self) -> None:
        schema_root = ROOT / "references" / "schemas"
        removed = {
            "structure-audit-v4.schema.json",
            "structure-locator-review-v1.schema.json",
            "v5-migration-supplement.schema.json",
            "score-migration.schema.json",
            "evaluation-result-v6.schema.json",
            "dimension-calculations.schema.json",
        }
        self.assertFalse(any((schema_root / name).exists() for name in removed))
        current = "\n".join(
            (schema_root / name).read_text()
            for name in (
                "structure-audit-v5.schema.json",
                "dimension-calculations-v5.schema.json",
                "item-assessments-v6.schema.json",
                "evaluation-result-v10.schema.json",
                "web-report-v8.schema.json",
                "v8-projection-metadata-v1.schema.json",
            )
        )
        for forbidden in ("structure-audit-v4", "structure-locator-review", "migration-supplement", "score-migration", "evaluation-result-v6"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, current)

    def test_relative_schema_reference_validates_chunk_plan(self) -> None:
        manifest = {
            "schema_version": "chunk-manifest-v1",
            "document_page_basis": "one_based_inclusive",
            "page_map_sha256": "0" * 64,
            "user_approved": True,
            "require_full_scope_coverage": True,
            "chunks": [{
                "chunk_id": "CHUNK-001",
                "title": "Chapter 1",
                "source_units": ["Chapter 1"],
                "owned_document_page_ranges": [[1, 2]],
                "context_document_page_ranges": [],
                "packet_order": 1,
            }],
            "validation": {"owned_pages_unique": True, "scope_coverage_complete": True},
            "chunk_manifest_sha256": "0" * 64,
        }
        self.assertEqual(schema_errors(manifest, "chunk-manifest.schema.json"), [])
        manifest["chunks"][0]["packet_order"] = 0
        self.assertTrue(any("packet_order" in error for error in schema_errors(manifest, "chunk-manifest.schema.json")))


if __name__ == "__main__":
    unittest.main()
