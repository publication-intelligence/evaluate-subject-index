from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dimension_score_v8_cli as v8  # noqa: E402
import parallel_candidate_audit_cli as audits  # noqa: E402
import policy_cli  # noqa: E402
import scoring_core as scoring  # noqa: E402


SHA = {
    key: character * 64
    for key, character in {
        "source": "1",
        "policy": "2",
        "page_map": "3",
        "manifest": "4",
        "benchmark": "5",
        "candidate": "6",
    }.items()
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PolicyIdentityTests(unittest.TestCase):
    def policy_input(self) -> dict:
        return {
            "policy_id": "POLICY-TEST",
            "source_scope": {
                "source_sha256": SHA["source"],
                "document_page_span": [1, 2],
                "page_map_sha256": SHA["page_map"],
                "chunk_manifest_sha256": SHA["manifest"],
                "availability": {},
            },
            "audience": {
                "label": "general",
                "basis": "inferred",
                "confidence": "medium",
                "rationale": "Synthetic regression policy.",
            },
            "audit_design": {"mode": "full", "candidate_blindness": "required"},
            "deviations": [],
        }

    def test_markdown_wording_hash_is_ignored_noncontract_metadata(self) -> None:
        policy = policy_cli.build_policy(self.policy_input())
        policy["policy_profile"]["standard_policy_sha256"] = "a" * 64
        policy["policy_sha256"] = policy_cli.canonical_hash(policy, "policy_sha256")
        current_markdown_hash = file_hash(ROOT / "references" / "standard-policy-v8.md")
        self.assertNotEqual(current_markdown_hash, policy["policy_profile"]["standard_policy_sha256"])
        v8.validate_v8_policy(policy)

    def test_bad_policy_self_hash_still_fails(self) -> None:
        policy = policy_cli.build_policy(self.policy_input())
        policy["policy_sha256"] = "f" * 64
        with self.assertRaisesRegex(scoring.CalculationError, "self-hash"):
            v8.validate_v8_policy(policy)

    def test_wrong_policy_profile_still_fails(self) -> None:
        policy = policy_cli.build_policy(self.policy_input())
        policy["policy_profile"]["id"] = "subject-index-standard-policy-v9"
        policy["policy_sha256"] = policy_cli.canonical_hash(policy, "policy_sha256")
        with self.assertRaises(scoring.CalculationError):
            v8.validate_v8_policy(policy)


class LedgerIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_entry(self, name: str, document: dict, role: str) -> tuple[dict, dict, Path]:
        path = self.root / name
        path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
        artifact = {"role": role, "path": name, "sha256": file_hash(path), "schema_version": document["schema_version"]}
        return document, artifact, path

    def loaded(self) -> dict:
        locator_documents = []
        locator_entries = []
        missing_documents = []
        missing_entries = []
        for number in (1, 2):
            chunk_id = f"CHUNK-{number:03d}"
            locator_id = f"LOC-{number:03d}"
            locator = {
                "schema_version": "locator-audit-v2",
                "evaluation_id": "EVAL-TEST",
                "candidate_sha256": SHA["candidate"],
                "chunk_id": chunk_id,
                "expected_locator_ids": [locator_id],
                "judgments": [{"locator_id": locator_id, "path_id": f"PATH-{number:03d}"}],
                "provenance": {"source_sha256": str(number) * 64, "policy_sha256": "9" * 64},
            }
            locator_documents.append(locator)
            locator_entries.append(self.write_entry(f"locator-{number}.json", locator, f"locator_audit[{number - 1}]"))

            subject_id = f"SUBJ-{number:03d}"
            task_id = f"TASK-{number:03d}"
            treatment_id = f"TREAT-{number:03d}"
            missing = {
                "schema_version": "missing-access-audit-v1",
                "evaluation_id": "EVAL-TEST",
                "benchmark_sha256": SHA["benchmark"],
                "candidate_sha256": SHA["candidate"],
                "chunk_id": chunk_id,
                "expected_subject_ids": [subject_id],
                "expected_reader_task_ids": [task_id],
                "expected_treatment_ids": [treatment_id],
                "subject_judgments": [{"subject_id": subject_id}],
                "reader_task_results": [{"task_id": task_id}],
                "treatment_judgments": [{"treatment_id": treatment_id}],
                "provenance": {
                    "policy_sha256": "7" * 64,
                    "page_map_sha256": "8" * 64,
                    "chunk_manifest_sha256": "9" * 64,
                    "locator_audit_set_sha256": "a" * 64,
                },
            }
            missing_documents.append(missing)
            missing_entries.append(self.write_entry(f"missing-{number}.json", missing, f"missing_access_audit[{number - 1}]"))

        structure = {
            "schema_version": "structure-audit-v5",
            "evaluation_id": "EVAL-TEST",
            "candidate_sha256": SHA["candidate"],
            "audit_mode": "full",
            "density": {"chapter_measurements": [{"chunk_id": f"CHUNK-{number:03d}"} for number in (1, 2)]},
            "provenance": {"locator_audit_set_sha256": "b" * 64, "missing_access_audit_set_sha256": "c" * 64},
        }
        _, structure_artifact, structure_path = self.write_entry("structure.json", structure, "structure_audit")
        manifest = {
            "page_map_sha256": SHA["page_map"],
            "chunk_manifest_sha256": SHA["manifest"],
            "user_approved": True,
            "require_full_scope_coverage": True,
            "validation": {"owned_pages_unique": True, "scope_coverage_complete": True},
            "chunks": [
                {"chunk_id": f"CHUNK-{number:03d}", "owned_document_page_ranges": [[number, number]]}
                for number in (1, 2)
            ],
        }
        return {
            "config": {"evaluation_id": "EVAL-TEST", "audit_mode": "full"},
            "policy": {
                "policy_sha256": SHA["policy"],
                "audit_design": {"mode": "full"},
                "source_scope": {
                    "source_sha256": SHA["source"],
                    "document_page_span": [1, 2],
                    "page_map_sha256": SHA["page_map"],
                    "chunk_manifest_sha256": SHA["manifest"],
                },
            },
            "locator_documents": locator_documents,
            "missing_documents": missing_documents,
            "structure": structure,
            "chunk_manifest": manifest,
            "locator_input_entries": locator_entries,
            "missing_input_entries": missing_entries,
            "input_artifacts": [structure_artifact],
            "input_paths": [entry[2] for entry in locator_entries + missing_entries] + [structure_path],
        }

    def test_redundant_worker_provenance_does_not_gate_canonical_inputs(self) -> None:
        identity = scoring.validate_ledger_set_integrity(self.loaded())
        self.assertEqual(SHA["source"], identity["source_sha256"])
        self.assertEqual(SHA["policy"], identity["policy_sha256"])
        self.assertEqual(SHA["page_map"], identity["page_map_sha256"])
        self.assertEqual(SHA["manifest"], identity["chunk_manifest_sha256"])

    def test_wrong_candidate_and_chunk_identity_still_fail(self) -> None:
        loaded = self.loaded()
        loaded["missing_documents"][0]["candidate_sha256"] = "0" * 64
        with self.assertRaisesRegex(scoring.CalculationError, "candidate"):
            scoring.validate_ledger_set_integrity(loaded)

        loaded = self.loaded()
        loaded["missing_documents"][0]["chunk_id"] = "CHUNK-002"
        with self.assertRaisesRegex(scoring.CalculationError, "duplicate chunk"):
            scoring.validate_ledger_set_integrity(loaded)

    def test_changed_selected_file_still_fails_its_frozen_hash(self) -> None:
        loaded = self.loaded()
        loaded["locator_input_entries"][0][2].write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(scoring.CalculationError, "changed"):
            scoring.validate_ledger_set_integrity(loaded)

    def test_manifest_coverage_must_be_complete_and_nonoverlapping(self) -> None:
        loaded = self.loaded()
        loaded["chunk_manifest"]["chunks"][1]["owned_document_page_ranges"] = [[1, 1]]
        with self.assertRaisesRegex(scoring.CalculationError, "overlaps"):
            scoring.validate_ledger_set_integrity(loaded)

        loaded = self.loaded()
        loaded["chunk_manifest"]["chunks"][1]["owned_document_page_ranges"] = [[3, 3]]
        with self.assertRaisesRegex(scoring.CalculationError, "complete"):
            scoring.validate_ledger_set_integrity(loaded)

    def test_audit_set_hashes_are_order_independent_and_byte_sensitive(self) -> None:
        loaded = self.loaded()
        first = scoring.validate_ledger_set_integrity(loaded)
        loaded["locator_documents"].reverse()
        loaded["locator_input_entries"].reverse()
        loaded["missing_documents"].reverse()
        loaded["missing_input_entries"].reverse()
        reordered = scoring.validate_ledger_set_integrity(loaded)
        self.assertEqual(first["locator_audit_set_sha256"], reordered["locator_audit_set_sha256"])
        self.assertEqual(first["missing_access_audit_set_sha256"], reordered["missing_access_audit_set_sha256"])

        document, artifact, path = loaded["locator_input_entries"][0]
        document["informational_note"] = "changed bytes"
        path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
        artifact["sha256"] = file_hash(path)
        changed = scoring.validate_ledger_set_integrity(loaded)
        self.assertNotEqual(first["locator_audit_set_sha256"], changed["locator_audit_set_sha256"])

    def test_missing_duplicate_and_foreign_ids_remain_detectable(self) -> None:
        documents = [{"chunk_id": "CHUNK-001", "expected": ["LOC-1", "LOC-2"], "records": [{"id": "LOC-1"}]}]
        _, _, missing, _ = scoring.flatten_unique(documents, "records", "id", "expected")
        self.assertEqual(["LOC-2"], missing)

        documents[0]["records"].append({"id": "LOC-1"})
        with self.assertRaisesRegex(scoring.CalculationError, "duplicate"):
            scoring.flatten_unique(documents, "records", "id", "expected")

        documents[0]["records"] = [{"id": "LOC-1"}, {"id": "LOC-FOREIGN"}]
        with self.assertRaisesRegex(scoring.CalculationError, "outside"):
            scoring.flatten_unique(documents, "records", "id", "expected")

    def test_registration_rejects_wrong_packet_denominator_without_provenance(self) -> None:
        artifact = {
            "evaluation_id": "EVAL-TEST",
            "candidate_sha256": SHA["candidate"],
            "chunk_id": "CHUNK-001",
            "expected_locator_ids": ["LOC-WRONG"],
            "judgments": [],
        }
        packet = {"assignments": {"LOC-001": {}}, "paths": {}}
        frozen = {"state": {"evaluation_id": "EVAL-TEST"}, "candidate_sha256": SHA["candidate"]}
        with mock.patch.object(audits, "schema_errors", return_value=[]), self.assertRaisesRegex(audits.PreparationError, "exact packet"):
            audits.validate_locator_audit(artifact, frozen, packet, "CHUNK-001")

    def test_registration_rejects_wrong_missing_access_workset(self) -> None:
        artifact = {
            "evaluation_id": "EVAL-TEST",
            "benchmark_sha256": SHA["benchmark"],
            "candidate_sha256": SHA["candidate"],
            "chunk_id": "CHUNK-001",
            "expected_subject_ids": ["SUBJ-WRONG"],
            "expected_reader_task_ids": [],
            "expected_treatment_ids": [],
            "subject_judgments": [],
            "reader_task_results": [],
            "treatment_judgments": [],
        }
        frozen = {
            "state": {"evaluation_id": "EVAL-TEST"},
            "benchmark": {"benchmark_sha256": SHA["benchmark"]},
            "candidate_sha256": SHA["candidate"],
        }
        workset = {"subject_ids": ["SUBJ-001"], "reader_task_ids": [], "treatment_ids": []}
        with mock.patch.object(audits, "schema_errors", return_value=[]), self.assertRaisesRegex(audits.PreparationError, "deterministic ownership"):
            audits.validate_missing_access_audit(artifact, frozen, workset, "CHUNK-001")


if __name__ == "__main__":
    unittest.main()
