from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import state_cli  # noqa: E402
import test_v8_completion as completion  # noqa: E402


class PublicLocatorNarrativeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = completion.CurrentV8CompletionTests(
            "test_registered_audits_reach_valid_result_report_and_complete_state"
        )
        self.fixture.setUp()

    def tearDown(self) -> None:
        self.fixture.tearDown()

    def test_private_locator_narratives_never_enter_public_report_or_bundle(self) -> None:
        evidence_secret = "PRIVATE-SOURCE-SECRET authored evidence narrative must stay restricted"
        fit_secret = "PRIVATE-SOURCE-SECRET authored fit rationale must stay restricted"
        access_secret = "PRIVATE-SOURCE-SECRET locator-derived access rationale must stay restricted"
        stance_secret = "PRIVATE-SOURCE-SECRET authored source stance must stay restricted"
        locator_path = self.fixture.root / "candidate/locator-audit.CHUNK-001.v2.json"
        locator = json.loads(locator_path.read_text())
        locator["judgments"][0]["evidence_summary"] = evidence_secret
        locator["judgments"][0]["fit_rationale"] = fit_secret
        locator_path.write_text(json.dumps(locator, indent=2) + "\n")
        state = json.loads(self.fixture.state_path.read_text())
        record = next(item for item in state["artifacts"] if item["path"] == "candidate/locator-audit.CHUNK-001.v2.json")
        record["sha256"] = completion.file_hash(locator_path)
        record["artifact_id"] = state_cli.artifact_id(record["path"], record["sha256"])

        missing_path = self.fixture.root / "candidate/missing-access-audit.CHUNK-001.v1.json"
        missing = json.loads(missing_path.read_text())
        missing["subject_judgments"][0]["access_rationale"] = access_secret
        missing["subject_judgments"][0]["matched_locator_ids"] = ["LOC-001"]
        missing["subject_judgments"][0]["locator_ids"] = ["LOC-001"]
        missing["subject_judgments"][0]["tested_direct_path_ids"] = ["PATH-001"]
        missing["subject_judgments"][0]["benchmark_evidence_ids"] = ["EVID-BENCH-001"]
        missing["reader_task_results"][0]["access_rationale"] = access_secret
        missing["reader_task_results"][0]["tested_locator_ids"] = ["LOC-001"]
        missing["reader_task_results"][0]["tested_path_ids"] = ["PATH-001"]
        missing["reader_task_results"][0]["matched_reference_ids"] = ["XREF-001"]
        missing["reader_task_results"][0]["uncertainty"] = {"status": "uncertain", "reason": access_secret, "evidence_ids": ["EVID-TASK-001"]}
        missing["treatment_judgments"][0]["access_rationale"] = access_secret
        missing["treatment_judgments"][0]["matched_path_ids"] = ["PATH-001"]
        missing["treatment_judgments"][0]["matched_locator_ids"] = ["LOC-001"]
        missing["treatment_judgments"][0]["usable_locator_ids"] = ["LOC-001"]
        missing["treatment_judgments"][0]["source_evidence_ids"] = ["EVID-SUBJ-001"]
        missing["treatment_judgments"][0]["locator_evidence_ids"] = ["EVID-LOC-001"]
        missing["treatment_judgments"][0]["reason_code"] = "structured_match"
        missing["treatment_judgments"][0]["confidence"] = "high"
        missing["treatment_judgments"][0]["uncertainty"] = "not_measured"
        missing_path.write_text(json.dumps(missing, indent=2) + "\n")
        record = next(item for item in state["artifacts"] if item["path"] == "candidate/missing-access-audit.CHUNK-001.v1.json")
        record["sha256"] = completion.file_hash(missing_path)
        record["artifact_id"] = state_cli.artifact_id(record["path"], record["sha256"])

        benchmark_path = self.fixture.root / "source-benchmark.json"
        benchmark = json.loads(benchmark_path.read_text())
        benchmark["subjects"][0]["stance"] = stance_secret
        benchmark_path.write_text(json.dumps(benchmark, indent=2) + "\n")
        record = next(item for item in state["artifacts"] if item["path"] == "source-benchmark.json")
        record["sha256"] = completion.file_hash(benchmark_path)
        record["artifact_id"] = state_cli.artifact_id(record["path"], record["sha256"])
        self.fixture.state_path.write_text(json.dumps(state, indent=2) + "\n")

        self.assertEqual(0, self.fixture.run_cli("register-structure", "--state", str(self.fixture.state_path), "--input", str(self.fixture.structure_path)).returncode)
        self.assertEqual(0, self.fixture.run_cli("score", "--state", str(self.fixture.state_path)).returncode)
        items_path = self.fixture.root / "scoring/item-assessments.v7.json"
        items = json.loads(items_path.read_text())
        self.assertIn(evidence_secret, items_path.read_text())
        self.assertIn(fit_secret, items_path.read_text())
        self.assertIn(access_secret, missing_path.read_text())
        self.assertIn(stance_secret, benchmark_path.read_text())

        built = self.fixture.run_cli("build-report", "--state", str(self.fixture.state_path))
        self.assertEqual(0, built.returncode, built.stdout + built.stderr)
        report = json.loads((self.fixture.root / "scoring/web-report.v10.json").read_text())
        bundle = self.fixture.root / "scoring/v8-canonical-projection"
        projection = json.loads((bundle / "projection.v1.json").read_text())
        collections = [json.loads(path.read_text()) for path in sorted((bundle / "data").glob("*.json"))]
        public_text = json.dumps([report, projection, *collections])
        self.assertNotIn(evidence_secret, public_text)
        self.assertNotIn(fit_secret, public_text)
        self.assertNotIn(access_secret, public_text)
        self.assertNotIn(stance_secret, public_text)
        self.assertEqual(3, len(collections))
        self.assertFalse((bundle / "data/correction-overlay.v1.json").exists())

        private = items["locator_assessments"][0]
        report_explanation = report["locator_explanations"][0]
        index = next(item for item in collections if item["collection_kind"] == "index_records")
        public = index["items"][0]["displayed_locators"][0]["atomic_locators"][0]["assessment"]
        for key in ("locator_id", "path_id", "source_page_label", "document_page", "judgment", "confidence", "evidence_ids", "grade", "locator_utility"):
            self.assertEqual(private[key], public[key])
        for key in ("locator_id", "path_id", "diagnostic_locator_grade", "keep_rating_credit", "evidence_ids", "structured_defect_ids"):
            self.assertEqual(private["locator_explanation"][key], report_explanation[key])
        self.assertEqual("Synthetic subject", index["items"][0]["heading_path"][0])
        self.assertEqual("Synthetic subject, 1", index["items"][0]["original_displayed_form"])
        self.assertIn("page treatment mixed", public["popover"]["summary"])
        self.assertTrue(all(factor["explanation"] for factor in public["popover"]["factors"]))
        source_subjects = next(item for item in collections if item["collection_kind"] == "source_subjects")
        source = source_subjects["items"][0]
        self.assertEqual("Synthetic meaning.", source["meaning"])
        self.assertEqual(
            "Benchmark stance narrative withheld from the public projection; stance preservation outcome: yes.",
            source["stance"],
        )
        self.assertEqual(
            ["Authored benchmark stance narratives are withheld; public items report only the registered stance-preservation outcome."],
            source_subjects["limitations"],
        )
        self.assertEqual("complete", source["audit_judgment"]["coverage"])
        self.assertEqual(["LOC-001"], source["audit_judgment"]["matched_locator_ids"])
        self.assertEqual(["LOC-001"], source["audit_judgment"]["locator_ids"])
        self.assertEqual(["PATH-001"], source["audit_judgment"]["tested_direct_path_ids"])
        self.assertEqual(["EVID-BENCH-001"], source["audit_judgment"]["benchmark_evidence_ids"])
        self.assertEqual("succeeds", source["reader_tasks"][0]["result"]["result"])
        self.assertEqual(["LOC-001"], source["reader_tasks"][0]["result"]["tested_locator_ids"])
        self.assertEqual(["PATH-001"], source["reader_tasks"][0]["result"]["tested_path_ids"])
        self.assertEqual(["XREF-001"], source["reader_tasks"][0]["result"]["matched_reference_ids"])
        self.assertEqual("uncertain", source["reader_tasks"][0]["result"]["uncertainty"]["status"])
        self.assertEqual("found", source["expected_treatments"][0]["status"])
        self.assertEqual("1", source["expected_treatments"][0]["source_page_label"])
        self.assertEqual(["PATH-001"], source["expected_treatments"][0]["matched_path_ids"])
        self.assertEqual(["LOC-001"], source["expected_treatments"][0]["usable_locator_ids"])
        self.assertEqual(["EVID-SUBJ-001"], source["expected_treatments"][0]["source_evidence_ids"])
        self.assertEqual(["EVID-LOC-001"], source["expected_treatments"][0]["locator_evidence_ids"])
        self.assertEqual("structured_match", source["expected_treatments"][0]["reason_code"])
        self.assertEqual("not_measured", source["expected_treatments"][0]["uncertainty"])
        self.assertTrue(source["audit_judgment"]["access_rationale"])
        self.assertTrue(source["reader_tasks"][0]["result"]["access_rationale"])
        self.assertTrue(source["expected_treatments"][0]["access_rationale"])


if __name__ == "__main__":
    unittest.main()
