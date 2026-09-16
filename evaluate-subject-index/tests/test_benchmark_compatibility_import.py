from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_cli(script: str, *arguments: object, ok: bool = True) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *(str(value) for value in arguments)],
        text=True, capture_output=True, check=False,
    )
    if ok and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    if not ok and not result.returncode:
        raise AssertionError("Command unexpectedly succeeded: " + result.stdout)
    return json.loads(result.stdout)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: dict, field: str) -> str:
    clone = dict(value)
    clone.pop(field, None)
    encoded = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class CompatibilityImportFixture:
    def __init__(self, root: Path):
        self.root = root
        source = root / "source.pdf"
        source.write_bytes(b"source")
        self.state = root / "evaluation-state.json"
        run_cli(
            "state_cli.py", "init", "--output", self.state,
            "--evaluation-id", "EVAL-IMPORT", "--source-title", "Example",
            "--source-file", source, "--document-page-start", 1,
            "--document-page-end", 1, "--intended-readership", "scholars",
        )
        source_sha = json.loads(self.state.read_text())["source"]["sha256"]

        self.page_map = root / "source" / "page-map.json"
        page_map = {
            "schema_version": "page-map-v1", "source_sha256": source_sha,
            "document_page_count": 1, "document_page_basis": "one_based_inclusive",
            "pages": [{
                "document_page": 1, "source_page_label": "1", "normalized_locator_key": "1",
                "label_style": "arabic", "mapping_id": "MAP-1",
                "in_evaluation_scope": True, "accepts_index_locators": True,
            }],
            "validation": {"all_document_pages_covered": True, "unique_indexable_locator_keys": True},
        }
        page_map["page_map_sha256"] = canonical_hash(page_map, "page_map_sha256")
        write_json(self.page_map, page_map)
        run_cli("state_cli.py", "set-stage", "--state", self.state, "--stage", "page_mapping", "--status", "completed", "--artifact-path", self.page_map)

        self.manifest = root / "source" / "chunk-manifest.json"
        manifest = {
            "schema_version": "chunk-manifest-v1", "document_page_basis": "one_based_inclusive",
            "page_map_sha256": page_map["page_map_sha256"], "user_approved": True,
            "require_full_scope_coverage": True,
            "chunks": [{
                "chunk_id": "CHUNK-001", "title": "Chapter", "source_units": ["Chapter"],
                "owned_document_page_ranges": [[1, 1]], "context_document_page_ranges": [], "packet_order": 1,
            }],
            "validation": {"owned_pages_unique": True, "scope_coverage_complete": True},
        }
        manifest["chunk_manifest_sha256"] = canonical_hash(manifest, "chunk_manifest_sha256")
        write_json(self.manifest, manifest)
        run_cli("state_cli.py", "set-stage", "--state", self.state, "--stage", "chunk_definition", "--status", "completed", "--artifact-path", self.manifest)

        policy_input = root / "source" / "policy-input.json"
        write_json(policy_input, {
            "schema_version": "subject-index-policy-build-input-v1", "policy_id": "POLICY-V8",
            "source_scope": {
                "source_sha256": source_sha, "document_page_span": [1, 1],
                "page_map_sha256": page_map["page_map_sha256"],
                "chunk_manifest_sha256": manifest["chunk_manifest_sha256"], "availability": {},
            },
            "audience": {"label": "scholars", "basis": "inferred", "confidence": "medium", "rationale": "Test."},
            "audit_design": {"mode": "full", "candidate_blindness": "required"}, "deviations": [],
        })
        self.policy = root / "source" / "evaluation-policy.v4.json"
        run_cli("policy_cli.py", "build", "--input", policy_input, "--output", self.policy)
        run_cli("state_cli.py", "set-stage", "--state", self.state, "--stage", "define_policy", "--status", "completed", "--artifact-path", self.policy)
        prepared = root / "source" / "prepared.json"
        write_json(prepared, {"schema_version": "prepared-v1"})
        run_cli("state_cli.py", "set-stage", "--state", self.state, "--stage", "source_chunk_preparation", "--status", "completed", "--artifact-path", prepared)

        legacy = root / "legacy"
        self.legacy_page_map = legacy / "page-map.json"
        self.legacy_manifest = legacy / "chunk-manifest.json"
        self.legacy_page_map.parent.mkdir(parents=True)
        self.legacy_page_map.write_bytes(self.page_map.read_bytes())
        self.legacy_manifest.write_bytes(self.manifest.read_bytes())
        current_policy = json.loads(self.policy.read_text())
        legacy_policy = deepcopy(current_policy)
        legacy_policy["schema_version"] = "subject-index-evaluation-policy-v2"
        legacy_policy["policy_id"] = "POLICY-LEGACY"
        legacy_policy["policy_sha256"] = canonical_hash(legacy_policy, "policy_sha256")
        self.legacy_policy = legacy / "evaluation-policy.v2.json"
        write_json(self.legacy_policy, legacy_policy)

        benchmark = {
            "schema_version": "source-subject-benchmark-v2", "benchmark_id": "BENCH-LEGACY", "version": 3,
            "evaluation_id": "EVAL-IMPORT", "source_sha256": source_sha,
            "policy_sha256": legacy_policy["policy_sha256"], "page_map_sha256": page_map["page_map_sha256"],
            "chunk_manifest_sha256": manifest["chunk_manifest_sha256"], "candidate_blindness": "preserved",
            "subjects": [{
                "subject_id": "SUBJ-1", "label": "Subject", "priority": "essential", "meaning": "Meaning",
                "stance": "Stance", "acceptable_access": ["Subject"],
                "evidence": [{"evidence_id": "EVID-1", "document_page": 1, "locator_class": "principal"}],
            }],
            "relationships": [{
                "relationship_id": "REL-1", "source_subject_id": "SUBJ-1", "target_subject_id": "SUBJ-1",
                "type": "self", "resolution_status": "resolved", "descriptions": ["preserve me"],
            }],
            "reader_tasks": [{"task_id": "TASK-1", "question": "What?", "subject_ids": ["SUBJ-1"]}],
            "freeze": {"frozen_at": "2026-01-01T00:00:00Z", "synthesis_pass_complete": True, "page_coverage_complete": True},
        }
        benchmark["benchmark_sha256"] = canonical_hash(benchmark, "benchmark_sha256")
        self.legacy_benchmark = legacy / "source-benchmark.v3.json"
        write_json(self.legacy_benchmark, benchmark)

        draft = {"version": 1, "file_sha256": "1" * 64, "canonical_sha256": "2" * 64}
        queues = {
            "subject_ids": ["SUBJ-1"], "relationship_ids": ["REL-1"], "reader_task_ids": ["TASK-1"],
            "cross_chapter_subject_ids": [], "unresolved_relationship_ids": [], "fallback_reader_task_ids": [],
        }
        self.inventory = legacy / "review-inventory.json"
        write_json(self.inventory, {
            "schema_version": "source-benchmark-review-inventory-v1", "evaluation_id": "EVAL-IMPORT",
            "draft": draft, "queues": queues,
        })
        self.review = legacy / "review.json"
        write_json(self.review, {
            "schema_version": "source-benchmark-review-v1", "evaluation_id": "EVAL-IMPORT", "review_mode": "full",
            "candidate_blindness": "preserved",
            "reviewer_independence": {"fresh_context": True, "candidate_unseen": True, "source_reconnected_sha256": source_sha},
            "draft": draft,
            "coverage": {
                "subject_ids_reviewed": ["SUBJ-1"], "relationship_ids_reviewed": ["REL-1"],
                "reader_task_ids_reviewed": ["TASK-1"], "cross_chapter_subject_ids_reviewed": [],
                "unresolved_relationship_ids_dispositioned": [], "fallback_reader_task_ids_reviewed": [],
            },
            "completion": {
                "structural_validation_passed": True, "editorial_review_complete": True,
                "source_first_omission_review_complete": True, "candidate_blindness_preserved": True,
                "no_unreviewed_required_items": True, "public_claims_allowed": True,
            },
            "recommendation": "approve_revised",
            "proposed_final": {"version": 3, "file_sha256": file_hash(self.legacy_benchmark), "canonical_sha256": benchmark["benchmark_sha256"]},
        })

        self.legacy_state = legacy / "evaluation-state.json"
        legacy_artifacts = [
            ("define_policy", self.legacy_policy), ("page_mapping", self.legacy_page_map),
            ("chunk_definition", self.legacy_manifest), ("benchmark_review", self.inventory),
            ("benchmark_review", self.review), ("benchmark_freeze", self.legacy_benchmark),
        ]
        write_json(self.legacy_state, {
            "schema_version": "subject-index-evaluation-state-v4", "evaluation_id": "EVAL-IMPORT",
            "source": {"sha256": source_sha}, "candidate": None,
            "stages": {name: {"status": "completed"} for name in (
                "source_subject_discovery", "benchmark_synthesis", "benchmark_review", "benchmark_freeze",
            )},
            "artifacts": [{"stage": stage, "sha256": file_hash(path)} for stage, path in legacy_artifacts],
            "benchmark_workflow": {
                "final_benchmark": {"file_sha256": file_hash(self.legacy_benchmark), "canonical_sha256": benchmark["benchmark_sha256"]},
                "candidate_blindness": "preserved", "merge_gate": "blocked_systemic_defect_revealed",
            },
        })

        self.output = root / "benchmark" / "source-benchmark.v8.json"
        self.provenance = root / "benchmark" / "source-benchmark.import-provenance.json"
        output = deepcopy(benchmark)
        output["relationships"][0]["relationship_type"] = output["relationships"][0].pop("type")
        output.update({
            "benchmark_id": "BENCH-V8", "version": 4, "evaluation_id": "EVAL-IMPORT",
            "policy_sha256": current_policy["policy_sha256"],
            "freeze": {"frozen_at": "2026-09-13T12:00:00Z", "synthesis_pass_complete": True, "page_coverage_complete": True},
            "compatibility_import": {
                "operation": "reviewed_legacy_benchmark_compatibility_import", "approval_id": "APPROVAL-1",
                "legacy_benchmark_file_sha256": file_hash(self.legacy_benchmark),
                "legacy_benchmark_sha256": benchmark["benchmark_sha256"], "legacy_artifact_freeze_commit": "9" * 40,
                "normalization": ["relationships[*].type->relationship_type"],
                "policy_rebinding": {"from": legacy_policy["policy_sha256"], "to": current_policy["policy_sha256"]},
                "no_discovery_or_editorial_review_rerun": True,
            },
        })
        output["benchmark_sha256"] = canonical_hash(output, "benchmark_sha256")
        self.approval = root / "approval.json"
        write_json(self.approval, {
            "schema_version": "source-benchmark-compatibility-approval-v1", "approval_id": "APPROVAL-1",
            "approved_at": "2026-09-13T11:00:00Z",
            "reviewer_attestation": {
                "reviewer_id": "reviewer@example", "candidate_unseen": True, "legacy_full_review_verified": True,
                "normalization_semantics_preserving": True, "policy_rebinding_compatible": True,
                "no_new_editorial_review_claimed": True,
            },
            "legacy": {
                "evaluation_id": "EVAL-IMPORT", "source_sha256": source_sha, "benchmark_id": "BENCH-LEGACY", "version": 3,
                "benchmark_file_sha256": file_hash(self.legacy_benchmark), "benchmark_sha256": benchmark["benchmark_sha256"],
                "policy_file_sha256": file_hash(self.legacy_policy), "policy_sha256": legacy_policy["policy_sha256"],
                "page_map_file_sha256": file_hash(self.legacy_page_map), "page_map_sha256": page_map["page_map_sha256"],
                "chunk_manifest_file_sha256": file_hash(self.legacy_manifest), "chunk_manifest_sha256": manifest["chunk_manifest_sha256"],
                "review_file_sha256": file_hash(self.review), "review_inventory_file_sha256": file_hash(self.inventory),
                "state_file_sha256": file_hash(self.legacy_state), "artifact_freeze_commit": "9" * 40,
            },
            "current": {
                "evaluation_id": "EVAL-IMPORT", "source_sha256": source_sha, "benchmark_id": "BENCH-V8", "version": 4,
                "policy_file_sha256": file_hash(self.policy), "policy_sha256": current_policy["policy_sha256"],
                "page_map_file_sha256": file_hash(self.page_map), "page_map_sha256": page_map["page_map_sha256"],
                "chunk_manifest_file_sha256": file_hash(self.manifest), "chunk_manifest_sha256": manifest["chunk_manifest_sha256"],
                "frozen_at": "2026-09-13T12:00:00Z", "benchmark_sha256": output["benchmark_sha256"],
            },
            "allowed_changes": [
                "relationships[*].type->relationship_type", "benchmark_id", "version", "evaluation_id",
                "policy_sha256", "freeze", "compatibility_import", "benchmark_sha256",
            ],
        })

    def arguments(self) -> tuple[object, ...]:
        return (
            "import-reviewed-legacy", "--state", self.state, "--page-map", self.page_map,
            "--chunk-manifest", self.manifest, "--policy", self.policy, "--legacy-state", self.legacy_state,
            "--legacy-page-map", self.legacy_page_map, "--legacy-chunk-manifest", self.legacy_manifest,
            "--legacy-policy", self.legacy_policy, "--legacy-benchmark", self.legacy_benchmark,
            "--legacy-review-inventory", self.inventory, "--legacy-review", self.review,
            "--compatibility-approval", self.approval, "--output", self.output,
            "--provenance-output", self.provenance,
        )

    def make_native_v8(self) -> None:
        source_evaluation_id = "EVAL-NATIVE-SOURCE"
        current_policy = json.loads(self.policy.read_text())
        self.legacy_policy.write_bytes(self.policy.read_bytes())

        draft = json.loads(self.legacy_benchmark.read_text())
        draft.update({
            "schema_version": "source-subject-benchmark-draft-v1",
            "benchmark_id": "BENCH-NATIVE-SOURCE", "version": 1,
            "evaluation_id": source_evaluation_id,
            "policy_sha256": current_policy["policy_sha256"],
            "synthesis": {
                "whole_source_pass_complete": True,
                "all_chunk_artifacts_reconciled": True,
                "candidate_unseen": True,
            },
        })
        draft["relationships"][0]["relationship_type"] = draft["relationships"][0].pop("type")
        draft["relationships"][0]["resolution_status"] = "unresolved"
        draft.pop("freeze")
        draft.pop("benchmark_sha256")
        self.legacy_draft = self.legacy_benchmark.parent / "source-benchmark.draft.v1.json"
        write_json(self.legacy_draft, draft)

        benchmark = deepcopy(draft)
        benchmark.update({
            "schema_version": "source-subject-benchmark-v2", "version": 2,
            "freeze": {
                "frozen_at": "2026-01-01T00:00:00Z",
                "synthesis_pass_complete": True,
                "page_coverage_complete": True,
                "review_mode": "full", "review_recommendation": "approve_revised",
                "candidate_blindness": "preserved",
                "source_reconnected_sha256": benchmark["source_sha256"],
            },
        })
        benchmark.pop("synthesis")
        benchmark["relationships"][0]["resolution_status"] = "resolved"
        benchmark["benchmark_sha256"] = canonical_hash(benchmark, "benchmark_sha256")
        write_json(self.legacy_benchmark, benchmark)

        run_cli("benchmark_review_cli.py", "screen", "--draft", self.legacy_draft, "--output", self.inventory)
        inventory = json.loads(self.inventory.read_text())
        inventory["draft"] = {
            "path": self.legacy_draft.name, "version": 1,
            "file_sha256": file_hash(self.legacy_draft),
            "canonical_sha256": canonical_hash(draft, "benchmark_sha256"),
            "candidate_blindness": "preserved",
        }
        write_json(self.inventory, inventory)
        write_json(self.review, {
            "schema_version": "source-benchmark-review-v1", "evaluation_id": source_evaluation_id,
            "review_mode": "full", "candidate_blindness": "preserved",
            "reviewer_independence": {
                "fresh_context": True, "candidate_unseen": True,
                "source_reconnected_sha256": benchmark["source_sha256"],
            },
            "draft": {
                "path": str(self.legacy_draft), "version": 1,
                "file_sha256": file_hash(self.legacy_draft),
                "canonical_sha256": canonical_hash(draft, "benchmark_sha256"),
            },
            "coverage": {
                "subject_ids_reviewed": ["SUBJ-1"], "relationship_ids_reviewed": ["REL-1"],
                "reader_task_ids_reviewed": ["TASK-1"], "cross_chapter_subject_ids_reviewed": [],
                "unresolved_relationship_ids_dispositioned": ["REL-1"],
                "fallback_reader_task_ids_reviewed": [],
            },
            "changes": {
                "merges": [], "splits": [], "priority_changes": [],
                "relationship_changes": [{"relationship_id": "REL-1"}],
                "reader_task_changes": [], "subjects_added": [], "subjects_removed": [],
                "terminology_changes": [],
            },
            "remaining_issues": [],
            "completion": {
                "structural_validation_passed": True, "editorial_review_complete": True,
                "source_first_omission_review_complete": True, "candidate_blindness_preserved": True,
                "no_unreviewed_required_items": True, "public_claims_allowed": True,
            },
            "recommendation": "approve_revised",
        })
        legacy_discovery = self.legacy_benchmark.parent / "source-subject-chunk.json"
        write_json(legacy_discovery, {"schema_version": "source-subject-chunk-v1"})

        native_state = json.loads(self.state.read_text())
        native_state["evaluation_id"] = source_evaluation_id
        native_state["configuration"]["scoring_identity"]["dimension_calculation_profile"] = "subject-index-dimension-calculation-v4"
        for stage in ("source_subject_discovery", "benchmark_synthesis", "benchmark_review", "benchmark_freeze"):
            native_state["stages"][stage] = {
                "status": "completed", "updated_at": "2026-01-01T00:00:00Z", "notes": ["Historical fixture."],
            }
        for stage, path, artifact_type, schema_version in (
            ("source_subject_discovery", legacy_discovery, "source_subject_chunk", "source-subject-chunk-v1"),
            ("benchmark_synthesis", self.legacy_draft, "source_benchmark_draft", draft["schema_version"]),
            ("benchmark_review", self.inventory, "source_benchmark_review_inventory", inventory["schema_version"]),
            ("benchmark_review", self.review, "source_benchmark_review", "source-benchmark-review-v1"),
            ("benchmark_freeze", self.legacy_benchmark, "source_benchmark", benchmark["schema_version"]),
        ):
            digest = file_hash(path)
            native_state["artifacts"].append({
                "artifact_id": f"ART-{digest[:12].upper()}", "stage": stage,
                "artifact_type": artifact_type, "path": path.name, "sha256": digest,
                "media_type": "application/json", "schema_version": schema_version,
                "visibility": "private", "retention": "required", "frozen": True,
                "recorded_at": "2026-01-01T00:00:00Z",
            })
        native_state["artifacts"].sort(key=lambda item: item["path"])
        write_json(self.legacy_state, native_state)

        output = deepcopy(benchmark)
        output.update({
            "benchmark_id": "BENCH-V8", "version": 3, "evaluation_id": "EVAL-IMPORT",
            "freeze": {
                "frozen_at": "2026-09-13T12:00:00Z",
                "synthesis_pass_complete": True,
                "page_coverage_complete": True,
            },
            "compatibility_import": {
                "operation": "reviewed_legacy_benchmark_compatibility_import",
                "approval_id": "APPROVAL-NATIVE", "reuse_mode": "native_v8_exact",
                "legacy_benchmark_file_sha256": file_hash(self.legacy_benchmark),
                "legacy_benchmark_sha256": benchmark["benchmark_sha256"],
                "legacy_state_file_sha256": file_hash(self.legacy_state),
                "policy_identity": current_policy["policy_sha256"],
                "normalization": [],
                "release_transport": {
                    "kind": "portable_checkpoint", "checkpoint_file_sha256": "8" * 64,
                    "checkpoint_state_file_sha256": file_hash(self.legacy_state),
                },
                "no_discovery_or_editorial_review_rerun": True,
            },
        })
        output["benchmark_sha256"] = canonical_hash(output, "benchmark_sha256")
        write_json(self.approval, {
            "schema_version": "source-benchmark-compatibility-approval-v1",
            "reuse_mode": "native_v8_exact", "approval_id": "APPROVAL-NATIVE",
            "approved_at": "2026-09-13T11:00:00Z",
            "reviewer_attestation": {
                "reviewer_id": "reviewer@example", "candidate_unseen": True,
                "legacy_full_review_verified": True, "exact_native_v8_reuse_verified": True,
                "same_policy_identity_verified": True, "no_semantic_normalization_required": True,
                "no_new_editorial_review_claimed": True,
            },
            "legacy": {
                "evaluation_id": source_evaluation_id, "source_sha256": benchmark["source_sha256"],
                "benchmark_id": benchmark["benchmark_id"], "version": benchmark["version"],
                "benchmark_file_sha256": file_hash(self.legacy_benchmark),
                "benchmark_sha256": benchmark["benchmark_sha256"],
                "policy_file_sha256": file_hash(self.legacy_policy),
                "policy_sha256": current_policy["policy_sha256"],
                "page_map_file_sha256": file_hash(self.legacy_page_map),
                "page_map_sha256": benchmark["page_map_sha256"],
                "chunk_manifest_file_sha256": file_hash(self.legacy_manifest),
                "chunk_manifest_sha256": benchmark["chunk_manifest_sha256"],
                "review_file_sha256": file_hash(self.review),
                "review_inventory_file_sha256": file_hash(self.inventory),
                "state_file_sha256": file_hash(self.legacy_state),
                "draft_file_sha256": file_hash(self.legacy_draft),
                "draft_canonical_sha256": canonical_hash(draft, "benchmark_sha256"),
            },
            "current": {
                "evaluation_id": "EVAL-IMPORT", "source_sha256": benchmark["source_sha256"],
                "benchmark_id": "BENCH-V8", "version": 3,
                "policy_file_sha256": file_hash(self.policy),
                "policy_sha256": current_policy["policy_sha256"],
                "page_map_file_sha256": file_hash(self.page_map),
                "page_map_sha256": benchmark["page_map_sha256"],
                "chunk_manifest_file_sha256": file_hash(self.manifest),
                "chunk_manifest_sha256": benchmark["chunk_manifest_sha256"],
                "frozen_at": "2026-09-13T12:00:00Z",
                "benchmark_sha256": output["benchmark_sha256"],
            },
            "release_transport": {
                "kind": "portable_checkpoint", "checkpoint_file_sha256": "8" * 64,
                "checkpoint_state_file_sha256": file_hash(self.legacy_state),
            },
            "allowed_changes": [
                "benchmark_id", "version", "evaluation_id", "freeze", "compatibility_import", "benchmark_sha256",
            ],
        })

    def native_arguments(self) -> tuple[object, ...]:
        return (*self.arguments(), "--legacy-draft", self.legacy_draft)

    def update_native_bindings(self, *paths: Path) -> None:
        approval = json.loads(self.approval.read_text())
        state = json.loads(self.legacy_state.read_text())
        field_by_path = {
            self.inventory: "review_inventory_file_sha256",
            self.review: "review_file_sha256",
            self.legacy_benchmark: "benchmark_file_sha256",
        }
        stage_by_path = {
            self.inventory: "benchmark_review", self.review: "benchmark_review",
            self.legacy_benchmark: "benchmark_freeze",
        }
        for path in paths:
            digest = file_hash(path)
            approval["legacy"][field_by_path[path]] = digest
            for artifact in state["artifacts"]:
                if artifact.get("stage") == stage_by_path[path] and artifact.get("path") == path.name:
                    artifact["sha256"] = digest
                    artifact["artifact_id"] = f"ART-{digest[:12].upper()}"
        write_json(self.legacy_state, state)
        approval["legacy"]["state_file_sha256"] = file_hash(self.legacy_state)
        approval["release_transport"]["checkpoint_state_file_sha256"] = file_hash(self.legacy_state)
        write_json(self.approval, approval)


