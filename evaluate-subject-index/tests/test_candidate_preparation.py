#!/usr/bin/env python3
"""Focused regressions for candidate heading and locator normalization."""

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


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "evaluate-subject-index" / "scripts"))

from candidate_preparation_cli import command_normalize, normalize_layout, split_heading_and_payload  # noqa: E402


def page_map() -> dict:
    pages = [
        {
            "document_page": number,
            "source_page_label": str(number),
            "normalized_locator_key": str(number),
            "label_style": "arabic",
            "mapping_id": "body",
            "in_evaluation_scope": True,
            "accepts_index_locators": True,
        }
        for number in range(1, 172)
    ]
    return {
        "schema_version": "page-map-v1",
        "source_sha256": "0" * 64,
        "document_page_count": len(pages),
        "document_page_basis": "one_based_inclusive",
        "pages": pages,
        "validation": {"all_document_pages_covered": True, "unique_indexable_locator_keys": True},
        "page_map_sha256": "1" * 64,
    }


def layout(lines: list[tuple[str, int]]) -> dict:
    line_records = [
        {
            "line_id": f"LINE-{index}",
            "region_id": "REGION-1",
            "candidate_pdf_page": 1,
            "reading_order_region": 1,
            "column": 1,
            "reading_order": index,
            "bbox": [0, index * 10, 100, index * 10 + 8],
            "indentation_level": indentation,
            "displayed_line_text": text,
            "continuation_status": "standalone",
            "inferred_boundary": "main_entry" if indentation == 0 else "subentry",
            "confidence": 1,
            "extraction_warnings": [],
            "original_displayed_form": text,
        }
        for index, (text, indentation) in enumerate(lines, 1)
    ]
    return {
        "schema_version": "candidate-layout-extraction-v1",
        "candidate_id": "whitespace-regression",
        "candidate_sha256": "2" * 64,
        "source_sha256": "0" * 64,
        "adapter_id": "synthetic-layout",
        "adapter_version": "1.0.0",
        "adapter": {
            "requested_id": "synthetic-layout",
            "id": "synthetic-layout",
            "version": "1.0.0",
            "selection_reason": "synthetic_regression",
            "selection_evidence": {},
        },
        "pdf": {"page_count": 1, "producer": None, "has_embedded_text": True},
        "pdf_metadata": {
            "sha256": "2" * 64,
            "page_count": 1,
            "is_pdf": False,
            "is_encrypted": False,
        },
        "pages": [{
            "candidate_pdf_page": 1,
            "width": 100,
            "height": 200,
            "two_column_layout": False,
            "column_split_x": None,
            "region_ids": ["REGION-1"],
            "line_ids": [item["line_id"] for item in line_records],
            "regions": [{
                "region_id": "REGION-1",
                "candidate_pdf_page": 1,
                "region_order": 1,
                "reading_order_region": 1,
                "column": 1,
                "role": "index_column",
                "bbox": [0, 0, 100, 200],
                "line_ids": [item["line_id"] for item in line_records],
                "line_count": len(line_records),
                "column_detection_confidence": 1,
                "lines": line_records,
            }],
        }],
        "excluded_lines": [],
        "counts": {
            "pages": 1,
            "regions": 1,
            "lines": len(line_records),
            "index_lines": len(line_records),
            "excluded_lines": 0,
            "excluded_repeated_headers": 0,
            "excluded_repeated_footers": 0,
            "excluded_page_number_footers": 0,
            "lines_with_extraction_warnings": 0,
            "column_continuations": 0,
            "page_continuations": 0,
        },
    }


class HeadingPayloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lookup = {str(number): {} for number in range(1, 172)}

    def test_whitespace_boundary_uses_frozen_locator_lookup(self) -> None:
        cases = {
            "Aachen 171": ("Aachen", "171"),
            "Académie française 47, 49, 50": ("Académie française", "47, 49, 50"),
            "pre-Revolutionary 5-12": ("pre-Revolutionary", "5-12"),
            "Louis XVI 100": ("Louis XVI", "100"),
            "Constitution of 1791 33": ("Constitution of 1791", "33"),
            "Appendix 9999": ("Appendix 9999", ""),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected, split_heading_and_payload(text, self.lookup))

    def test_punctuation_and_cross_reference_boundaries_are_unchanged(self) -> None:
        self.assertEqual(("Aachen", "171, 170"), split_heading_and_payload("Aachen, 171, 170", self.lookup))
        self.assertEqual(("Aachen", "see also Cologne"), split_heading_and_payload("Aachen see also Cologne", self.lookup))
        self.assertEqual(("Aachen", "171; see also Cologne"), split_heading_and_payload("Aachen 171; see also Cologne", self.lookup))


