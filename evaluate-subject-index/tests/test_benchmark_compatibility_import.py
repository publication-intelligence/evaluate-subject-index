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
                "candidate_blindness": "preserved", "release_status": "benchmark_frozen_final",
                "artifact_freeze_commit": "9" * 40, "merge_gate": "cleared_after_review",
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


if __name__ == "__main__":
    unittest.main()
