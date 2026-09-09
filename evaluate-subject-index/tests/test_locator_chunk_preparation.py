from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import candidate_preparation_cli
from state_cli import STAGES


def canonical_hash(value: dict, own_hash_field: str) -> str:
    clone = dict(value)
    clone.pop(own_hash_field, None)
    encoded = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def artifact_record(root: Path, path: Path, stage: str, artifact_type: str, schema_version: str) -> dict:
    relative = path.relative_to(root).as_posix()
    digest = file_sha256(path)
    identity = hashlib.sha256(f"{relative}\0{digest}".encode()).hexdigest()[:12].upper()
    return {
        "artifact_id": f"ART-{identity}",
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


def run_cli(*arguments: object, ok: bool = True) -> tuple[dict, int]:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "page_chunk_cli.py"), *(str(value) for value in arguments)],
        text=True,
        capture_output=True,
        check=False,
    )
    if ok and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    if not ok and not result.returncode:
        raise AssertionError("Command unexpectedly succeeded: " + result.stdout)
    return json.loads(result.stdout), result.returncode


class LocatorFixture:
    source_sha = "a" * 64
    candidate_sha = "b" * 64
    policy_sha = "c" * 64

    def __init__(self, root: Path):
        self.root = root
        self.page_map_path = root / "page-map.json"
        self.manifest_path = root / "chunk-manifest.json"
        self.benchmark_path = root / "source-benchmark.json"
        self.candidate_path = root / "preparation" / "candidate-index.json"
        self.candidate_ref_path = root / "preparation" / "candidate_ref.json"
        self.inventory_path = root / "preparation" / "item-inventory.json"
        self.state_path = root / "evaluation-state.json"
        self.output_dir = root / "preparation" / "locator-packets"
        self.page_map = self._page_map()
        self.manifest = self._manifest()
        self.benchmark = self._benchmark()
        self.candidate = self._candidate()
        for path, value in (
            (self.page_map_path, self.page_map),
            (self.manifest_path, self.manifest),
            (self.benchmark_path, self.benchmark),
            (self.candidate_path, self.candidate),
            (self.inventory_path, {"schema_version": "subject-index-item-inventory-v2"}),
        ):
            write_json(path, value)
        self._write_state()

    def _page_map(self) -> dict:
        value = {
            "schema_version": "page-map-v1",
            "source_sha256": self.source_sha,
            "document_page_count": 17,
            "document_page_basis": "one_based_inclusive",
            "pages": [
                {
                    "document_page": page,
                    "source_page_label": str(page),
                    "normalized_locator_key": str(page),
                    "label_style": "arabic",
                    "mapping_id": "main",
                    "in_evaluation_scope": True,
                    "accepts_index_locators": True,
                }
                for page in range(1, 18)
            ],
            "validation": {"all_document_pages_covered": True, "unique_indexable_locator_keys": True},
            "page_map_sha256": None,
        }
        value["page_map_sha256"] = canonical_hash(value, "page_map_sha256")
        return value

    def _manifest(self) -> dict:
        value = {
            "schema_version": "chunk-manifest-v1",
            "document_page_basis": "one_based_inclusive",
            "user_approved": True,
            "require_full_scope_coverage": True,
            "chunks": [
                {
                    "chunk_id": f"CHUNK-{page:03d}",
                    "title": f"Chunk {page}",
                    "source_units": [f"Unit {page}"],
                    "owned_document_page_ranges": [[page, page]],
                    "context_document_page_ranges": [],
                    "packet_order": page,
                }
                for page in range(1, 18)
            ],
            "page_map_sha256": self.page_map["page_map_sha256"],
            "validation": {"owned_pages_unique": True, "scope_coverage_complete": True},
            "chunk_manifest_sha256": None,
        }
        value["chunk_manifest_sha256"] = canonical_hash(value, "chunk_manifest_sha256")
        return value

    def _benchmark(self) -> dict:
        value = {
            "schema_version": "source-subject-benchmark-v2",
            "benchmark_id": "BENCHMARK-1",
            "version": 1,
            "evaluation_id": "EVAL-LOCATOR",
            "source_sha256": self.source_sha,
            "policy_sha256": self.policy_sha,
            "page_map_sha256": self.page_map["page_map_sha256"],
            "candidate_blindness": "preserved",
            "chunk_manifest_sha256": self.manifest["chunk_manifest_sha256"],
            "subjects": [],
            "relationships": [],
            "reader_tasks": [],
            "freeze": {"frozen_at": "2026-09-09T00:00:00Z", "synthesis_pass_complete": True, "page_coverage_complete": True},
            "benchmark_sha256": None,
        }
        value["benchmark_sha256"] = canonical_hash(value, "benchmark_sha256")
        return value

    def _candidate(self) -> dict:
        records = []
        for page in range(1, 18):
            records.append({
                "record_id": f"REC-{page:03d}",
                "record_type": "page_bearing",
                "path_id": f"PATH-{page:03d}",
                "heading_path": [f"Heading {page}"],
                "original_displayed_form": f"Heading {page}, {page}",
                "locator_displays": [{
                    "display_id": f"DISPLAY-{page:03d}",
                    "displayed_locator": str(page),
                    "kind": "point",
                    "mapping_status": "resolved",
                    "locator_ids": [f"LOC-{page:03d}"],
                }],
                "locator_assignments": [{
                    "locator_id": f"LOC-{page:03d}",
                    "display_id": f"DISPLAY-{page:03d}",
                    "displayed_locator": str(page),
                    "source_page_label": str(page),
                    "normalized_locator_key": str(page),
                    "document_page": page,
                    "mapping_status": "resolved",
                    "range_id": None,
                }],
                "cross_references": [],
            })
        return {
            "schema_version": "candidate-index-v2",
            "candidate_id": "candidate-current",
            "candidate_sha256": self.candidate_sha,
            "page_map_sha256": self.page_map["page_map_sha256"],
            "records": records,
            "normalization": {
                "engine": "candidate-preparation-cli",
                "engine_version": "1.0.0",
                "record_count": 17,
                "editorial_corrections_applied": False,
                "benchmark_content_used": False,
            },
        }

    def _candidate_ref(self) -> dict:
        finding = {"status": "verified", "rationale": "Synthetic current-workflow fixture."}
        return {
            "schema_version": "candidate-ref-v1",
            "candidate_id": "candidate-current",
            "candidate_sha256": self.candidate_sha,
            "candidate_filename": "candidate.pdf",
            "file_origin": "delivered_pdf",
            "source": {"sha256": self.source_sha, "edition": "Test edition"},
            "page_map_sha256": self.page_map["page_map_sha256"],
            "chunk_manifest_sha256": self.manifest["chunk_manifest_sha256"],
            "policy": {
                "profile": "subject-index-standard-policy-v8",
                "sha256": self.policy_sha,
                "rubric_version": "subject-index-rubric-v8",
                "audit_mode": "full",
            },
            "pdf": {"page_count": 1, "producer": None, "has_embedded_text": True},
            "provenance": {
                "candidate_bytes": finding,
                "internal_pdf_completeness": finding,
                "structural_continuity": finding,
                "source_edition_compatibility": finding,
                "locator_page_map_compatibility": finding,
                "authoritative_copy_fidelity": {**finding, "claimed_original_publisher_pdf": True},
            },
            "created_at": "2026-09-09T00:00:00Z",
        }

    def _write_state(self) -> None:
        completed = set(STAGES[:STAGES.index("candidate_normalization")])
        stages = {
            stage: {
                "status": "completed" if stage in completed else "not_started",
                "updated_at": "2026-09-09T00:00:00Z" if stage in completed else None,
                "notes": [],
            }
            for stage in STAGES
        }
        artifacts = []
        special = {
            "page_mapping": (self.page_map_path, "page_map", "page-map-v1"),
            "chunk_definition": (self.manifest_path, "chunk_manifest", "chunk-manifest-v1"),
            "benchmark_freeze": (self.benchmark_path, "source_benchmark", "source-subject-benchmark-v2"),
        }
        for stage in STAGES[1:STAGES.index("candidate_normalization")]:
            if stage in special:
                path, artifact_type, schema_version = special[stage]
            else:
                path = self.root / "control" / f"{stage}.json"
                schema_version = f"test-{stage}-v1"
                artifact_type = stage
                write_json(path, {"schema_version": schema_version})
            artifacts.append(artifact_record(self.root, path, stage, artifact_type, schema_version))
        state = {
            "schema_version": "subject-index-evaluation-state-v6",
            "evaluation_id": "EVAL-LOCATOR",
            "created_at": "2026-09-09T00:00:00Z",
            "updated_at": "2026-09-09T00:00:00Z",
            "source": {
                "title": "Example",
                "edition": "Test edition",
                "filename": "source.pdf",
                "sha256": self.source_sha,
                "document_page_span": [1, 17],
                "document_page_basis": "one_based_inclusive",
            },
            "candidate": None,
            "configuration": {
                "audit_mode": "full",
                "index_type": "subject_index",
                "intended_readership": "general",
                "readership_provenance": {"basis": "inferred", "confidence": "medium", "rationale": "Test."},
                "output_format": "json",
                "storage_mode": "local",
                "policy_profile": "subject-index-standard-policy-v8",
                "rubric_version": "subject-index-rubric-v8",
                "scoring_identity": {
                    "rubric_version": "subject-index-rubric-v8",
                    "dimension_calculation_profile": "subject-index-dimension-calculation-v4",
                },
            },
            "stages": stages,
            "artifacts": artifacts,
            "blockers": [],
        }
        write_json(self.state_path, state)

    def register_candidate(self) -> dict:
        documents = {}
        paths = {}
        schemas = {
            "candidate_ref": "candidate-ref-v1",
            "layout_profile": "candidate-layout-profile-v1",
            "layout_extraction": "candidate-layout-extraction-v1",
            "candidate_index": "candidate-index-v2",
            "item_inventory": "subject-index-item-inventory-v2",
            "normalization_exceptions": "candidate-normalization-exceptions-v1",
            "normalization_report": "candidate-normalization-report-v1",
            "normalization_qa": "candidate-normalization-qa-v1",
        }
        for name, schema_version in schemas.items():
            path = self.candidate_path if name == "candidate_index" else self.inventory_path if name == "item_inventory" else self.root / "preparation" / f"{name}.json"
            document = self.candidate if name == "candidate_index" else self._candidate_ref() if name == "candidate_ref" else {"schema_version": schema_version, "candidate_id": "candidate-current"}
            write_json(path, document)
            documents[name] = document
            paths[name] = path
        result = {
            "paths": paths,
            "documents": documents,
            "candidate_sha256": self.candidate_sha,
            "hashes": {name: file_sha256(path) for name, path in paths.items()},
            "counts": self.candidate["normalization"],
        }
        candidate_file = self.root / "candidate.pdf"
        candidate_file.write_bytes(b"local candidate bytes")
        args = argparse.Namespace(
            state=str(self.state_path), preparation_dir=str(self.root / "preparation"), candidate_id="Candidate Current",
            candidate_file=str(candidate_file), page_map=str(self.page_map_path), chunk_manifest=str(self.manifest_path),
            policy=str(self.root / "policy.json"), qa=None, source_edition=None, benchmark=str(self.benchmark_path),
        )
        with patch.object(candidate_preparation_cli, "validate_private_preparation", return_value=result):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream), self.assert_exit_zero():
                candidate_preparation_cli.command_register(args)
        return json.loads(stream.getvalue())

    @contextlib.contextmanager
    def assert_exit_zero(self):
        try:
            yield
        except SystemExit as exc:
            if exc.code != 0:
                raise AssertionError(f"Unexpected exit code {exc.code}") from exc
        else:
            raise AssertionError("CLI command did not emit a result")

    def command(self) -> tuple[object, ...]:
        return (
            "prepare-locator-chunks", "--state", self.state_path,
            "--normalized-candidate", self.candidate_path,
            "--page-map", self.page_map_path,
            "--chunk-manifest", self.manifest_path,
            "--benchmark", self.benchmark_path,
            "--output-dir", self.output_dir,
        )

    def update_registered_file(self, path: Path, value: dict) -> None:
        write_json(path, value)
        state = json.loads(self.state_path.read_text())
        relative = path.relative_to(self.root).as_posix()
        record = next(item for item in state["artifacts"] if item["path"] == relative)
        record["sha256"] = file_sha256(path)
        record["artifact_id"] = artifact_record(self.root, path, record["stage"], record["artifact_type"], record["schema_version"])["artifact_id"]
        write_json(self.state_path, state)


