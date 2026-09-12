from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import parallel_candidate_audit_cli as audits  # noqa: E402
from state_cli import STAGES, validate_state  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_record(root: Path, path: Path, stage: str, artifact_type: str, schema_version: str) -> dict:
    relative = path.relative_to(root).as_posix()
    digest = file_sha256(path)
    return {
        "artifact_id": audits.artifact_id(relative, digest),
        "stage": stage,
        "artifact_type": artifact_type,
        "path": relative,
        "sha256": digest,
        "media_type": "application/json",
        "schema_version": schema_version,
        "visibility": "private",
        "retention": "required",
        "frozen": True,
        "recorded_at": "2026-09-09T00:00:00Z",
    }


class ReplacementFixture:
    candidate_sha = "b" * 64
    chunks = ("CHUNK-001", "CHUNK-002")

    def __init__(self, root: Path):
        self.root = root
        self.state_path = root / "evaluation-state.json"
        self.candidate_path = root / "candidate" / "candidate-index.json"
        self.inventory_path = root / "candidate" / "item-inventory.json"
        self.benchmark_path = root / "benchmark" / "source-benchmark.json"
        self.candidate = {
            "schema_version": "candidate-index-v2",
            "candidate_id": "candidate-synthetic",
            "candidate_sha256": self.candidate_sha,
            "records": [
                {
                    "path_id": f"PATH-{number:03d}",
                    "heading_path": [f"Heading {number}"],
                    "locator_assignments": [{
                        "locator_id": f"LOC-{number:03d}",
                        "display_id": f"DISPLAY-{number:03d}",
                        "displayed_locator": str(number),
                        "document_page": number,
                        "source_page_label": str(number),
                        "mapping_status": "resolved",
                        "range_id": None,
                    }],
                }
                for number in (1, 2)
            ],
        }
        write_json(self.candidate_path, self.candidate)
        write_json(self.inventory_path, {"schema_version": "subject-index-item-inventory-v2"})
        write_json(self.benchmark_path, {"schema_version": "source-subject-benchmark-v2"})
        self.canonical = {
            kind: {
                chunk_id: root / "candidate" / ("locator-audits" if kind == "locator" else "missing-access-audits")
                / f"{'locator-audit' if kind == 'locator' else 'missing-access-audit'}.{chunk_id}.{'v2' if kind == 'locator' else 'v1'}.json"
                for chunk_id in self.chunks
            }
            for kind in ("locator", "missing_access")
        }
        self._write_state()
        self.packets = {
            chunk_id: {
                "assignments": {
                    f"LOC-{number:03d}": {
                        **self.candidate["records"][number - 1]["locator_assignments"][0],
                        "path_id": f"PATH-{number:03d}",
                        "heading_path": [f"Heading {number}"],
                    },
                },
                "paths": {f"PATH-{number:03d}": [f"Heading {number}"]},
            }
            for number, chunk_id in enumerate(self.chunks, 1)
        }

    def _write_state(self) -> None:
        records = []
        special = {
            "benchmark_freeze": (self.benchmark_path, "source_benchmark", "source-subject-benchmark-v2"),
            "candidate_normalization": (self.candidate_path, "candidate_index", "candidate-index-v2"),
        }
        for stage in STAGES[1:]:
            if stage in {"locator_audit", "missing_access_audit"}:
                kind = "locator" if stage == "locator_audit" else "missing_access"
                for chunk_id, path in self.canonical[kind].items():
                    schema = "locator-audit-v2" if kind == "locator" else "missing-access-audit-v1"
                    write_json(path, {"schema_version": schema, "chunk_id": chunk_id, "version": "old"})
                    records.append(artifact_record(self.root, path, stage, stage, schema))
                continue
            if stage in special:
                path, artifact_type, schema = special[stage]
            else:
                path = self.root / "artifacts" / f"{stage}.json"
                artifact_type = stage
                schema = {
                    "scoring": "subject-index-evaluation-result-v10",
                    "web_report": "subject-index-web-report-v8",
                }.get(stage, f"synthetic-{stage}-v1")
                write_json(path, {"schema_version": schema, "stage": stage})
            records.append(artifact_record(self.root, path, stage, artifact_type, schema))
        records.append(artifact_record(self.root, self.inventory_path, "candidate_normalization", "item_inventory", "subject-index-item-inventory-v2"))
        candidate_record = next(item for item in records if item["artifact_type"] == "candidate_index")
        state = {
            "schema_version": "subject-index-evaluation-state-v6",
            "evaluation_id": "EVAL-REPLACEMENT",
            "created_at": "2026-09-09T00:00:00Z",
            "updated_at": "2026-09-09T00:00:00Z",
            "source": {"title": "Synthetic", "filename": "synthetic.pdf", "sha256": "a" * 64, "document_page_span": [1, 2]},
            "candidate": {
                "candidate_id": "candidate-synthetic", "candidate_sha256": self.candidate_sha,
                "schema_version": "candidate-index-v2", "normalized_path": candidate_record["path"],
                "normalized_sha256": candidate_record["sha256"],
                "item_inventory_path": self.inventory_path.relative_to(self.root).as_posix(),
                "benchmark_path": self.benchmark_path.relative_to(self.root).as_posix(),
                "benchmark_sha256": "c" * 64,
            },
            "configuration": {
                "audit_mode": "full", "index_type": "subject_index", "intended_readership": "general",
                "readership_provenance": {"basis": "inferred", "confidence": "high", "rationale": "Synthetic fixture."},
                "output_format": "json", "storage_mode": "local", "policy_profile": "subject-index-standard-policy-v8",
                "rubric_version": "subject-index-rubric-v8",
                "scoring_identity": {"rubric_version": "subject-index-rubric-v8", "dimension_calculation_profile": "subject-index-dimension-calculation-v5"},
            },
            "stages": {stage: {"status": "completed", "updated_at": "2026-09-09T00:00:00Z", "notes": []} for stage in STAGES},
            "artifacts": sorted(records, key=lambda item: item["path"]),
            "blockers": [],
        }
        write_json(self.state_path, state)

    def frozen(self) -> dict:
        return {
            "state": json.loads(self.state_path.read_text()), "root": self.root,
            "candidate": self.candidate, "candidate_sha256": self.candidate_sha,
            "chunks": {chunk_id: {} for chunk_id in self.chunks}, "warnings": [],
        }

    def incoming(self, kind: str, *, duplicate: bool = False, wrong_hash: bool = False, invalid: bool = False) -> list[str]:
        paths = []
        for number, chunk_id in enumerate(self.chunks, 1):
            selected_chunk = self.chunks[0] if duplicate else chunk_id
            value = {
                "schema_version": "locator-audit-v2" if kind == "locator" else "missing-access-audit-v1",
                "evaluation_id": "EVAL-REPLACEMENT",
                "candidate_sha256": "f" * 64 if wrong_hash and number == 2 else self.candidate_sha,
                "chunk_id": selected_chunk,
                "version": "corrected",
            }
            if invalid and number == 2:
                value.pop("schema_version")
            path = self.root / "incoming" / f"{kind}-{number}.json"
            write_json(path, value)
            paths.append(str(path))
        return paths

    def args(self, kind: str, paths: list[str], *, replace: bool) -> argparse.Namespace:
        return argparse.Namespace(state=str(self.state_path), audit_kind=kind, audit=paths, replace_complete_batch=replace)


