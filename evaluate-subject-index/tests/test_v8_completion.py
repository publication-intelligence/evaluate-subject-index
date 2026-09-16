from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dimension_score_v8_cli as dimensions  # noqa: E402
import policy_cli  # noqa: E402
import scoring_core as core  # noqa: E402
import state_cli  # noqa: E402
import web_projection  # noqa: E402
from structure_audit import id_set_hash  # noqa: E402


SOURCE_SHA = "1" * 64
PAGE_MAP_SHA = "2" * 64
CANDIDATE_SHA = "3" * 64
BENCHMARK_SHA = "4" * 64
EVALUATION_ID = "EVAL-SYNTHETIC-COMPLETE"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CurrentV8CompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.state_path = self.root / "evaluation-state.json"
        self.structure_path = self.root / "structure-audit.v5.json"
        self._build_registered_audit_state()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, document: dict) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return path

    def record(self, path: Path, stage: str, artifact_type: str, schema_version: str | None = None) -> dict:
        relative = path.relative_to(self.root).as_posix()
        digest = file_hash(path)
        return {
            "artifact_id": state_cli.artifact_id(relative, digest),
            "stage": stage,
            "artifact_type": artifact_type,
            "path": relative,
            "sha256": digest,
            "media_type": "application/json",
            "visibility": "private",
            "retention": "required",
            "frozen": True,
            "recorded_at": "2026-01-01T00:00:00Z",
            **({"schema_version": schema_version} if schema_version else {}),
        }

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "dimension_score_v8_cli.py"), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def add_cross_reference_record_for_existing_heading(self) -> None:
        candidate_path = self.root / "candidate/candidate-index.json"
        candidate = json.loads(candidate_path.read_text())
        candidate["records"].append({
            "record_id": "REC-002",
            "record_type": "cross_reference",
            "path_id": "PATH-002",
            "heading_path": ["Synthetic subject"],
            "original_displayed_form": "Synthetic subject. See also Synthetic subject",
            "locator_displays": [],
            "locator_assignments": [],
            "cross_references": [{
                "reference_id": "XREF-001",
                "type": "see also",
                "target": "Synthetic subject",
                "target_path_id": "PATH-001",
                "original_displayed_form": "Synthetic subject",
            }],
        })
        candidate["normalization"]["record_count"] = 2
        self.write("candidate/candidate-index.json", candidate)

        inventory_path = self.root / "candidate/item-inventory.json"
        inventory = json.loads(inventory_path.read_text())
        inventory["paths"].append({
            "path_id": "PATH-002", "record_id": "REC-002", "record_type": "cross_reference",
            "heading_path": ["Synthetic subject"], "node_ids": ["NODE-001"],
            "locator_ids": [], "reference_ids": ["XREF-001"],
        })
        inventory["heading_nodes"][0]["path_ids"].append("PATH-002")
        inventory["heading_nodes"][0]["record_ids"].append("REC-002")
        inventory["heading_nodes"][0]["direct_path_ids"].append("PATH-002")
        inventory["cross_references"].append({
            "reference_id": "XREF-001", "record_id": "REC-002", "source_path_id": "PATH-002",
            "source_node_id": "NODE-001", "reference_type": "see also",
            "target_display": "Synthetic subject", "target_path_id": "PATH-001",
        })
        inventory["counts"]["paths"] = 2
        inventory["counts"]["cross_references"] = 1
        self.write("candidate/item-inventory.json", inventory)

        state = json.loads(self.state_path.read_text())
        for artifact_type, path in (("candidate_index", candidate_path), ("item_inventory", inventory_path)):
            record = next(item for item in state["artifacts"] if item["artifact_type"] == artifact_type)
            record["sha256"] = file_hash(path)
            record["artifact_id"] = state_cli.artifact_id(record["path"], record["sha256"])
            if artifact_type == "candidate_index":
                state["candidate"]["normalized_sha256"] = record["sha256"]
        self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def treatment_pages(*, found: list[int] | None = None) -> dict:
        found = found or []
        return {
            "expected_document_pages": found,
            "found_document_pages": found,
            "missed_document_pages": [],
            "uninspectable_document_pages": [],
        }

    def _build_registered_audit_state(self) -> None:
        manifest = {
            "schema_version": "chunk-manifest-v1",
            "document_page_basis": "one_based_inclusive",
            "user_approved": True,
            "require_full_scope_coverage": True,
            "chunks": [{
                "chunk_id": "CHUNK-001",
                "title": "Synthetic chapter",
                "source_units": ["chapter-1"],
                "owned_document_page_ranges": [[1, 1]],
                "context_document_page_ranges": [[1, 1]],
                "packet_order": 1,
            }],
            "page_map_sha256": PAGE_MAP_SHA,
            "validation": {"owned_pages_unique": True, "scope_coverage_complete": True},
            "chunk_manifest_sha256": None,
        }
        manifest["chunk_manifest_sha256"] = core.canonical_hash(manifest, "chunk_manifest_sha256")
        policy = policy_cli.build_policy({
            "policy_id": "POLICY-SYNTHETIC",
            "source_scope": {
                "source_sha256": SOURCE_SHA,
                "document_page_span": [1, 1],
                "page_map_sha256": PAGE_MAP_SHA,
                "chunk_manifest_sha256": manifest["chunk_manifest_sha256"],
                "availability": {},
            },
            "audience": {"label": "general", "basis": "inferred", "confidence": "high", "rationale": "Synthetic fixture."},
            "audit_design": {"mode": "full", "candidate_blindness": "required"},
            "deviations": [],
        })
        candidate = {
            "schema_version": "candidate-index-v2",
            "candidate_id": "CANDIDATE-SYNTHETIC",
            "candidate_sha256": CANDIDATE_SHA,
            "page_map_sha256": PAGE_MAP_SHA,
            "records": [{
                "record_id": "REC-001",
                "record_type": "page_bearing",
                "path_id": "PATH-001",
                "heading_path": ["Synthetic subject"],
                "original_displayed_form": "Synthetic subject, 1",
                "locator_displays": [{"display_id": "DISPLAY-001", "displayed_locator": "1", "kind": "point", "mapping_status": "resolved", "locator_ids": ["LOC-001"]}],
                "locator_assignments": [{"locator_id": "LOC-001", "display_id": "DISPLAY-001", "displayed_locator": "1", "source_page_label": "1", "normalized_locator_key": "1", "document_page": 1, "mapping_status": "resolved", "range_id": None}],
                "cross_references": [],
            }],
            "normalization": {"engine": "synthetic", "engine_version": "1", "record_count": 1, "editorial_corrections_applied": False, "benchmark_content_used": False},
        }
        inventory = {
            "schema_version": "subject-index-item-inventory-v2",
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": CANDIDATE_SHA,
            "paths": [{"path_id": "PATH-001", "record_id": "REC-001", "record_type": "page_bearing", "heading_path": ["Synthetic subject"], "node_ids": ["NODE-001"], "locator_ids": ["LOC-001"], "reference_ids": []}],
            "heading_nodes": [{"node_id": "NODE-001", "level": 1, "role": "main_heading", "label": "Synthetic subject", "heading_path": ["Synthetic subject"], "parent_node_id": None, "path_ids": ["PATH-001"], "record_ids": ["REC-001"], "direct_path_ids": ["PATH-001"]}],
            "locators": [{"locator_id": "LOC-001", "path_id": "PATH-001", "node_ids": ["NODE-001"], "source_page_label": "1", "document_page": 1, "mapping_status": "resolved"}],
            "cross_references": [],
            "counts": {"paths": 1, "heading_nodes": 1, "locators": 1, "cross_references": 0},
        }
        locator = {
            "schema_version": "locator-audit-v2",
            "evaluation_id": EVALUATION_ID,
            "candidate_sha256": CANDIDATE_SHA,
            "chunk_id": "CHUNK-001",
            "expected_locator_ids": ["LOC-001"],
            "judgments": [{
                "locator_id": "LOC-001", "path_id": "PATH-001", "complete_heading_path": ["Synthetic subject"],
                "document_page": 1, "source_page_label": "1", "source_scope_status": "indexable",
                "treatment_class": "mixed", "complete_path_fit": "exact_fit", "judgment": "supported",
                "evidence_summary": "The page gives independently useful treatment.",
                "fit_rationale": "The page directly treats the complete heading path.",
                "evidence_ids": ["EVID-LOC-001"], "confidence": "high", "error_codes": [], "severity": "none",
            }],
            "completion": {"expected": 1, "judged": 1, "unique": True, "complete": True},
        }
        missing = {
            "schema_version": "missing-access-audit-v1",
            "evaluation_id": EVALUATION_ID,
            "benchmark_sha256": BENCHMARK_SHA,
            "candidate_sha256": CANDIDATE_SHA,
            "chunk_id": "CHUNK-001",
            "expected_subject_ids": ["SUBJ-001"],
            "expected_reader_task_ids": ["TASK-001"],
            "expected_treatment_ids": ["TREAT-001"],
            "subject_judgments": [{
                "subject_id": "SUBJ-001", "priority": "essential", "coverage": "complete", "direct_access": True,
                "cross_reference_access": False, "stance_preserved": "yes", "matched_path_ids": ["PATH-001"],
                "expected_document_pages": [1], "found_document_pages": [1], "missed_document_pages": [],
                "severity": "none", "confidence": "high", "realistic_first_lookup_success": "yes",
                "treatment_recall": {"principal": self.treatment_pages(found=[1]), "supporting": self.treatment_pages(), "synthesis_or_conclusion": self.treatment_pages()},
                "locator_recall": {"expected": 1, "found": 1, "missed": 0, "rate": 1},
                "missing_routes": [], "missed_treatments": [], "error_codes": [], "evidence_ids": ["EVID-SUBJ-001"],
                "uncertainty": {"status": "none"},
            }],
            "reader_task_results": [{"task_id": "TASK-001", "subject_ids": ["SUBJ-001"], "result": "succeeds", "access_mode": "direct", "matched_path_ids": ["PATH-001"], "severity": "none", "confidence": "high", "evidence_ids": ["EVID-TASK-001"]}],
            "treatment_judgments": [{"treatment_id": "TREAT-001", "subject_id": "SUBJ-001", "document_page": 1, "locator_class": "principal", "status": "found", "evidence_ids": ["EVID-TREAT-001"]}],
            "reader_task_completion": {"expected": 1, "judged": 1, "unique": True, "complete": True},
            "treatment_completion": {"expected": 1, "judged": 1, "unique": True, "complete": True},
            "completion": {"expected": 1, "judged": 1, "complete": True},
        }
        structure = {
            "schema_version": "structure-audit-v6",
            "evaluation_id": EVALUATION_ID,
            "candidate_sha256": CANDIDATE_SHA,
            "audit_mode": "full",
            "candidate_denominator": {
                "nodes": [{"node_id": "NODE-001", "heading_path": ["Synthetic subject"], "role": "main_heading"}],
                "cross_reference_ids": [], "locator_bearing_path_ids": ["PATH-001"],
                "node_count": 1, "cross_reference_count": 0, "locator_bearing_path_count": 1,
                "node_id_set_sha256": id_set_hash(["NODE-001"]),
                "cross_reference_id_set_sha256": id_set_hash([]),
                "locator_bearing_path_id_set_sha256": id_set_hash(["PATH-001"]),
            },
            "full_scope_attestation": {"complete": True, "all_nodes_reviewed": True, "all_cross_references_reviewed": True, "all_locator_bearing_paths_checked_for_triggers": True, "unlisted_node_disposition": "passes", "unlisted_cross_reference_disposition": "supported", "pilot_pass_node_ids": [], "pilot_supported_cross_reference_ids": [], "evidence_ids": ["EVID-STRUCTURE-SCOPE"]},
            "metrics": {"page_bearing_paths": 1, "expanded_locators": 1, "cross_references": 0, "total_paths": 1, "total_nodes": 1},
            "density": {"policy_status": "scored", "measurement_level": "chapter_or_approved_intellectual_unit", "targets": [{}, {}], "chapter_measurements": [{"chunk_id": "CHUNK-001", "indexable_source_words": 100, "locator_bearing_heading_paths": 1, "locator_occurrences": 1}], "maximum_score_contribution": 5, "distribution_findings": []},
            "node_judgments": [{
                "node_id": "NODE-001",
                "component_judgments": {
                    "conceptual_stance_fidelity": {"status": "passes", "summary": "Concept preserved.", "evidence_ids": ["EVID-NODE-001"]},
                    "heading_access_architecture": {"status": "passes", "summary": "Access works.", "evidence_ids": ["EVID-NODE-001"], "causal_findings": []},
                    "mechanics_consistency": {"status": "cosmetic_issues", "summary": "One cosmetic inconsistency.", "evidence_ids": ["EVID-NODE-001"]},
                },
                "summary": "One explicit structure exception.", "confidence": "high", "evidence_ids": ["EVID-NODE-001"],
            }],
            "cross_reference_judgments": [],
            "locator_architecture": {"thresholds": {"long_displayed_locator_string": {"operator": ">", "displayed_locator_count": 6}, "long_continuous_range": {"operator": ">", "inclusive_range_span": 10}, "numeric_trigger_is_automatic_defect": False}, "triggered_path_ids": [], "triggered_reviews": []},
            "defects": [],
            "strengths": [{"strength_id": "STRENGTH-001", "summary": "Direct access succeeds.", "affected_item_ids": ["PATH-001"], "evidence_ids": ["EVID-TASK-001"]}],
            "uncertainties": [],
            "scoring_context": {
                "candidate_attempt": {"status": "meaningful_attempt", "evidence_ids": []},
                "cross_reference_applicability": {"status": "inapplicable", "basis_code": "no_delivered_references_no_obligation_or_defect", "delivered_reference_count": 0, "warranted_reference_obligation_count": 0, "warranted_reference_obligation_ids": [], "reference_defect_ids": []},
                "optional_subject_scoring": [],
                "node_component_applicability": [],
            },
        }
        self.write("structure-audit.v5.json", structure)

        actual = {
            "page_mapping": self.write("page-map.json", {"synthetic": True}),
            "chunk_definition": self.write("chunk-manifest.json", manifest),
            "define_policy": self.write("evaluation-policy.json", policy),
            "benchmark_freeze": self.write("source-benchmark.json", {
                "schema_version": "source-subject-benchmark-v2", "benchmark_id": "BENCHMARK-SYNTHETIC", "version": 1,
                "evaluation_id": EVALUATION_ID, "source_sha256": SOURCE_SHA, "policy_sha256": policy["policy_sha256"],
                "page_map_sha256": PAGE_MAP_SHA, "candidate_blindness": "preserved", "chunk_manifest_sha256": manifest["chunk_manifest_sha256"],
                "subjects": [{"subject_id": "SUBJ-001", "label": "Synthetic subject", "priority": "essential", "meaning": "Synthetic meaning.", "stance": "Synthetic stance.", "acceptable_access": ["Synthetic subject"], "chapter_provenance": ["CHUNK-001"], "evidence": [{"evidence_id": "EVID-TREAT-001", "document_page": 1, "source_page_label": "1", "locator_class": "principal"}]}],
                "relationships": [], "reader_tasks": [{"task_id": "TASK-001", "question": "Find the synthetic subject.", "subject_ids": ["SUBJ-001"]}],
                "freeze": {"frozen_at": "2026-01-01T00:00:00Z", "synthesis_pass_complete": True, "page_coverage_complete": True},
                "benchmark_sha256": BENCHMARK_SHA,
            }),
            "candidate_index": self.write("candidate/candidate-index.json", candidate),
            "item_inventory": self.write("candidate/item-inventory.json", inventory),
            "locator_audit": self.write("candidate/locator-audit.CHUNK-001.v2.json", locator),
            "missing_access_audit": self.write("candidate/missing-access-audit.CHUNK-001.v1.json", missing),
        }
        records = [
            self.record(actual["page_mapping"], "page_mapping", "page_map", "page-map-v1"),
            self.record(actual["chunk_definition"], "chunk_definition", "chunk_manifest", "chunk-manifest-v1"),
            self.record(actual["define_policy"], "define_policy", "evaluation_policy", "subject-index-evaluation-policy-v4"),
            self.record(actual["benchmark_freeze"], "benchmark_freeze", "source_benchmark", "source-subject-benchmark-v2"),
            self.record(actual["candidate_index"], "candidate_normalization", "candidate_index", "candidate-index-v2"),
            self.record(actual["item_inventory"], "candidate_normalization", "item_inventory", "subject-index-item-inventory-v2"),
            self.record(actual["locator_audit"], "locator_audit", "locator_audit", "locator-audit-v2"),
            self.record(actual["missing_access_audit"], "missing_access_audit", "missing_access_audit", "missing-access-audit-v1"),
        ]
        for stage in ("source_chunk_preparation", "source_subject_discovery", "benchmark_synthesis", "benchmark_review", "locator_chunk_preparation"):
            path = self.write(f"support/{stage}.json", {"stage": stage})
            records.append(self.record(path, stage, stage))
        candidate_record = next(item for item in records if item["artifact_type"] == "candidate_index")
        state = {
            "schema_version": "subject-index-evaluation-state-v6",
            "evaluation_id": EVALUATION_ID,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "source": {"title": "Synthetic source", "filename": "synthetic.pdf", "sha256": SOURCE_SHA, "document_page_span": [1, 1]},
            "candidate": {"candidate_id": candidate["candidate_id"], "candidate_sha256": CANDIDATE_SHA, "schema_version": "candidate-index-v2", "normalized_path": candidate_record["path"], "normalized_sha256": candidate_record["sha256"], "item_inventory_path": next(item["path"] for item in records if item["artifact_type"] == "item_inventory"), "benchmark_path": next(item["path"] for item in records if item["stage"] == "benchmark_freeze"), "benchmark_sha256": BENCHMARK_SHA},
            "configuration": {"audit_mode": "full", "index_type": "subject_index", "intended_readership": "general", "readership_provenance": {"basis": "inferred", "confidence": "high", "rationale": "Synthetic fixture."}, "output_format": "json", "storage_mode": "local", "policy_profile": "subject-index-standard-policy-v8", "rubric_version": "subject-index-rubric-v8", "scoring_identity": {"rubric_version": "subject-index-rubric-v8", "dimension_calculation_profile": "subject-index-dimension-calculation-v5"}},
            "stages": {stage: {"status": "completed" if STAGES_INDEX[stage] <= STAGES_INDEX["missing_access_audit"] else "not_started", "updated_at": "2026-01-01T00:00:00Z" if STAGES_INDEX[stage] <= STAGES_INDEX["missing_access_audit"] else None, "notes": []} for stage in state_cli.STAGES},
            "artifacts": sorted(records, key=lambda item: item["path"]),
            "blockers": [],
        }
        self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def test_major_node_exceptions_score_without_duplicate_defects(self) -> None:
        structure = json.loads(self.structure_path.read_text())
        components = structure["node_judgments"][0]["component_judgments"]
        for component_id in ("conceptual_stance_fidelity", "mechanics_consistency"):
            components[component_id] = {
                "status": "major_issues",
                "summary": "Evidence-bound major synthetic exception.",
                "evidence_ids": ["EVID-NODE-001"],
            }
        structure["node_judgments"][0]["summary"] = "Evidence-bound major exceptions with no duplicate defect rows."
        self.write("structure-audit.v5.json", structure)

        registered = self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path))
        self.assertEqual(0, registered.returncode, registered.stdout + registered.stderr)
        scored = self.run_cli("score", "--state", str(self.state_path))
        self.assertEqual(0, scored.returncode, scored.stdout + scored.stderr)

        calculations = json.loads((self.root / "scoring/dimension-calculations.v6.json").read_text())
        dimensions = {item["dimension_id"]: item for item in calculations["dimensions"]}
        for component_id in ("conceptual_stance_fidelity", "mechanics_consistency"):
            self.assertEqual("scored", dimensions[component_id]["status"])
            self.assertEqual(1, dimensions[component_id]["raw_status_counts"]["major_issues"])
        self.assertEqual([], structure["defects"])

    def test_distinct_heading_path_denominator_accepts_separate_cross_reference_record(self) -> None:
        self.add_cross_reference_record_for_existing_heading()
        structure = json.loads(self.structure_path.read_text())
        denominator = structure["candidate_denominator"]
        denominator["cross_reference_ids"] = ["XREF-001"]
        denominator["cross_reference_count"] = 1
        denominator["cross_reference_id_set_sha256"] = id_set_hash(["XREF-001"])
        structure["metrics"]["cross_references"] = 1
        structure["scoring_context"]["cross_reference_applicability"] = {
            "status": "applicable", "basis_code": "delivered_references",
            "delivered_reference_count": 1, "warranted_reference_obligation_count": 0,
            "warranted_reference_obligation_ids": [], "reference_defect_ids": [],
        }

        structure["metrics"]["total_paths"] = 2
        self.write("structure-audit.v5.json", structure)
        state_before_rejection = self.state_path.read_bytes()
        incorrect = self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path))
        self.assertNotEqual(0, incorrect.returncode)
        self.assertIn("structure_candidate_metric_mismatch", incorrect.stdout)
        self.assertEqual(state_before_rejection, self.state_path.read_bytes())

        structure["metrics"]["total_paths"] = 1
        self.write("structure-audit.v5.json", structure)
        registered = self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path))
        self.assertEqual(0, registered.returncode, registered.stdout + registered.stderr)
        scored = self.run_cli("score", "--state", str(self.state_path))
        self.assertEqual(0, scored.returncode, scored.stdout + scored.stderr)

    def test_explicit_major_defect_still_triggers_concept_cap(self) -> None:
        structure = json.loads(self.structure_path.read_text())
        concept = structure["node_judgments"][0]["component_judgments"]["conceptual_stance_fidelity"]
        concept.update({"status": "major_issues", "evidence_ids": ["EVID-NODE-001", "DEFECT-001"]})
        structure["defects"] = [{
            "defect_id": "DEFECT-001",
            "code": "STA",
            "dimension_owner": "conceptual_stance_fidelity",
            "severity": "major",
            "severity_basis": "materially_misleading",
            "retrieval_consequence": "misleads",
            "defect_kind": "stance_reversal",
            "affected_item_ids": ["NODE-001"],
            "affected_source_sections": [],
            "affected_structural_sections": ["NODE-001"],
            "root_cause_family": "synthetic_stance_reversal",
            "affected_count": 1,
            "applicable_count": 1,
            "affected_rate": 1,
            "source_section_denominator": 1,
            "source_section_rate": 0,
            "structural_section_denominator": 1,
            "structural_section_rate": 1,
            "high_priority_access_destroyed": False,
        }]
        self.write("structure-audit.v5.json", structure)

        registered = self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path))
        self.assertEqual(0, registered.returncode, registered.stdout + registered.stderr)
        scored = self.run_cli("score", "--state", str(self.state_path))
        self.assertEqual(0, scored.returncode, scored.stdout + scored.stderr)

        calculations = json.loads((self.root / "scoring/dimension-calculations.v6.json").read_text())
        concept_dimension = next(item for item in calculations["dimensions"] if item["dimension_id"] == "conceptual_stance_fidelity")
        localized_cap = next(item for item in concept_dimension["cap_evaluations"] if item["cap_id"] == "concept.localized_major_defect")
        self.assertTrue(localized_cap["triggered"])
        self.assertEqual(["DEFECT-001"], localized_cap["affected_evidence_ids"])

    def test_standalone_preflight_accepts_native_v6_and_preserves_validation(self) -> None:
        registered = self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path))
        self.assertEqual(0, registered.returncode, registered.stdout + registered.stderr)
        scored = self.run_cli("score", "--state", str(self.state_path))
        self.assertEqual(0, scored.returncode, scored.stdout + scored.stderr)

        config_path = self.root / "scoring/dimension-calculation-input.v2.json"
        preflight = self.run_cli("preflight", "--input", str(config_path))
        self.assertEqual(0, preflight.returncode, preflight.stdout + preflight.stderr)
        self.assertTrue(json.loads(preflight.stdout)["sufficient"])

        locator_path = self.root / "candidate/locator-audit.CHUNK-001.v2.json"
        locator = json.loads(locator_path.read_text())
        del locator["judgments"][0]["complete_path_fit"]
        self.write("candidate/locator-audit.CHUNK-001.v2.json", locator)
        invalid = self.run_cli("preflight", "--input", str(config_path))
        self.assertEqual(0, invalid.returncode, invalid.stdout + invalid.stderr)
        result = json.loads(invalid.stdout)
        self.assertFalse(result["sufficient"])
        self.assertEqual("inconsistent_or_incomplete_locator_utility_state", result["missing_requirements"][0]["code"])

    def test_registered_audits_reach_valid_result_report_and_complete_state(self) -> None:
        original_state = self.state_path.read_bytes()
        missing = self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.root / "missing-structure.json"))
        self.assertNotEqual(0, missing.returncode)
        self.assertIn("input_not_found", missing.stdout)
        self.assertEqual(original_state, self.state_path.read_bytes())

        wrong_structure = copy.deepcopy(json.loads(self.structure_path.read_text()))
        wrong_structure["candidate_sha256"] = "f" * 64
        wrong_path = self.write("wrong-structure.json", wrong_structure)
        failed = self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(wrong_path))
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("candidate_identity_mismatch", failed.stdout)
        self.assertEqual(original_state, self.state_path.read_bytes())

        failed = subprocess.run(
            [sys.executable, str(SCRIPTS / "state_cli.py"), "set-stage", "--state", str(self.state_path), "--stage", "structure_audit", "--status", "completed", "--artifact-path", str(self.structure_path)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("typed_transition_required", failed.stdout)
        self.assertEqual(original_state, self.state_path.read_bytes())

        registered = self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path))
        self.assertEqual(0, registered.returncode, registered.stdout + registered.stderr)
        state_before_duplicate = self.state_path.read_bytes()
        duplicate_state = json.loads(state_before_duplicate)
        policy_record = next(item for item in duplicate_state["artifacts"] if item["stage"] == "define_policy")
        duplicate_policy_path = self.root / "duplicate-policy.json"
        duplicate_policy_path.write_bytes((self.root / policy_record["path"]).read_bytes())
        duplicate_state["artifacts"].append(self.record(duplicate_policy_path, "define_policy", "evaluation_policy", "subject-index-evaluation-policy-v4"))
        duplicate_state["artifacts"].sort(key=lambda item: item["path"])
        self.state_path.write_text(json.dumps(duplicate_state, indent=2) + "\n", encoding="utf-8")
        duplicate_bytes = self.state_path.read_bytes()
        failed = self.run_cli("score", "--state", str(self.state_path))
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("duplicate_registered_artifact", failed.stdout)
        self.assertEqual(duplicate_bytes, self.state_path.read_bytes())
        self.state_path.write_bytes(state_before_duplicate)

        locator_path = self.root / "candidate/locator-audit.CHUNK-001.v2.json"
        locator_bytes = locator_path.read_bytes()
        state_before_hash_failure = self.state_path.read_bytes()
        locator_path.write_bytes(locator_bytes + b" ")
        failed = self.run_cli("score", "--state", str(self.state_path))
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("registered_artifact_hash_mismatch", failed.stdout)
        self.assertEqual(state_before_hash_failure, self.state_path.read_bytes())
        locator_path.write_bytes(locator_bytes)

        scored = self.run_cli("score", "--state", str(self.state_path))
        self.assertEqual(0, scored.returncode, scored.stdout + scored.stderr)

        result_path = self.root / "scoring/evaluation-result.v12.json"
        result_bytes = result_path.read_bytes()
        state_before_report_failure = self.state_path.read_bytes()
        result_path.write_bytes(result_bytes + b" ")
        failed = self.run_cli("build-report", "--state", str(self.state_path))
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("registered_artifact_hash_mismatch", failed.stdout)
        self.assertEqual(state_before_report_failure, self.state_path.read_bytes())
        result_path.write_bytes(result_bytes)

        reported = self.run_cli("build-report", "--state", str(self.state_path))
        self.assertEqual(0, reported.returncode, reported.stdout + reported.stderr)

        state = json.loads(self.state_path.read_text())
        self.assertTrue(all(item["status"] == "completed" for item in state["stages"].values()))
        result = json.loads(result_path.read_text())
        report = json.loads((self.root / "scoring/web-report.v10.json").read_text())
        items = json.loads((self.root / "scoring/item-assessments.v7.json").read_text())
        self.assertEqual("subject-index-evaluation-result-v12", result["schema_version"])
        self.assertEqual("subject-index-web-report-v10", report["schema_version"])
        self.assertIsNotNone(result["overall_percentage"])
        calculations = json.loads((self.root / "scoring/dimension-calculations.v6.json").read_text())
        selectivity = next(item for item in calculations["dimensions"] if item["dimension_id"] == "editorial_selectivity")
        density_component = next(item for item in selectivity["components"] if item["component_id"] == "density_fit")
        expected_chapter_fits = {
            item["chunk_id"]: {
                key: item[key]
                for key in ("path_fit_percentage", "occurrence_fit_percentage", "unit_fit_percentage")
            }
            for item in density_component["details"]["chapter_measurements"]
        }
        self.assertEqual(density_component["percentage"], report["density"]["density_fit_percentage"])
        self.assertEqual(expected_chapter_fits, report["density"]["chapter_fit_by_chunk"])
        presentation = report["presentation_summary"]
        self.assertEqual("subject-index-presentation-summary-v1", presentation["schema_version"])
        self.assertEqual(
            {
                "evaluation_id": EVALUATION_ID,
                "web_report_sha256": report["calculation_explainer"]["sha256"],
            },
            presentation["provenance"],
        )
        self.assertEqual(
            {
                "essential": {"complete": 1, "partial": 0, "missing": 0},
                "major": {"complete": 0, "partial": 0, "missing": 0},
                "optional": {"complete": 0, "partial": 0, "missing": 0},
            },
            presentation["coverage_by_priority"],
        )
        self.assertEqual({"displayed_locators": 1, "expected_treatments": 1}, presentation["scope"])
        metric_by_id = {item["metric_id"]: item for item in presentation["metrics"]}
        self.assertEqual({
            "weighted_concept_access_partial_credit", "essential_concept_miss_rate", "locator_recall",
            "reader_task_strict_success", "substantive_selectivity", "strict_supported_locator_rate",
            "conceptual_stance_fidelity", "valid_entry_precision_at_least_partial", "density_fit",
            "heading_access_architecture", "cross_reference_validity", "mechanics_consistency",
        }, set(metric_by_id))
        reliability = next(item for item in calculations["dimensions"] if item["dimension_id"] == "page_reference_reliability")["reliability_provenance"]
        self.assertEqual(reliability["reliability_f1"], metric_by_id["valid_entry_precision_at_least_partial"]["value"])
        self.assertEqual("Reliability F1", metric_by_id["valid_entry_precision_at_least_partial"]["label"])
        self.assertEqual("1", metric_by_id["reader_task_strict_success"]["numerator"])
        self.assertEqual("1", metric_by_id["reader_task_strict_success"]["denominator"])
        self.assertIsNone(metric_by_id["cross_reference_validity"]["value"])
        self.assertEqual("Not applicable", metric_by_id["cross_reference_validity"]["display_value"])
        self.assertEqual(6, len(presentation["dimensions"]))
        for dimension in presentation["dimensions"]:
            self.assertTrue(dimension["rationale"])
            for line in dimension["calculation_basis"]:
                numeric_tokens = re.findall(r"-?[0-9]+(?:\.[0-9]+)?", line["equation"])
                self.assertEqual(len(numeric_tokens), len(line["number_scores"]), line["equation"])
        self.assertEqual("mixed", items["locator_assessments"][0]["locator_utility"]["treatment_category"])
        self.assertEqual("1", items["locator_assessments"][0]["dimension_reliability_credit"])
        self.assertEqual(1, len(items["source_subject_assessments"]))
        self.assertEqual(1, len(json.loads((self.root / "candidate/missing-access-audit.CHUNK-001.v1.json").read_text())["reader_task_results"]))
        projection_root = self.root / "scoring/v8-canonical-projection"
        expected = {
            "scoring/web-report.v10.json", "scoring/v8-canonical-projection/projection.v1.json",
            "scoring/v8-canonical-projection/data/index-records.v1.json",
            "scoring/v8-canonical-projection/data/source-subjects.v1.json",
            "scoring/v8-canonical-projection/data/density.v1.json",
        }
        self.assertEqual(expected, {item["path"] for item in state["artifacts"] if item["stage"] == "web_report"})
        self.assertFalse((projection_root / "data/correction-overlay.v1.json").exists())
        projection = json.loads((projection_root / "projection.v1.json").read_text())
        self.assertEqual({"index_records", "source_subjects", "density"}, {row["collection_id"] for row in projection["collections"]})
        self.assertEqual({"applicable": False, "overlay_included": False, "reason": "No confirmed registered correction overlay applies.", "affected_headings": 0, "character_replacements": 0}, projection["correction_outcomes"])
        canonical_view = projection["score_views"]["views"][0]
        self.assertEqual(report["scorecard"], [
            {key: row[key] for key in ("dimension_id", "weight", "dimension_percentage", "weighted_contribution", "formula_id")}
            for row in canonical_view["scorecard"]
        ])
        self.assertEqual(
            report["calculation_explainer"]["dimension_denominators"],
            canonical_view["dimension_denominators"],
        )
        self.assertTrue(all(isinstance(row["dimension_percentage"], str) for row in canonical_view["scorecard"]))
        self.assertTrue(all(isinstance(row["weighted_contribution"], str) for row in canonical_view["scorecard"]))
        self.assertTrue(all(row["rating"] == float(row["dimension_percentage"]) / 20 for row in canonical_view["scorecard"]))
        self.assertTrue(all(row["awarded_points"] == float(row["weighted_contribution"]) for row in canonical_view["scorecard"]))
        self.assertTrue(all(row["maximum_points"] == row["weight"] for row in canonical_view["scorecard"]))
        density_projection = json.loads((projection_root / "data/density.v1.json").read_text())
        self.assertEqual(density_component["percentage"], density_projection["fit_percentage"])
        self.assertEqual(float(density_projection["fit_percentage"]) / 20, density_projection["fit_rating"])
        legacy_projection = copy.deepcopy(projection)
        legacy_score = legacy_projection["score_views"]["views"][0]["scorecard"][0]
        legacy_score["rating"] = float(legacy_score.pop("dimension_percentage")) / 20
        legacy_score["awarded_points"] = float(legacy_score.pop("weighted_contribution"))
        legacy_score["maximum_points"] = legacy_score.pop("weight")
        with self.assertRaises(core.CalculationError):
            core.validate_schema_document(legacy_projection, "web-projection-v1.schema.json", "Legacy projection")
        density_with_rating = copy.deepcopy(density_projection)
        density_with_rating["fit_rating"] = str(density_with_rating["fit_rating"])
        with self.assertRaises(core.CalculationError):
            core.validate_schema_document(density_with_rating, "web-collection-v1.schema.json", "Legacy density")
        corrected_bytes = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in [self.root / "scoring/web-report.v10.json", *sorted(projection_root.rglob("*.json"))]}
        scoring_bytes = {self.root / item["path"]: (self.root / item["path"]).read_bytes() for item in state["artifacts"] if item["stage"] == "scoring"}

        legacy_report = copy.deepcopy(report)
        del legacy_report["calculation_explainer"]["dimension_denominators"]
        report_path = self.root / "scoring/web-report.v10.json"
        report_path.write_bytes(dimensions._json_bytes(legacy_report))
        legacy_density = copy.deepcopy(density_projection)
        legacy_density["collection_sha256"] = core.canonical_hash(legacy_density, "collection_sha256")
        density_path = projection_root / "data/density.v1.json"
        density_path.write_bytes(web_projection.json_bytes(legacy_density))
        legacy_projection = copy.deepcopy(projection)
        legacy_view = legacy_projection["score_views"]["views"][0]
        del legacy_view["dimension_denominators"]
        legacy_view["scorecard"] = [{
            "dimension_id": row["dimension_id"],
            "rating": float(row["dimension_percentage"]) / 20,
            "awarded_points": float(row["weighted_contribution"]),
            "maximum_points": row["weight"],
            "formula_id": row["formula_id"],
        } for row in report["scorecard"]]
        registered = {row["artifact_type"]: row for row in state["artifacts"] if row["stage"] == "web_report"}
        old_report_sha = registered["web_report"]["sha256"]
        registered["web_report"]["sha256"] = file_hash(report_path)
        for binding in [
            *legacy_projection["provenance"]["source_artifacts"],
            *legacy_view["provenance_artifacts"],
        ]:
            if binding["artifact_path"] == registered["web_report"]["path"]:
                binding["sha256"] = registered["web_report"]["sha256"]
        density_binding = next(row for row in legacy_projection["collections"] if row["collection_id"] == "density")
        density_binding["content_sha256"] = legacy_density["collection_sha256"]
        density_binding["file_sha256"] = file_hash(density_path)
        legacy_projection["projection_sha256"] = core.canonical_hash(legacy_projection, "projection_sha256")
        projection_path = projection_root / "projection.v1.json"
        projection_path.write_bytes(web_projection.json_bytes(legacy_projection))
        registered["web_projection"]["sha256"] = file_hash(projection_path)
        registered["web_density"]["sha256"] = file_hash(density_path)
        for record in registered.values():
            record["artifact_id"] = state_cli.artifact_id(record["path"], record["sha256"])
            if record["artifact_type"] != "web_report":
                record["input_sha256"] = sorted(registered["web_report"]["sha256"] if value == old_report_sha else value for value in record["input_sha256"])
        self.state_path.write_text(json.dumps(state, indent=2) + "\n")
        legacy_bytes = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in [report_path, *sorted(projection_root.rglob("*.json"))]}
        state_before_refusal = self.state_path.read_bytes()
        refused = self.run_cli("build-report", "--state", str(self.state_path))
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("stage_already_completed", refused.stdout)
        self.assertEqual(state_before_refusal, self.state_path.read_bytes())

        rebuilt = self.run_cli("build-report", "--state", str(self.state_path), "--replace-complete-bundle")
        self.assertEqual(0, rebuilt.returncode, rebuilt.stdout + rebuilt.stderr)
        self.assertTrue(json.loads(rebuilt.stdout)["replacement"])
        second_bytes = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in [self.root / "scoring/web-report.v10.json", *sorted(projection_root.rglob("*.json"))]}
        self.assertNotEqual(legacy_bytes, second_bytes)
        self.assertEqual(corrected_bytes, second_bytes)
        self.assertEqual(scoring_bytes, {path: path.read_bytes() for path in scoring_bytes})
        rebuilt_state = json.loads(self.state_path.read_text())
        self.assertIn("Rebuilt and replaced", rebuilt_state["stages"]["web_report"]["notes"][0])

        pure_density = json.loads(density_path.read_text())
        del pure_density["fit_rating"]
        pure_density["collection_sha256"] = core.canonical_hash(pure_density, "collection_sha256")
        density_path.write_bytes(web_projection.json_bytes(pure_density))
        pure_projection = json.loads(projection_path.read_text())
        for row in pure_projection["score_views"]["views"][0]["scorecard"]:
            for field in ("rating", "awarded_points", "maximum_points"):
                del row[field]
        density_binding = next(row for row in pure_projection["collections"] if row["collection_id"] == "density")
        density_binding["content_sha256"] = pure_density["collection_sha256"]
        density_binding["file_sha256"] = file_hash(density_path)
        pure_projection["projection_sha256"] = core.canonical_hash(pure_projection, "projection_sha256")
        projection_path.write_bytes(web_projection.json_bytes(pure_projection))
        registered = {row["artifact_type"]: row for row in rebuilt_state["artifacts"] if row["stage"] == "web_report"}
        registered["web_projection"]["sha256"] = file_hash(projection_path)
        registered["web_density"]["sha256"] = file_hash(density_path)
        for record in (registered["web_projection"], registered["web_density"]):
            record["artifact_id"] = state_cli.artifact_id(record["path"], record["sha256"])
        self.state_path.write_text(json.dumps(rebuilt_state, indent=2) + "\n")

        rebuilt_pure = self.run_cli("build-report", "--state", str(self.state_path), "--replace-complete-bundle")
        self.assertEqual(0, rebuilt_pure.returncode, rebuilt_pure.stdout + rebuilt_pure.stderr)
        third_bytes = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in [report_path, *sorted(projection_root.rglob("*.json"))]}
        self.assertEqual(corrected_bytes, third_bytes)
        self.assertEqual(scoring_bytes, {path: path.read_bytes() for path in scoring_bytes})

    def test_complete_web_bundle_replacement_rolls_back_all_bytes_on_write_failure(self) -> None:
        self.assertEqual(0, self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path)).returncode)
        self.assertEqual(0, self.run_cli("score", "--state", str(self.state_path)).returncode)
        self.assertEqual(0, self.run_cli("build-report", "--state", str(self.state_path)).returncode)
        state = json.loads(self.state_path.read_text())
        tracked = {self.root / item["path"] for item in state["artifacts"] if item["stage"] in {"scoring", "web_report"}}
        before = {path: path.read_bytes() for path in tracked}
        state_before = self.state_path.read_bytes()
        original_write = dimensions._atomic_write
        failed = False

        def fail_one_write(path: Path, payload: bytes) -> None:
            nonlocal failed
            if not failed and path.name == "source-subjects.v1.json":
                failed = True
                raise OSError("synthetic replacement write failure")
            original_write(path, payload)

        output = io.StringIO()
        args = argparse.Namespace(
            state=str(self.state_path), output=None, bundle_output=None,
            replace_complete_bundle=True,
        )
        with patch.object(dimensions, "_atomic_write", side_effect=fail_one_write), contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            dimensions.command_build_report_state(args)
        self.assertEqual(1, raised.exception.code)
        self.assertIn("web_report_registration_error", output.getvalue())
        self.assertEqual(state_before, self.state_path.read_bytes())
        self.assertEqual(before, {path: path.read_bytes() for path in tracked})

        original_save = dimensions.save_state

        def fail_after_state_replace(path: Path, value: dict) -> None:
            original_save(path, value)
            raise OSError("synthetic state write failure")

        output = io.StringIO()
        with patch.object(dimensions, "save_state", side_effect=fail_after_state_replace), contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            dimensions.command_build_report_state(args)
        self.assertEqual(1, raised.exception.code)
        self.assertIn("web_report_registration_error", output.getvalue())
        self.assertEqual(state_before, self.state_path.read_bytes())
        self.assertEqual(before, {path: path.read_bytes() for path in tracked})

    def test_complete_web_bundle_replacement_rejects_partial_and_unmanaged_targets(self) -> None:
        self.assertEqual(0, self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path)).returncode)
        self.assertEqual(0, self.run_cli("score", "--state", str(self.state_path)).returncode)
        self.assertEqual(0, self.run_cli("build-report", "--state", str(self.state_path)).returncode)
        complete_state = json.loads(self.state_path.read_text())

        partial = copy.deepcopy(complete_state)
        partial["artifacts"] = [item for item in partial["artifacts"] if item.get("artifact_type") != "web_density"]
        self.state_path.write_text(json.dumps(partial, indent=2) + "\n")
        partial_before = self.state_path.read_bytes()
        refused = self.run_cli("build-report", "--state", str(self.state_path), "--replace-complete-bundle")
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("replacement_bundle_incomplete", refused.stdout)
        self.assertEqual(partial_before, self.state_path.read_bytes())

        self.state_path.write_text(json.dumps(complete_state, indent=2) + "\n")
        report_path = self.root / "scoring/web-report.v10.json"
        report_bytes = report_path.read_bytes()
        report_path.write_bytes(report_bytes + b" ")
        complete_before = self.state_path.read_bytes()
        refused = self.run_cli("build-report", "--state", str(self.state_path), "--replace-complete-bundle")
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("registered_artifact_hash_mismatch", refused.stdout)
        self.assertEqual(complete_before, self.state_path.read_bytes())
        report_path.write_bytes(report_bytes)

        unmanaged = self.root / "scoring/v8-canonical-projection/data/unmanaged.json"
        unmanaged.write_text("{}\n")
        complete_before = self.state_path.read_bytes()
        refused = self.run_cli("build-report", "--state", str(self.state_path), "--replace-complete-bundle")
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("unmanaged_output_collision", refused.stdout)
        self.assertEqual(complete_before, self.state_path.read_bytes())
        self.assertEqual(b"{}\n", unmanaged.read_bytes())

    def test_build_report_selects_result_bound_calculation_from_history(self) -> None:
        registered = self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path))
        self.assertEqual(0, registered.returncode, registered.stdout + registered.stderr)
        scored = self.run_cli("score", "--state", str(self.state_path))
        self.assertEqual(0, scored.returncode, scored.stdout + scored.stderr)

        current_path = self.root / "scoring/dimension-calculations.v6.json"
        historical_path = self.root / "history/dimension-calculations.v6.json"
        historical_path.parent.mkdir()
        historical_path.write_text(json.dumps(json.loads(current_path.read_text())))
        state = json.loads(self.state_path.read_text())
        state["artifacts"].append(self.record(
            historical_path,
            "scoring",
            "dimension_calculations",
            "subject-index-dimension-calculations-v6",
        ))
        state["artifacts"].sort(key=lambda item: item["path"])
        self.state_path.write_text(json.dumps(state, indent=2) + "\n")

        reported = self.run_cli("build-report", "--state", str(self.state_path))

        self.assertEqual(0, reported.returncode, reported.stdout + reported.stderr)
        report = json.loads((self.root / "scoring/web-report.v10.json").read_text())
        result = json.loads((self.root / "scoring/evaluation-result.v12.json").read_text())
        self.assertEqual(result["dimension_calculations"]["sha256"], report["calculation_explainer"]["sha256"])

    def test_unsafe_projection_is_rejected_without_writes(self) -> None:
        self.assertEqual(0, self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path)).returncode)
        self.assertEqual(0, self.run_cli("score", "--state", str(self.state_path)).returncode)
        benchmark_path = self.root / "source-benchmark.json"
        benchmark = json.loads(benchmark_path.read_text())
        benchmark["subjects"][0]["meaning"] = "Unsafe /home/private/source.pdf"
        benchmark_path.write_text(json.dumps(benchmark, indent=2) + "\n")
        state = json.loads(self.state_path.read_text())
        record = next(row for row in state["artifacts"] if row["stage"] == "benchmark_freeze")
        record["sha256"] = file_hash(benchmark_path)
        record["artifact_id"] = state_cli.artifact_id(record["path"], record["sha256"])
        self.state_path.write_text(json.dumps(state, indent=2) + "\n")
        before = self.state_path.read_bytes()
        failed = self.run_cli("build-report", "--state", str(self.state_path))
        self.assertNotEqual(0, failed.returncode)
        self.assertIn("unsafe_public_projection", failed.stdout)
        self.assertEqual(before, self.state_path.read_bytes())
        self.assertFalse((self.root / "scoring/web-report.v10.json").exists())
        self.assertFalse((self.root / "scoring/v8-canonical-projection").exists())

    def test_confirmed_overlay_is_conditionally_bound(self) -> None:
        self.assertEqual(0, self.run_cli("register-structure", "--state", str(self.state_path), "--input", str(self.structure_path)).returncode)
        self.assertEqual(0, self.run_cli("score", "--state", str(self.state_path)).returncode)
        overlay = {
            "schema_version": web_projection.OVERLAY_SCHEMA_VERSION, "evaluation_id": EVALUATION_ID,
            "overlay_role": "display_only_counterfactual_bound_to_canonical_v8", "causal_classification": "confirmed_representation_only",
            "affected_heading_count": 1, "affected_node_ids": ["NODE-001"], "character_replacement_count": 1,
            "headings": [{"node_id": "NODE-001"}], "character_replacements": [{"node_id": "NODE-001"}],
            "adjusted_item_changes": {"heading_nodes": [], "locators": [], "paths": [], "cross_references": [], "source_subjects": []},
            "correction_outcomes": {"affected_headings": 1, "character_replacements": 1, "corrected_cross_reference_id": "XREF-001", "remaining_unresolved_cross_reference_id": "XREF-002", "observed_minor_defect_count": 1, "adjusted_minor_defect_count": 0, "cross_reference_gate_unchanged": True, "readiness_unchanged": True},
            "provenance": {"basis": "confirmed ledger"},
        }
        overlay["overlay_sha256"] = core.canonical_hash(overlay, "overlay_sha256")
        overlay_path = self.write("corrections/correction-overlay.v1.json", overlay)
        state = json.loads(self.state_path.read_text())
        state["artifacts"].append(self.record(overlay_path, "scoring", "correction_overlay", web_projection.OVERLAY_SCHEMA_VERSION))
        state["artifacts"].sort(key=lambda row: row["path"])
        self.state_path.write_text(json.dumps(state, indent=2) + "\n")
        built = self.run_cli("build-report", "--state", str(self.state_path))
        self.assertEqual(0, built.returncode, built.stdout + built.stderr)
        projection_root = self.root / "scoring/v8-canonical-projection"
        self.assertTrue((projection_root / "data/correction-overlay.v1.json").is_file())
        projection = json.loads((projection_root / "projection.v1.json").read_text())
        self.assertEqual("confirmed_representation_adjustment_applied", projection["score_views"]["projection_adjustment_status"])
        self.assertEqual(overlay["correction_outcomes"], projection["correction_outcomes"])


