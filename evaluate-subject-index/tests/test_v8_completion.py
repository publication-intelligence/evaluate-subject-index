from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

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
        first_bytes = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in [self.root / "scoring/web-report.v10.json", *sorted(projection_root.rglob("*.json"))]}
        state["artifacts"] = [item for item in state["artifacts"] if item["stage"] != "web_report"]
        state["stages"]["web_report"] = {"status": "not_started", "updated_at": None, "notes": []}
        self.state_path.write_text(json.dumps(state, indent=2) + "\n")
        (self.root / "scoring/web-report.v10.json").unlink()
        shutil.rmtree(projection_root)
        rebuilt = self.run_cli("build-report", "--state", str(self.state_path))
        self.assertEqual(0, rebuilt.returncode, rebuilt.stdout + rebuilt.stderr)
        second_bytes = {path.relative_to(self.root).as_posix(): path.read_bytes() for path in [self.root / "scoring/web-report.v10.json", *sorted(projection_root.rglob("*.json"))]}
        self.assertEqual(first_bytes, second_bytes)

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