def synthetic_validation(audit: dict, frozen: dict, audit_kind: str, packets: dict, locator_set: dict | None):
    expected_schema = "locator-audit-v2" if audit_kind == "locator" else "missing-access-audit-v1"
    audits.require(audit.get("schema_version") == expected_schema, "schema_validation_failed", "Synthetic audit schema is invalid.")
    audits.require(audit.get("evaluation_id") == frozen["state"]["evaluation_id"], "audit_identity_mismatch", "Synthetic audit evaluation identity differs.")
    audits.require(audit.get("candidate_sha256") == frozen["candidate_sha256"], "audit_identity_mismatch", "Synthetic audit candidate hash differs.")
    chunk_id = audits.validate_chunk_id(audit.get("chunk_id"))
    audits.require(chunk_id in frozen["chunks"], "unknown_chunk", "Synthetic audit chunk is not frozen.")
    if audit_kind == "locator":
        audits.require(chunk_id in packets, "locator_packet_missing", "Synthetic locator packet is missing.")
    else:
        audits.require(locator_set is not None, "locator_audit_set_incomplete", "Synthetic locator set is missing.")
    return chunk_id, {"completion": {"expected": 1, "judged": 1, "complete": True}}


class AuditBatchReplacementTests(unittest.TestCase):
    def run_registration(self, fixture: ReplacementFixture, args: argparse.Namespace) -> dict:
        validation_inputs = (fixture.packets, None) if args.audit_kind == "locator" else ({}, {"complete": True})
        output = io.StringIO()
        with (
            patch.object(audits, "load_frozen_inputs", return_value=fixture.frozen()),
            patch.object(audits, "load_local_validation_inputs", return_value=validation_inputs),
            patch.object(audits, "validate_local_audit", side_effect=synthetic_validation),
            contextlib.redirect_stdout(output),
        ):
            try:
                audits.command_register_local(args)
            except SystemExit as exc:
                self.assertEqual(0, exc.code)
        return json.loads(output.getvalue())

    def test_complete_replacement_supports_both_audits_and_invalidates_later_state_only(self) -> None:
        for kind in ("locator", "missing_access"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                fixture = ReplacementFixture(Path(temporary))
                stage = audits.audit_stage(kind)
                stage_index = STAGES.index(stage)
                if kind == "missing_access":
                    in_progress = json.loads(fixture.state_path.read_text())
                    in_progress["stages"]["structure_audit"]["status"] = "in_progress"
                    for name in ("scoring", "web_report"):
                        in_progress["stages"][name]["status"] = "not_started"
                    write_json(fixture.state_path, in_progress)
                original = json.loads(fixture.state_path.read_text())
                later_records = [item for item in original["artifacts"] if STAGES.index(item["stage"]) > stage_index]
                earlier_records = [item for item in original["artifacts"] if STAGES.index(item["stage"]) < stage_index]
                response = self.run_registration(fixture, fixture.args(kind, fixture.incoming(kind), replace=True))

                state = json.loads(fixture.state_path.read_text())
                self.assertEqual("completed", state["stages"][stage]["status"])
                self.assertEqual(STAGES[stage_index + 1:], response["invalidated_stages"])
                self.assertTrue(all(state["stages"][name]["status"] == "not_started" for name in STAGES[stage_index + 1:]))
                self.assertEqual(earlier_records, [item for item in state["artifacts"] if STAGES.index(item["stage"]) < stage_index])
                self.assertFalse(any(item["stage"] in STAGES[stage_index + 1:] for item in state["artifacts"]))
                self.assertTrue(all((fixture.root / item["path"]).is_file() for item in later_records))
                current = [item for item in state["artifacts"] if item["stage"] == stage]
                self.assertEqual(2, len(current))
                self.assertTrue(all(json.loads(path.read_text())["version"] == "corrected" for path in fixture.canonical[kind].values()))
                self.assertEqual([], validate_state(state, state_path=fixture.state_path)[0])

    def test_incomplete_duplicate_invalid_and_wrong_hash_batches_fail_before_mutation(self) -> None:
        scenarios = {
            "incomplete": lambda fixture: fixture.incoming("locator")[:1],
            "duplicate": lambda fixture: fixture.incoming("locator", duplicate=True),
            "invalid": lambda fixture: fixture.incoming("locator", invalid=True),
            "wrong_hash": lambda fixture: fixture.incoming("locator", wrong_hash=True),
        }
        for name, make_paths in scenarios.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                fixture = ReplacementFixture(Path(temporary))
                state_before = fixture.state_path.read_bytes()
                canonical_before = {path: path.read_bytes() for path in fixture.canonical["locator"].values()}
                args = fixture.args("locator", make_paths(fixture), replace=True)
                with (
                    patch.object(audits, "load_frozen_inputs", return_value=fixture.frozen()),
                    patch.object(audits, "load_local_validation_inputs", return_value=(fixture.packets, None)),
                    patch.object(audits, "validate_local_audit", side_effect=synthetic_validation),
                    self.assertRaises(audits.PreparationError),
                ):
                    audits.command_register_local(args)
                self.assertEqual(state_before, fixture.state_path.read_bytes())
                self.assertEqual(canonical_before, {path: path.read_bytes() for path in fixture.canonical["locator"].values()})

    def test_normal_registration_still_refuses_to_overwrite_changed_canonical_chunk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReplacementFixture(Path(temporary))
            state_before = fixture.state_path.read_bytes()
            canonical_before = {path: path.read_bytes() for path in fixture.canonical["locator"].values()}
            args = fixture.args("locator", fixture.incoming("locator"), replace=False)
            with (
                patch.object(audits, "load_frozen_inputs", return_value=fixture.frozen()),
                patch.object(audits, "load_local_validation_inputs", return_value=(fixture.packets, None)),
                patch.object(audits, "validate_local_audit", side_effect=synthetic_validation),
                self.assertRaises(audits.PreparationError) as raised,
            ):
                audits.command_register_local(args)
            self.assertEqual("canonical_chunk_exists", raised.exception.code)
            self.assertEqual(state_before, fixture.state_path.read_bytes())
            self.assertEqual(canonical_before, {path: path.read_bytes() for path in fixture.canonical["locator"].values()})


if __name__ == "__main__":
    unittest.main()
