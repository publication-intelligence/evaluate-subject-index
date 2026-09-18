from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import study_comparison as study
from v10_reference_bindings import validate_document


SHA = "a" * 64
NORMALIZED_SHA = "b" * 64
INVENTORY_SHA = "c" * 64
STRUCTURE_SHA = "d" * 64


def fixture():
    references = [
        ("XREF-ONE", "see", "Alpha", None),
        ("XREF-MULTI", "see also", "Beta", None),
        ("XREF-BROKEN", "see", "Missing", None),
    ]
    candidate = {
        "candidate_sha256": SHA,
        "records": [
            {
                "path_id": path_id,
                "cross_references": [
                    {"reference_id": reference_id, "type": kind, "target": target, "target_path_id": target_path_id}
                    for reference_id, kind, target, target_path_id in references
                ] if path_id == "PATH-SOURCE" else [],
            }
            for path_id in ("PATH-SOURCE", "PATH-ALPHA", "PATH-BETA-1", "PATH-BETA-2")
        ],
    }
    inventory = {
        "candidate_sha256": SHA,
        "paths": [{"path_id": row["path_id"]} for row in candidate["records"]],
        "cross_references": [
            {
                "reference_id": reference_id,
                "reference_type": kind,
                "target_display": target,
                "target_path_id": target_path_id,
            }
            for reference_id, kind, target, target_path_id in references
        ],
    }
    structure = {
        "evaluation_id": "EVAL-ONE",
        "candidate_sha256": SHA,
        "candidate_denominator": {"cross_reference_ids": [row[0] for row in references]},
        "full_scope_attestation": {
            "unlisted_cross_reference_disposition": "supported",
            "pilot_supported_cross_reference_ids": [],
        },
        "cross_reference_judgments": [
            {"reference_id": "XREF-BROKEN", "judgment": "unsupported"}
        ],
        "uncertainties": [],
        "uncertainty_gate_scopes": [],
    }
    bindings = [
        {
            "reference_id": "XREF-ONE",
            "status": "valid_destination",
            "reference_type": "see",
            "target_display": "Alpha",
            "resolved_path_ids": ["PATH-ALPHA"],
            "evidence_ids": ["EVID-ONE"],
            "rationale": "Reviewed against the delivered index.",
        },
        {
            "reference_id": "XREF-MULTI",
            "status": "valid_destination",
            "reference_type": "see also",
            "target_display": "Beta",
            "resolved_path_ids": ["PATH-BETA-1", "PATH-BETA-2"],
            "evidence_ids": ["EVID-MULTI"],
            "rationale": "Both delivered destinations were reviewed.",
        },
    ]
    document = {
        "schema_version": "subject-index-v10-reviewed-cross-reference-bindings-v1",
        "review_id": "XREF-REVIEW-ONE",
        "evaluation_id": "EVAL-ONE",
        "candidate_sha256": SHA,
        "normalized_candidate_sha256": NORMALIZED_SHA,
        "item_inventory_sha256": INVENTORY_SHA,
        "structure_binding": {"path": "structure-audit.json", "sha256": STRUCTURE_SHA},
        "binding_set_sha256": study.digest(bindings),
        "reviewed_at": "2026-09-18T00:00:00Z",
        "reviewed_by": "reviewer-one",
        "authorization_reference": "authorized-review-one",
        "review_confidence": "high",
        "scope_attestation": {
            "destination_sets_complete": True,
            "unresolved_or_ambiguous_bindings_included": False,
        },
        "bindings": bindings,
    }
    return document, candidate, inventory, structure


def validate(document, candidate, inventory, structure):
    return validate_document(
        document,
        evaluation_id="EVAL-ONE",
        candidate_sha256=SHA,
        normalized_candidate_sha256=NORMALIZED_SHA,
        item_inventory_sha256=INVENTORY_SHA,
        candidate=candidate,
        inventory=inventory,
        structure=structure,
        structure_path="structure-audit.json",
        structure_file_sha256=STRUCTURE_SHA,
    )


class ReviewedReferenceBindingTests(unittest.TestCase):
    def test_single_and_multiple_destinations_preserve_the_exact_mapping_set(self):
        document, candidate, inventory, structure = fixture()
        result = validate(document, candidate, inventory, structure)
        self.assertEqual({"XREF-ONE", "XREF-MULTI"}, set(result))
        self.assertEqual(["PATH-ALPHA"], result["XREF-ONE"]["resolved_path_ids"])
        self.assertEqual(["PATH-BETA-1", "PATH-BETA-2"], result["XREF-MULTI"]["resolved_path_ids"])
        self.assertEqual(study.digest(document["bindings"]), document["binding_set_sha256"])

    def test_binding_set_tampering_is_rejected(self):
        document, candidate, inventory, structure = fixture()
        document["bindings"][0]["rationale"] = "Changed after review."
        with self.assertRaisesRegex(ValueError, "hash"):
            validate(document, candidate, inventory, structure)

    def test_type_text_and_nonexistent_path_mismatches_are_rejected(self):
        for field, value, message in (
            ("reference_type", "see also", "type"),
            ("target_display", "Different", "text"),
            ("resolved_path_ids", ["PATH-MISSING"], "nonexistent"),
        ):
            document, candidate, inventory, structure = fixture()
            document["bindings"][0][field] = value
            document["binding_set_sha256"] = study.digest(document["bindings"])
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                validate(document, candidate, inventory, structure)

    def test_duplicates_and_incomplete_sets_fail_closed(self):
        document, candidate, inventory, structure = fixture()
        document["bindings"].append(deepcopy(document["bindings"][0]))
        document["binding_set_sha256"] = study.digest(document["bindings"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate(document, candidate, inventory, structure)

        document, candidate, inventory, structure = fixture()
        document["bindings"].pop()
        document["binding_set_sha256"] = study.digest(document["bindings"])
        with self.assertRaisesRegex(ValueError, "exact complete"):
            validate(document, candidate, inventory, structure)

        document, candidate, inventory, structure = fixture()
        document["scope_attestation"]["destination_sets_complete"] = False
        with self.assertRaisesRegex(ValueError, "Invalid"):
            validate(document, candidate, inventory, structure)

    def test_exception_ledger_and_destination_uncertainty_cannot_be_cleared(self):
        document, candidate, inventory, structure = fixture()
        self.assertNotIn("XREF-BROKEN", validate(document, candidate, inventory, structure))

        document["bindings"].append({
            "reference_id": "XREF-BROKEN",
            "status": "valid_destination",
            "reference_type": "see",
            "target_display": "Missing",
            "resolved_path_ids": ["PATH-ALPHA"],
            "evidence_ids": ["EVID-BROKEN"],
            "rationale": "Must not replace the unsupported exception.",
        })
        document["binding_set_sha256"] = study.digest(document["bindings"])
        with self.assertRaisesRegex(ValueError, "exact complete"):
            validate(document, candidate, inventory, structure)

        document, candidate, inventory, structure = fixture()
        structure["uncertainties"] = [{"uncertainty_id": "UNC-XREF", "affected_item_ids": ["XREF-ONE"]}]
        structure["uncertainty_gate_scopes"] = [{"uncertainty_id": "UNC-XREF", "scope": "cross_reference_destination", "target_ids": ["XREF-ONE"]}]
        with self.assertRaisesRegex(ValueError, "unresolved or ambiguous"):
            validate(document, candidate, inventory, structure)


if __name__ == "__main__":
    unittest.main()
