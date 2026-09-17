from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def help_text(script: str, *arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *arguments, "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


class CurrentCommandSurfaceTests(unittest.TestCase):
    def test_current_documentation_exposes_only_v10_dispatcher(self) -> None:
        current_docs = [
            ROOT.parent / "README.md",
            ROOT / "SKILL.md",
            ROOT / "references" / "workflow.md",
            ROOT / "references" / "benchmark-review.md",
            ROOT / "references" / "study-comparison.md",
            ROOT / "references" / "storage-and-checkpoints.md",
            ROOT / "references" / "candidate-preparation.md",
        ]
        text = "\n".join(path.read_text() for path in current_docs)
        self.assertIn("scripts/v10_cli.py", text)
        for legacy_entrypoint in (
            "scripts/v9_cli.py",
            "scripts/v10_semantic_cli.py",
            "scripts/state_cli.py",
            "scripts/study_cli.py",
            "scripts/page_chunk_cli.py",
            "scripts/benchmark_review_cli.py",
            "scripts/dimension_score_v8_cli.py",
            "scripts/item_grade_v8_cli.py",
        ):
            with self.subTest(legacy_entrypoint=legacy_entrypoint):
                self.assertNotIn(legacy_entrypoint, text)

    def test_checkpoint_cli_has_no_migration_command(self) -> None:
        text = help_text("bundle_cli.py")
        self.assertIn("checkpoint", text)
        self.assertIn("import-bundle", text)
        self.assertNotIn("export-bundle", text)
        self.assertNotIn("migrate-publication-profile", text)
        checkpoint_help = help_text("bundle_cli.py", "checkpoint")
        self.assertIn("portable", checkpoint_help)
        self.assertIn("private-complete", checkpoint_help)

    def test_worker_prompt_wrapper_is_not_part_of_the_runtime(self) -> None:
        self.assertFalse((SCRIPTS / "worker_prompt_cli.py").exists())
        self.assertFalse((ROOT / "references" / "schemas" / "locator-worker-prompt-pack.schema.json").exists())

    def test_candidate_preparation_is_local(self) -> None:
        text = help_text("candidate_preparation_cli.py")
        self.assertIn("register", text)
        self.assertNotIn("extract", text)
        self.assertNotIn("bind-publication", text)
        self.assertNotIn("integrate", text)

    def test_candidate_preparation_has_no_success_only_artifact_schemas(self) -> None:
        schemas = ROOT / "references" / "schemas"
        self.assertTrue((schemas / "candidate-normalization-issues.schema.json").is_file())
        for name in (
            "candidate-ref.schema.json",
            "candidate-layout-profile.schema.json",
            "candidate-normalization-exceptions.schema.json",
            "candidate-normalization-report.schema.json",
            "candidate-normalization-qa.schema.json",
        ):
            self.assertFalse((schemas / name).exists())

    def test_locator_preparation_uses_registered_state_not_repository_locks(self) -> None:
        text = help_text("page_chunk_cli.py")
        self.assertIn("prepare-locator-chunks", text)
        self.assertNotIn("filter-candidate", text)
        source = (SCRIPTS / "page_chunk_cli.py").read_text()
        self.assertNotIn("candidate-benchmark-lock", source)
        self.assertNotIn("benchmark-lock", source)

    def test_active_v8_runtime_has_no_legacy_lock_or_rubric_v4_requirement(self) -> None:
        runtime = "\n".join(path.read_text() for path in sorted(SCRIPTS.glob("*.py")))
        current_schemas = "\n".join(
            (ROOT / "references" / "schemas" / name).read_text()
            for name in (
                "evaluation-state.schema.json",
                "locator-audit-v2.schema.json",
                "missing-access-audit.schema.json",
                "structure-audit-v6.schema.json",
                "dimension-calculation-input.schema.json",
                "dimension-calculations-v6.schema.json",
                "item-assessments-v7.schema.json",
                "evaluation-result-v12.schema.json",
                "web-report-v10.schema.json",
            )
        )
        self.assertNotIn("subject-index-rubric-v4", runtime)
        self.assertNotIn("candidate-benchmark-lock", runtime)
        self.assertNotIn("benchmark_lock_sha256", runtime)
        self.assertNotIn("benchmark_lock_sha256", current_schemas)
        self.assertFalse((ROOT / "references" / "schemas" / "candidate-benchmark-lock.schema.json").exists())

    def test_parallel_audits_require_no_github_evidence(self) -> None:
        text = help_text("parallel_candidate_audit_cli.py")
        self.assertIn("validate-audits", text)
        self.assertIn("register-audits", text)
        self.assertIn("--replace-complete-batch", help_text("parallel_candidate_audit_cli.py", "register-audits"))
        self.assertNotIn("merge-evidence", text)
        self.assertNotIn("build-locator-worker", text)

    def test_parallel_discovery_is_local(self) -> None:
        text = help_text("parallel_discovery_cli.py")
        self.assertIn("validate-discoveries", text)
        self.assertIn("register-discoveries", text)
        self.assertNotIn("worker-receipt", text)
        self.assertNotIn("integrate", text)

    def test_benchmark_review_has_narrow_legacy_import(self) -> None:
        text = help_text("benchmark_review_cli.py")
        self.assertIn("import-reviewed-legacy", text)
        import_help = help_text("benchmark_review_cli.py", "import-reviewed-legacy")
        self.assertIn("--compatibility-approval", import_help)
        self.assertIn("--legacy-review-inventory", import_help)
        self.assertIn("--provenance-output", import_help)

    def test_scoring_surface_is_current_only(self) -> None:
        text = help_text("dimension_score_v8_cli.py")
        self.assertIn("preflight", text)
        self.assertIn("calculate", text)
        self.assertNotIn("derive-structure-review", text)
        self.assertNotIn("validate-artifact", text)
        scoring_runtime = "\n".join(
            (SCRIPTS / name).read_text()
            for name in ("scoring_core.py", "dimension_score_v8_cli.py", "item_grade_v8_cli.py", "locator_utility.py", "structure_audit.py")
        )
        for forbidden in ("structure_locator_review", "migration_supplement", "locator_fit_supplement", "locator_fit_compatibility"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, scoring_runtime)
        self.assertFalse((SCRIPTS / "structure_locator_review.py").exists())
        self.assertIn("project-structure-causality", help_text("item_grade_v8_cli.py"))

    def test_policy_builder_uses_the_current_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "policy-input.json"
            output = root / "policy.json"
            source.write_text(json.dumps({
                "schema_version": "subject-index-policy-build-input-v1",
                "policy_id": "POLICY-CURRENT",
                "source_scope": {
                    "source_sha256": "a" * 64,
                    "document_page_span": [1, 10],
                    "page_map_sha256": "b" * 64,
                    "chunk_manifest_sha256": "c" * 64,
                    "availability": {},
                },
                "audience": {
                    "label": "general",
                    "basis": "inferred",
                    "confidence": "medium",
                    "rationale": "Test input.",
                },
                "audit_design": {"mode": "full", "candidate_blindness": "required"},
                "deviations": [],
            }))
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "v10_cli.py"), "policy", "build", "--input", str(source), "--output", str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            policy = json.loads(output.read_text())
            self.assertEqual("subject-index-evaluation-policy-v7", policy["schema_version"])
            self.assertEqual("subject-index-standard-policy-v10", policy["policy_profile"]["id"])
            self.assertEqual("subject-index-evaluation-v10-decision-v3", policy["v10_contract"]["contract_id"])
            self.assertEqual("779fb8ffb21bc17fe87a23ee9160a124e013a094c08280b7bdb26fef40d2da50", policy["v10_contract"]["contract_sha256"])
            self.assertTrue({"GATE-WRONG-LOCATOR", "GATE-BROKEN-REFERENCE"} <= {row["gate_id"] for row in policy["critical_gates"]})
            self.assertNotIn("standard_policy_sha256", policy["policy_profile"])

    def test_v10_is_the_only_public_runtime_and_initializes_natively(self) -> None:
        self.assertFalse((SCRIPTS / "v9_cli.py").exists())
        self.assertFalse((SCRIPTS / "v10_semantic_cli.py").exists())
        self.assertFalse((SCRIPTS / "v10_migration_cli.py").exists())
        direct_env=dict(os.environ);direct_env.pop('ESI_FROZEN_TEST_CLI',None)
        direct=subprocess.run([sys.executable,str(SCRIPTS/'policy_cli.py'),'--help'],text=True,capture_output=True,env=direct_env)
        self.assertNotEqual(0,direct.returncode)
        self.assertIn('use scripts/v10_cli.py',direct.stdout+direct.stderr)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.pdf"
            source.write_bytes(b"synthetic source")
            state = root / "evaluation-state.json"
            result = subprocess.run([
                sys.executable, str(SCRIPTS / "v10_cli.py"), "state", "init",
                "--output", str(state), "--evaluation-id", "EVAL-V10-NATIVE",
                "--source-title", "Synthetic", "--source-file", str(source),
                "--document-page-start", "1", "--document-page-end", "2",
                "--intended-readership", "general", "--readership-rationale", "Synthetic test.",
            ], text=True, capture_output=True, check=False)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            document = json.loads(state.read_text())
            self.assertEqual("subject-index-evaluation-state-v9", document["schema_version"])
            self.assertEqual("subject-index-standard-policy-v10", document["configuration"]["policy_profile"])


if __name__ == "__main__":
    unittest.main()
