from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_cli(script: str, *arguments: object, ok: bool = True) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *(str(value) for value in arguments)],
        text=True,
        capture_output=True,
        check=False,
    )
    if ok and result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    if not ok and result.returncode == 0:
        raise AssertionError("Command unexpectedly succeeded: " + result.stdout)
    return json.loads(result.stdout)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def benchmark_hash(value: dict) -> str:
    clone = dict(value)
    clone.pop("benchmark_sha256", None)
    encoded = json.dumps(clone, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class BenchmarkFreezeFixture:
    def __init__(self, root: Path):
        self.root = root
        source = root / "source.pdf"
        source.write_bytes(b"source")
        self.state_path = root / "evaluation-state.json"
        run_cli(
            "state_cli.py", "init", "--output", self.state_path,
            "--evaluation-id", "EVAL-FREEZE", "--source-title", "Example",
            "--source-file", source, "--document-page-start", 1,
            "--document-page-end", 3, "--intended-readership", "scholars",
        )
        source_sha256 = json.loads(self.state_path.read_text())["source"]["sha256"]
        identities = {
            "page_mapping": {"page_map_sha256": "b" * 64},
            "chunk_definition": {"chunk_manifest_sha256": "c" * 64},
            "define_policy": {"policy_sha256": "a" * 64},
            "source_chunk_preparation": {},
            "source_subject_discovery": {},
        }
        for stage, identity in identities.items():
            path = root / f"{stage}.json"
            write_json(path, {"schema_version": f"{stage}-v1", **identity})
            run_cli(
                "state_cli.py", "set-stage", "--state", self.state_path,
                "--stage", stage, "--status", "completed", "--artifact-path", path,
            )

        self.draft_path = root / "benchmark" / "source-benchmark.draft.v1.json"
        draft = {
            "schema_version": "source-subject-benchmark-draft-v1",
            "benchmark_id": "BENCH-1", "version": 1,
            "evaluation_id": "EVAL-FREEZE", "source_sha256": source_sha256,
            "policy_sha256": "a" * 64, "page_map_sha256": "b" * 64,
            "chunk_manifest_sha256": "c" * 64, "candidate_blindness": "preserved",
            "subjects": [{
                "subject_id": "SUBJ-1", "label": "A subject", "priority": "essential",
                "meaning": "Meaning", "stance": "Stance", "acceptable_access": ["A subject"],
                "evidence": [{
                    "evidence_id": "EVID-1", "document_page": 1,
                    "locator_class": "principal",
                }],
                "chapter_provenance": ["chapter-1", "chapter-2"],
            }],
            "relationships": [{
                "relationship_id": "REL-1", "source_subject_id": "SUBJ-1",
                "target_subject_id": "SUBJ-1", "relationship_type": "self",
                "resolution_status": "unresolved",
            }],
            "reader_tasks": [{
                "task_id": "TASK-1", "question": "What is it?",
                "subject_ids": ["SUBJ-1"], "fallback_generated": True,
            }],
            "exclusions": [], "uncertainties": [],
            "synthesis": {
                "whole_source_pass_complete": True,
                "all_chunk_artifacts_reconciled": True,
                "candidate_unseen": True,
            },
        }
        write_json(self.draft_path, draft)
        run_cli(
            "state_cli.py", "set-stage", "--state", self.state_path,
            "--stage", "benchmark_synthesis", "--status", "completed",
            "--artifact-path", self.draft_path,
        )

        self.inventory_path = root / "validation" / "source-benchmark-review-inventory.json"
        run_cli(
            "benchmark_review_cli.py", "screen", "--draft", self.draft_path,
            "--output", self.inventory_path,
        )
        inventory = json.loads(self.inventory_path.read_text())
        self.review_path = root / "validation" / "source-benchmark-review.v1.json"
        review = {
            "schema_version": "source-benchmark-review-v1",
            "evaluation_id": "EVAL-FREEZE", "review_mode": "full",
            "candidate_blindness": "preserved",
            "reviewer_independence": {
                "fresh_context": True, "candidate_unseen": True,
                "source_reconnected_sha256": source_sha256,
            },
            "draft": inventory["draft"],
            "coverage": {
                "subject_ids_reviewed": ["SUBJ-1"],
                "relationship_ids_reviewed": ["REL-1"],
                "reader_task_ids_reviewed": ["TASK-1"],
                "cross_chapter_subject_ids_reviewed": ["SUBJ-1"],
                "unresolved_relationship_ids_dispositioned": ["REL-1"],
                "fallback_reader_task_ids_reviewed": ["TASK-1"],
            },
            "approved_changes": [], "remaining_issues": [],
            "completion": {
                "structural_validation_passed": True,
                "editorial_review_complete": True,
                "source_first_omission_review_complete": True,
                "candidate_blindness_preserved": True,
                "no_unreviewed_required_items": True,
                "public_claims_allowed": True,
            },
            "recommendation": "retain_draft",
        }
        write_json(self.review_path, review)

        self.final_path = root / "benchmark" / "source-benchmark.v1.json"
        final = {key: value for key, value in draft.items() if key != "synthesis"}
        final["schema_version"] = "source-subject-benchmark-v2"
        final["freeze"] = {
            "frozen_at": "2026-09-09T12:00:00Z",
            "synthesis_pass_complete": True,
            "page_coverage_complete": True,
        }
        final["benchmark_sha256"] = benchmark_hash(final)
        write_json(self.final_path, final)

    def freeze_arguments(self) -> tuple[object, ...]:
        return (
            "freeze", "--state", self.state_path, "--draft", self.draft_path,
            "--inventory", self.inventory_path, "--review", self.review_path,
            "--final", self.final_path,
        )


class BenchmarkFreezeTests(unittest.TestCase):
    def test_incomplete_review_leaves_state_and_artifacts_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = BenchmarkFreezeFixture(Path(temporary))
            review = json.loads(fixture.review_path.read_text())
            review["coverage"]["subject_ids_reviewed"] = []
            write_json(fixture.review_path, review)
            paths = (
                fixture.state_path, fixture.draft_path, fixture.inventory_path,
                fixture.review_path, fixture.final_path,
            )
            before = {path: path.read_bytes() for path in paths}
            result = run_cli("benchmark_review_cli.py", *fixture.freeze_arguments(), ok=False)
            self.assertFalse(result["ok"])
            self.assertTrue(any("incomplete coverage" in error for error in result["errors"]))
            self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_invalid_final_and_generic_stage_completion_cannot_advance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = BenchmarkFreezeFixture(Path(temporary))
            final = json.loads(fixture.final_path.read_text())
            final["benchmark_sha256"] = "0" * 64
            write_json(fixture.final_path, final)
            state_before = fixture.state_path.read_bytes()
            result = run_cli("benchmark_review_cli.py", *fixture.freeze_arguments(), ok=False)
            self.assertTrue(any("does not recompute" in error for error in result["errors"]))
            self.assertEqual(state_before, fixture.state_path.read_bytes())
            generic = run_cli(
                "state_cli.py", "set-stage", "--state", fixture.state_path,
                "--stage", "benchmark_review", "--status", "completed",
                "--artifact-path", fixture.review_path, ok=False,
            )
            self.assertEqual("typed_transition_required", generic["error"]["code"])

    def test_unapproved_semantic_change_cannot_advance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = BenchmarkFreezeFixture(Path(temporary))
            final = json.loads(fixture.final_path.read_text())
            final["version"] = 2
            final["subjects"][0]["label"] = "Changed without ledger approval"
            final["benchmark_sha256"] = benchmark_hash(final)
            write_json(fixture.final_path, final)
            review = json.loads(fixture.review_path.read_text())
            review["recommendation"] = "approve_revised"
            write_json(fixture.review_path, review)
            state_before = fixture.state_path.read_bytes()
            result = run_cli("benchmark_review_cli.py", *fixture.freeze_arguments(), ok=False)
            self.assertTrue(any("approved_changes" in error for error in result["errors"]))
            self.assertEqual(state_before, fixture.state_path.read_bytes())

    def test_valid_freeze_registers_review_and_final_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = BenchmarkFreezeFixture(Path(temporary))
            result = run_cli("benchmark_review_cli.py", *fixture.freeze_arguments())
            self.assertTrue(result["ok"])
            state = json.loads(fixture.state_path.read_text())
            self.assertEqual("completed", state["stages"]["benchmark_review"]["status"])
            self.assertEqual("completed", state["stages"]["benchmark_freeze"]["status"])
            types = {item["artifact_type"] for item in state["artifacts"]}
            self.assertIn("source_benchmark_review", types)
            self.assertIn("source_benchmark", types)
            self.assertNotIn("source_benchmark_review_inventory", types)
            self.assertEqual("candidate_normalization", result["next_actions"][0]["stage"])


if __name__ == "__main__":
    unittest.main()