class PresentationCalculationBasisTests(unittest.TestCase):
    @staticmethod
    def component(component_id: str, value: str | None, weight: str) -> dict:
        return {
            "component_id": component_id,
            "raw_numerator": None if value is None else value,
            "raw_denominator": None if value is None else "1",
            "normalized_value": value,
            "weight": weight,
            "effective_weight": weight,
            "weight_renormalized": False,
        }

    @staticmethod
    def denominator(component_id: str, *, not_measured: int = 0, uninspectable: int = 0, inapplicable: bool = False) -> dict:
        return {
            "component_id": component_id,
            "original": 1,
            "applicable": 0 if inapplicable else 1,
            "measured": 0 if (not_measured or uninspectable or inapplicable) else 1,
            "excluded": 1 if inapplicable else 0,
            "uninspectable": uninspectable,
            "not_measured": not_measured,
            "exclusion_reasons": {"genuinely_inapplicable": 1} if inapplicable else {},
            "measurement_coverage": "0" if (not_measured or uninspectable or inapplicable) else "1",
            "small_denominator_exception": False,
            "genuinely_inapplicable": inapplicable,
            "zero_due_to_non_attempt": False,
            "defined_zero_rule": None,
            "provisionally_scoreable": not (not_measured or uninspectable),
        }

    def test_weighted_formula_and_applied_cap_are_explicit(self) -> None:
        dimension = {
            "dimension_id": "findability_navigation",
            "components": [
                self.component("coverage_conditioned_reader_tasks", "0.9", "0.60"),
                self.component("heading_access_architecture", "0.8", "0.30"),
                self.component("cross_reference_validity", "0.7", "0.10"),
            ],
            "denominators": {"components": [
                self.denominator("coverage_conditioned_reader_tasks"),
                self.denominator("heading_access_architecture"),
                self.denominator("cross_reference_validity"),
            ]},
            "pre_cap_percentage": "85",
            "dimension_percentage": "60",
            "applied_cap": {"cap_id": "findability.example", "maximum_percentage": 60, "affected_evidence_ids": []},
        }

        lines = dimensions._presentation_calculation_basis(dimension)

        self.assertTrue(any("Canonical weighted combination" in line["equation"] for line in lines))
        cap = next(line for line in lines if line["equation"].startswith("Applied cap"))
        self.assertEqual("Canonical cap: findability.example.", cap["tooltip"])
        self.assertIn("85%", cap["equation"])
        self.assertIn("60%", cap["equation"])
        for line in lines:
            self.assertEqual(
                len(re.findall(r"-?[0-9]+(?:\.[0-9]+)?", line["equation"])),
                len(line["number_scores"]),
                line["equation"],
            )

    def test_unavailable_components_keep_distinct_states(self) -> None:
        dimension = {
            "dimension_id": "findability_navigation",
            "components": [
                self.component("coverage_conditioned_reader_tasks", None, "0.60"),
                self.component("heading_access_architecture", None, "0.30"),
                self.component("cross_reference_validity", None, "0.10"),
            ],
            "denominators": {"components": [
                self.denominator("coverage_conditioned_reader_tasks", not_measured=1),
                self.denominator("heading_access_architecture", uninspectable=1),
                self.denominator("cross_reference_validity", inapplicable=True),
            ]},
            "pre_cap_percentage": None,
            "dimension_percentage": None,
            "applied_cap": None,
        }

        equations = [line["equation"] for line in dimensions._presentation_calculation_basis(dimension)]

        self.assertEqual([
            "Coverage-conditioned reader-task credit is not measured",
            "Heading-access architecture is uninspectable",
            "Cross-reference validity is not applicable",
        ], equations)