class LocatorChunkPreparationTests(unittest.TestCase):
    def test_local_registration_prepares_complete_17_packet_batch_and_advances(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LocatorFixture(Path(temporary))
            registration = fixture.register_candidate()
            self.assertTrue(registration["ok"])
            self.assertEqual("candidate-current", registration["candidate_id"])
            before = subprocess.run(
                [sys.executable, str(SCRIPTS / "state_cli.py"), "next", "--state", str(fixture.state_path)],
                text=True, capture_output=True, check=True,
            )
            self.assertEqual("prepare-locator-chunks", json.loads(before.stdout)["next_actions"][0]["command"])

            result, _ = run_cli(*fixture.command())
            self.assertTrue(result["ok"])
            self.assertEqual(17, result["counts"]["packets"])
            self.assertEqual(17, result["counts"]["routed_assignments"])
            self.assertEqual(0, result["counts"]["routing_exceptions"])
            locator_ids = []
            for packet_record in result["locator_packets"]:
                packet = json.loads((fixture.root / packet_record["path"]).read_text())
                self.assertEqual(1, len(packet["owned_document_pages"]))
                locator_ids.extend(
                    assignment["locator_id"]
                    for path in packet["paths"]
                    for assignment in path["locator_assignments"]
                )
            self.assertEqual([f"LOC-{page:03d}" for page in range(1, 18)], sorted(locator_ids))

            state = json.loads(fixture.state_path.read_text())
            self.assertEqual("completed", state["stages"]["locator_chunk_preparation"]["status"])
            registered = [item for item in state["artifacts"] if item["stage"] == "locator_chunk_preparation"]
            self.assertEqual(18, len(registered))
            self.assertTrue(all(item["frozen"] and item["retention"] == "required" and item["visibility"] == "private" for item in registered))
            after = subprocess.run(
                [sys.executable, str(SCRIPTS / "state_cli.py"), "next", "--state", str(fixture.state_path)],
                text=True, capture_output=True, check=True,
            )
            next_action = json.loads(after.stdout)["next_actions"][0]
            self.assertEqual("locator_audit", next_action["stage"])
            self.assertEqual("audit-locators", next_action["command"])
            self.assertTrue(next_action["available"])

    def test_rejects_before_benchmark_freeze_or_candidate_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = LocatorFixture(Path(temporary))
            original = fixture.state_path.read_bytes()
            result, _ = run_cli(*fixture.command(), ok=False)
            self.assertEqual("stage_dependencies_incomplete", result["error"]["code"])
            self.assertEqual(original, fixture.state_path.read_bytes())

            state = json.loads(fixture.state_path.read_text())
            state["stages"]["benchmark_freeze"] = {"status": "not_started", "updated_at": None, "notes": []}
            write_json(fixture.state_path, state)
            original = fixture.state_path.read_bytes()
            result, _ = run_cli(*fixture.command(), ok=False)
            self.assertEqual("stage_dependencies_incomplete", result["error"]["code"])
            self.assertEqual(original, fixture.state_path.read_bytes())

    def test_identity_mismatches_are_rejected_without_state_mutation(self) -> None:
        mutations = {
            "candidate": lambda fixture: self._mutate_candidate_identity(fixture),
            "benchmark": lambda fixture: self._mutate_benchmark_identity(fixture),
            "page-map": lambda fixture: self._mutate_page_map_identity(fixture),
            "chunk-manifest": lambda fixture: self._mutate_manifest_identity(fixture),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                fixture = LocatorFixture(Path(temporary))
                fixture.register_candidate()
                mutate(fixture)
                original = fixture.state_path.read_bytes()
                result, _ = run_cli(*fixture.command(), ok=False)
                self.assertFalse(result["ok"])
                self.assertEqual(original, fixture.state_path.read_bytes())
                self.assertEqual("not_started", json.loads(original)["stages"]["locator_chunk_preparation"]["status"])

    def _mutate_candidate_identity(self, fixture: LocatorFixture) -> None:
        fixture.candidate["candidate_id"] = "different-candidate"
        fixture.update_registered_file(fixture.candidate_path, fixture.candidate)

    def _mutate_benchmark_identity(self, fixture: LocatorFixture) -> None:
        fixture.benchmark["evaluation_id"] = "EVAL-DIFFERENT"
        fixture.benchmark["benchmark_sha256"] = canonical_hash(fixture.benchmark, "benchmark_sha256")
        fixture.update_registered_file(fixture.benchmark_path, fixture.benchmark)

    def _mutate_page_map_identity(self, fixture: LocatorFixture) -> None:
        fixture.page_map["source_sha256"] = "d" * 64
        fixture.page_map["page_map_sha256"] = canonical_hash(fixture.page_map, "page_map_sha256")
        fixture.update_registered_file(fixture.page_map_path, fixture.page_map)

    def _mutate_manifest_identity(self, fixture: LocatorFixture) -> None:
        fixture.manifest["page_map_sha256"] = "d" * 64
        fixture.manifest["chunk_manifest_sha256"] = canonical_hash(fixture.manifest, "chunk_manifest_sha256")
        fixture.update_registered_file(fixture.manifest_path, fixture.manifest)

    def test_duplicate_chunk_identity_or_overlapping_ownership_is_rejected(self) -> None:
        for kind in ("duplicate", "overlap"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                fixture = LocatorFixture(Path(temporary))
                fixture.register_candidate()
                if kind == "duplicate":
                    fixture.manifest["chunks"].append(dict(fixture.manifest["chunks"][0]))
                else:
                    fixture.manifest["chunks"][1]["owned_document_page_ranges"] = [[1, 2]]
                fixture.manifest["chunk_manifest_sha256"] = canonical_hash(fixture.manifest, "chunk_manifest_sha256")
                fixture.update_registered_file(fixture.manifest_path, fixture.manifest)
                candidate_ref = json.loads(fixture.candidate_ref_path.read_text())
                candidate_ref["chunk_manifest_sha256"] = fixture.manifest["chunk_manifest_sha256"]
                fixture.update_registered_file(fixture.candidate_ref_path, candidate_ref)
                fixture.benchmark["chunk_manifest_sha256"] = fixture.manifest["chunk_manifest_sha256"]
                fixture.benchmark["benchmark_sha256"] = canonical_hash(fixture.benchmark, "benchmark_sha256")
                fixture.update_registered_file(fixture.benchmark_path, fixture.benchmark)
                state = json.loads(fixture.state_path.read_text())
                state["candidate"]["benchmark_sha256"] = fixture.benchmark["benchmark_sha256"]
                write_json(fixture.state_path, state)
                original = fixture.state_path.read_bytes()
                result, _ = run_cli(*fixture.command(), ok=False)
                self.assertIn(result["error"]["code"], {"duplicate_chunk_identity", "overlapping_chunk_ownership"})
                self.assertEqual(original, fixture.state_path.read_bytes())

    def test_unresolved_or_ownerless_assignments_write_exceptions_without_advancing_state(self) -> None:
        for kind in ("unresolved", "ownerless"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                fixture = LocatorFixture(Path(temporary))
                fixture.register_candidate()
                if kind == "unresolved":
                    assignment = fixture.candidate["records"][-1]["locator_assignments"][0]
                    assignment.update({"mapping_status": "unresolved", "document_page": None, "source_page_label": None, "normalized_locator_key": None})
                    fixture.candidate["records"][-1]["locator_displays"][0]["mapping_status"] = "unresolved"
                    fixture.update_registered_file(fixture.candidate_path, fixture.candidate)
                else:
                    fixture.manifest["chunks"].pop()
                    fixture.manifest["require_full_scope_coverage"] = False
                    fixture.manifest["validation"]["scope_coverage_complete"] = False
                    fixture.manifest["chunk_manifest_sha256"] = canonical_hash(fixture.manifest, "chunk_manifest_sha256")
                    fixture.update_registered_file(fixture.manifest_path, fixture.manifest)
                    candidate_ref = json.loads(fixture.candidate_ref_path.read_text())
                    candidate_ref["chunk_manifest_sha256"] = fixture.manifest["chunk_manifest_sha256"]
                    fixture.update_registered_file(fixture.candidate_ref_path, candidate_ref)
                    fixture.benchmark["chunk_manifest_sha256"] = fixture.manifest["chunk_manifest_sha256"]
                    fixture.benchmark["benchmark_sha256"] = canonical_hash(fixture.benchmark, "benchmark_sha256")
                    fixture.update_registered_file(fixture.benchmark_path, fixture.benchmark)
                    state = json.loads(fixture.state_path.read_text())
                    state["candidate"]["benchmark_sha256"] = fixture.benchmark["benchmark_sha256"]
                    write_json(fixture.state_path, state)
                original = fixture.state_path.read_bytes()
                result, exit_code = run_cli(*fixture.command(), ok=False)
                self.assertEqual(2, exit_code)
                self.assertEqual(1, result["counts"]["routing_exceptions"])
                ledger = json.loads((fixture.root / result["routing_exception_ledger"]["path"]).read_text())
                self.assertEqual(1, ledger["exception_count"])
                self.assertEqual(original, fixture.state_path.read_bytes())
                self.assertEqual("not_started", json.loads(original)["stages"]["locator_chunk_preparation"]["status"])


if __name__ == "__main__":
    unittest.main()