class WhitespaceLayoutNormalizationTests(unittest.TestCase):
    def test_first_whitespace_delimited_locator_is_preserved_and_expanded(self) -> None:
        candidate, _, issues = normalize_layout(
            layout([
                ("Aachen 171", 0),
                ("Académie française 47, 49, 50", 0),
                ("Revolution", 0),
                ("pre-Revolutionary 5-12", 1),
                ("Louis XVI 100", 0),
                ("Constitution of 1791 33", 0),
                ("Appendix 9999", 0),
                ("Punctuation, 47, 49", 0),
                ("References see also Other", 0),
                ("Mixed 50; see also Other", 0),
            ]),
            page_map(),
        )

        records = {record["original_displayed_form"]: record for record in candidate["records"]}
        self.assertEqual(["Académie française"], records["Académie française 47, 49, 50"]["heading_path"])
        self.assertEqual(
            ["47", "49", "50"],
            [item["displayed_locator"] for item in records["Académie française 47, 49, 50"]["locator_displays"]],
        )
        self.assertEqual(["Revolution", "pre-Revolutionary"], records["pre-Revolutionary 5-12"]["heading_path"])
        self.assertEqual("5-12", records["pre-Revolutionary 5-12"]["locator_displays"][0]["displayed_locator"])
        self.assertEqual(8, len(records["pre-Revolutionary 5-12"]["locator_assignments"]))
        self.assertEqual(["Louis XVI"], records["Louis XVI 100"]["heading_path"])
        self.assertEqual(["Constitution of 1791"], records["Constitution of 1791 33"]["heading_path"])
        self.assertEqual(["Appendix 9999"], records["Appendix 9999"]["heading_path"])
        self.assertEqual([], records["Appendix 9999"]["locator_assignments"])
        self.assertEqual("50", records["Mixed 50; see also Other"]["locator_displays"][0]["displayed_locator"])
        self.assertEqual("Other", records["Mixed 50; see also Other"]["cross_references"][0]["target"])
        self.assertEqual(10, candidate["normalization"]["displayed_locator_count"])
        self.assertEqual(17, candidate["normalization"]["expanded_locator_assignment_count"])
        self.assertEqual([], issues["issues"])

    def test_clean_normalization_writes_only_three_canonical_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_file = root / "candidate.txt"
            candidate_file.write_text("Aachen 171\n")
            candidate_layout = layout([("Aachen 171", 0)])
            digest = hashlib.sha256(candidate_file.read_bytes()).hexdigest()
            candidate_layout["candidate_sha256"] = digest
            candidate_layout["pdf_metadata"]["sha256"] = digest
            layout_path = root / "layout.json"
            layout_path.write_text(json.dumps(candidate_layout))
            args = argparse.Namespace(
                state=str(root / "state.json"), page_map=str(root / "page-map.json"),
                chunk_manifest=str(root / "chunks.json"), policy=str(root / "policy.json"),
                candidate_file=str(candidate_file), layout=str(layout_path), candidate_id="whitespace-regression",
                source_edition=None, output_dir=str(root / "output"), force=False,
            )
            identities = {"source_sha256": "0" * 64, "page_map": page_map()}
            stream = io.StringIO()
            with patch("candidate_preparation_cli.load_source_identities", return_value=identities), contextlib.redirect_stdout(stream):
                with self.assertRaises(SystemExit) as emitted:
                    command_normalize(args)
            self.assertEqual(0, emitted.exception.code)
            result = json.loads(stream.getvalue())
            self.assertEqual(3, len(result["artifacts_written"]))
            self.assertEqual(
                {"layout_extraction", "candidate_index", "item_inventory"},
                {item["artifact"] for item in result["artifacts_written"]},
            )
            self.assertFalse((root / "output" / "validation" / "candidate-normalization-issues.whitespace-regression.v1.json").exists())

            candidate_layout = layout([(", 171", 0)])
            candidate_layout["candidate_sha256"] = digest
            candidate_layout["pdf_metadata"]["sha256"] = digest
            layout_path.write_text(json.dumps(candidate_layout))
            args.output_dir = str(root / "issues-output")
            stream = io.StringIO()
            with patch("candidate_preparation_cli.load_source_identities", return_value=identities), contextlib.redirect_stdout(stream):
                with self.assertRaises(SystemExit) as emitted:
                    command_normalize(args)
            self.assertEqual(0, emitted.exception.code)
            result = json.loads(stream.getvalue())
            self.assertEqual(4, len(result["artifacts_written"]))
            issue_path = root / "issues-output" / "validation" / "candidate-normalization-issues.whitespace-regression.v1.json"
            self.assertEqual("needs_review", json.loads(issue_path.read_text())["issues"][0]["status"])


if __name__ == "__main__":
    unittest.main()