class CompatibilityImportTests(unittest.TestCase):
    def test_success_registers_imported_provenance_and_four_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CompatibilityImportFixture(Path(temporary))
            result = run_cli("benchmark_review_cli.py", *fixture.arguments())
            self.assertTrue(result["ok"])
            state = json.loads(fixture.state.read_text())
            for stage in ("source_subject_discovery", "benchmark_synthesis", "benchmark_review", "benchmark_freeze"):
                self.assertEqual("completed", state["stages"][stage]["status"])
                self.assertIn("not rerun", " ".join(state["stages"][stage]["notes"]))
            benchmark = json.loads(fixture.output.read_text())
            self.assertEqual("self", benchmark["relationships"][0]["relationship_type"])
            self.assertNotIn("type", benchmark["relationships"][0])
            self.assertEqual("preserved", benchmark["candidate_blindness"])
            self.assertEqual("candidate_normalization", result["next_actions"][0]["stage"])

    def test_native_v8_success_reuses_same_policy_without_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CompatibilityImportFixture(Path(temporary))
            fixture.make_native_v8()
            result = run_cli("benchmark_review_cli.py", *fixture.native_arguments())
            self.assertTrue(result["ok"])
            self.assertEqual(file_hash(fixture.legacy_state), result["legacy_state_file_sha256"])
            benchmark = json.loads(fixture.output.read_text())
            self.assertIn("relationship_type", benchmark["relationships"][0])
            self.assertNotIn("type", benchmark["relationships"][0])
            self.assertEqual("native_v8_exact", benchmark["compatibility_import"]["reuse_mode"])
            self.assertEqual([], benchmark["compatibility_import"]["normalization"])
            provenance = json.loads(fixture.provenance.read_text())
            self.assertEqual("native_v8_exact", provenance["reuse_mode"])
            self.assertEqual([], provenance["normalization"]["operations"])
            self.assertEqual(0, provenance["normalization"]["relationships_normalized"])

    def test_native_v8_tampering_writes_nothing(self) -> None:
        for mutation, expected in (
            ("inventory", "deterministic recomputation"),
            ("review", "incomplete coverage"),
            ("blocking_issue", "retains a blocking issue"),
            ("relationship", "must contain relationship_type"),
            ("freeze", "freeze.review_recommendation"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                fixture = CompatibilityImportFixture(Path(temporary))
                fixture.make_native_v8()
                if mutation == "inventory":
                    inventory = json.loads(fixture.inventory.read_text())
                    inventory["diagnostics"]["warnings"].append("tampered")
                    write_json(fixture.inventory, inventory)
                    fixture.update_native_bindings(fixture.inventory)
                elif mutation == "review":
                    review = json.loads(fixture.review.read_text())
                    review["coverage"]["subject_ids_reviewed"] = []
                    write_json(fixture.review, review)
                    fixture.update_native_bindings(fixture.review)
                elif mutation == "blocking_issue":
                    review = json.loads(fixture.review.read_text())
                    review["remaining_issues"] = [{"blocking": True}]
                    write_json(fixture.review, review)
                    fixture.update_native_bindings(fixture.review)
                elif mutation == "relationship":
                    benchmark = json.loads(fixture.legacy_benchmark.read_text())
                    benchmark["relationships"][0]["type"] = benchmark["relationships"][0].pop("relationship_type")
                    benchmark["benchmark_sha256"] = canonical_hash(benchmark, "benchmark_sha256")
                    write_json(fixture.legacy_benchmark, benchmark)
                    fixture.update_native_bindings(fixture.legacy_benchmark)
                else:
                    benchmark = json.loads(fixture.legacy_benchmark.read_text())
                    benchmark["freeze"]["review_recommendation"] = "retain_draft"
                    benchmark["benchmark_sha256"] = canonical_hash(benchmark, "benchmark_sha256")
                    write_json(fixture.legacy_benchmark, benchmark)
                    fixture.update_native_bindings(fixture.legacy_benchmark)
                state_before = fixture.state.read_bytes()
                result = run_cli("benchmark_review_cli.py", *fixture.native_arguments(), ok=False)
                self.assertTrue(any(expected in error for error in result["errors"]))
                self.assertEqual(state_before, fixture.state.read_bytes())
                self.assertFalse(fixture.output.exists())
                self.assertFalse(fixture.provenance.exists())

    def test_native_v8_requires_same_policy_source_only_state_and_draft(self) -> None:
        for mutation, expected in (
            ("policy", "byte-identical"),
            ("candidate", "candidate"),
            ("missing_draft", "requires --legacy-draft"),
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                fixture = CompatibilityImportFixture(Path(temporary))
                fixture.make_native_v8()
                arguments = fixture.native_arguments()
                if mutation == "policy":
                    policy = json.loads(fixture.legacy_policy.read_text())
                    policy["policy_id"] = "OTHER"
                    policy["policy_sha256"] = canonical_hash(policy, "policy_sha256")
                    write_json(fixture.legacy_policy, policy)
                elif mutation == "candidate":
                    state = json.loads(fixture.legacy_state.read_text())
                    state["candidate"] = {"candidate_id": "EXPOSED"}
                    write_json(fixture.legacy_state, state)
                    approval = json.loads(fixture.approval.read_text())
                    approval["legacy"]["state_file_sha256"] = file_hash(fixture.legacy_state)
                    approval["release_transport"]["checkpoint_state_file_sha256"] = file_hash(fixture.legacy_state)
                    write_json(fixture.approval, approval)
                else:
                    arguments = fixture.arguments()
                state_before = fixture.state.read_bytes()
                result = run_cli("benchmark_review_cli.py", *arguments, ok=False)
                self.assertTrue(any(expected in error.lower() for error in result["errors"]))
                self.assertEqual(state_before, fixture.state.read_bytes())
                self.assertFalse(fixture.output.exists())

    def test_incomplete_review_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CompatibilityImportFixture(Path(temporary))
            review = json.loads(fixture.review.read_text())
            review["coverage"]["subject_ids_reviewed"] = []
            write_json(fixture.review, review)
            state_before = fixture.state.read_bytes()
            result = run_cli("benchmark_review_cli.py", *fixture.arguments(), ok=False)
            self.assertTrue(any("incomplete" in error for error in result["errors"]))
            self.assertEqual(state_before, fixture.state.read_bytes())
            self.assertFalse(fixture.output.exists())
            self.assertFalse(fixture.provenance.exists())

    def test_candidate_exposure_or_ambiguous_normalization_writes_nothing(self) -> None:
        for mutation, expected in (("candidate", "candidate exposure"), ("relationship", "exactly one legacy type key")):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                fixture = CompatibilityImportFixture(Path(temporary))
                if mutation == "candidate":
                    state = json.loads(fixture.state.read_text())
                    state["artifacts"].append({
                        "artifact_id": "ART-000000000000", "stage": "candidate_normalization",
                        "artifact_type": "candidate_index", "path": "candidate.json", "sha256": "0" * 64,
                        "media_type": "application/json", "visibility": "private", "retention": "required",
                        "frozen": True, "recorded_at": "2026-01-01T00:00:00Z",
                    })
                    write_json(fixture.state, state)
                else:
                    benchmark = json.loads(fixture.legacy_benchmark.read_text())
                    benchmark["relationships"][0]["relationship_type"] = "self"
                    write_json(fixture.legacy_benchmark, benchmark)
                before = fixture.state.read_bytes()
                result = run_cli("benchmark_review_cli.py", *fixture.arguments(), ok=False)
                self.assertTrue(any(expected in error for error in result["errors"]))
                self.assertEqual(before, fixture.state.read_bytes())
                self.assertFalse(fixture.output.exists())

    def test_identity_hash_mismatch_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CompatibilityImportFixture(Path(temporary))
            benchmark = json.loads(fixture.legacy_benchmark.read_text())
            benchmark["benchmark_sha256"] = "0" * 64
            write_json(fixture.legacy_benchmark, benchmark)
            before = fixture.state.read_bytes()
            result = run_cli("benchmark_review_cli.py", *fixture.arguments(), ok=False)
            self.assertTrue(any("does not recompute" in error for error in result["errors"]))
            self.assertEqual(before, fixture.state.read_bytes())
            self.assertFalse(fixture.output.exists())

    def test_legacy_state_evaluation_identity_mismatch_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CompatibilityImportFixture(Path(temporary))
            legacy_state = json.loads(fixture.legacy_state.read_text())
            legacy_state["evaluation_id"] = "EVAL-OTHER"
            write_json(fixture.legacy_state, legacy_state)
            approval = json.loads(fixture.approval.read_text())
            approval["legacy"]["state_file_sha256"] = file_hash(fixture.legacy_state)
            write_json(fixture.approval, approval)
            before = fixture.state.read_bytes()
            result = run_cli("benchmark_review_cli.py", *fixture.arguments(), ok=False)
            self.assertTrue(any("Legacy state evaluation_id" in error for error in result["errors"]))
            self.assertEqual(before, fixture.state.read_bytes())
            self.assertFalse(fixture.output.exists())

    def test_atomic_write_cleanup_preserves_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = CompatibilityImportFixture(Path(temporary))
            blocked_parent = fixture.root / "blocked"
            blocked_parent.write_text("not a directory")
            fixture.output = blocked_parent / "source-benchmark.json"
            before = fixture.state.read_bytes()
            result = run_cli("benchmark_review_cli.py", *fixture.arguments(), ok=False)
            self.assertEqual("atomic_write_failed", result["error"]["code"])
            self.assertEqual(before, fixture.state.read_bytes())
            self.assertEqual("not a directory", blocked_parent.read_text())
            self.assertFalse(fixture.provenance.exists())


if __name__ == "__main__":
    unittest.main()