class WebProjectionJoinTests(unittest.TestCase):
    def test_reader_task_many_to_many_membership_is_preserved(self) -> None:
        grade = {"score": 100, "rating": 5, "band": "excellent", "color_token": "grade_excellent", "status": "passes"}
        subjects = [{"subject_id": f"SUBJ-00{i}", "label": f"Subject {i}", "priority": "major", "meaning": "Meaning.", "stance": "Stance.", "acceptable_access": [f"Subject {i}"], "evidence": [{"evidence_id": f"EVID-00{i}", "document_page": i, "source_page_label": str(i), "locator_class": "principal"}]} for i in (1, 2)]
        benchmark = {"subjects": subjects, "reader_tasks": [{"task_id": "TASK-001", "question": "Find both.", "subject_ids": ["SUBJ-001", "SUBJ-002"]}]}
        items = {"source_subject_assessments": [{"subject_id": row["subject_id"], "grade": grade} for row in subjects]}
        missing = [{
            "subject_judgments": [{"subject_id": row["subject_id"], "coverage": "complete"} for row in subjects],
            "reader_task_results": [{"task_id": "TASK-001", "subject_ids": ["SUBJ-001", "SUBJ-002"], "result": "succeeds"}],
            "treatment_judgments": [{"treatment_id": f"TREAT-00{i}", "subject_id": f"SUBJ-00{i}", "document_page": i, "locator_class": "principal", "status": "found", "evidence_ids": [f"EVID-00{i}"]} for i in (1, 2)],
        }]
        projected = web_projection.build_source_subjects(benchmark, items, missing)
        memberships = [task["subject_ids"] for row in projected["items"] for task in row["reader_tasks"]]
        self.assertEqual([["SUBJ-001", "SUBJ-002"], ["SUBJ-001", "SUBJ-002"]], memberships)
        self.assertEqual(1, projected["counts"]["reader_tasks"])


STAGES_INDEX = {stage: index for index, stage in enumerate(state_cli.STAGES)}


if __name__ == "__main__":
    unittest.main()
