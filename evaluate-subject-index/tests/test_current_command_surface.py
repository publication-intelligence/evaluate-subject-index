from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def help_text(script: str) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


class CurrentCommandSurfaceTests(unittest.TestCase):
    def test_checkpoint_cli_has_no_migration_command(self) -> None:
        text = help_text("bundle_cli.py")
        self.assertIn("import-bundle", text)
        self.assertNotIn("migrate-publication-profile", text)

    def test_candidate_preparation_is_local(self) -> None:
        text = help_text("candidate_preparation_cli.py")
        self.assertIn("register", text)
        self.assertNotIn("extract", text)
        self.assertNotIn("bind-publication", text)
        self.assertNotIn("integrate", text)

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
                "structure-audit-v5.schema.json",
                "dimension-calculation-input.schema.json",
                "dimension-calculations-v5.schema.json",
                "item-assessments-v6.schema.json",
                "evaluation-result-v10.schema.json",
                "web-report-v8.schema.json",
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
        self.assertNotIn("merge-evidence", text)
        self.assertNotIn("build-locator-worker", text)

    def test_parallel_discovery_is_local(self) -> None:
        text = help_text("parallel_discovery_cli.py")
        self.assertIn("validate-discoveries", text)
        self.assertIn("register-discoveries", text)
        self.assertNotIn("worker-receipt", text)
        self.assertNotIn("integrate", text)

    def test_scoring_surface_is_current_only(self) -> None:
        text = help_text("dimension_score_v8_cli.py")
        self.assertIn("preflight", text)
        self.assertIn("calculate", text)
        self.assertNotIn("migrate", text)
        self.assertNotIn("validate-artifact", text)

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
                [sys.executable, str(SCRIPTS / "policy_cli.py"), "build", "--input", str(source), "--output", str(output)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            policy = json.loads(output.read_text())
            self.assertEqual("subject-index-evaluation-policy-v4", policy["schema_version"])
            self.assertEqual("subject-index-standard-policy-v8", policy["policy_profile"]["id"])
            self.assertNotIn("standard_policy_sha256", policy["policy_profile"])


if __name__ == "__main__":
    unittest.main()
