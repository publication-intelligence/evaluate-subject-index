from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_projection  # noqa: E402


class WebDensityProjectionTests(unittest.TestCase):
    def test_density_uses_canonical_calculation_by_chunk_id(self) -> None:
        structure = self.structure()
        structure["density"]["distribution_findings"] = [{
            "finding": "not_measured",
            "interpretation": "Generic methodological limitation.",
        }]
        calculation = self.calculation([
            self.calculated("CHUNK-002", "12", "24", "80", "100", "90"),
            self.calculated("CHUNK-001", "8.5", "19.25", "100", "80", "90"),
        ], percentage="87.5")

        density = web_projection.build_density(structure, self.manifest(), calculation)

        self.assertEqual(["CHUNK-001", "CHUNK-002"], [row["chunk_id"] for row in density["items"]])
        self.assertEqual([1000, 2000], [row["indexable_source_words"] for row in density["items"]])
        self.assertEqual([8.5, 12.0], [row["path_rate_per_1000_words"] for row in density["items"]])
        self.assertEqual([19.25, 24.0], [row["occurrence_rate_per_1000_words"] for row in density["items"]])
        self.assertEqual("90", density["items"][0]["canonical_fit_judgment"]["combined"])
        self.assertEqual("100", density["items"][0]["canonical_fit_judgment"]["path_fit_percentage"])
        self.assertEqual("80", density["items"][0]["canonical_fit_judgment"]["occurrence_fit_percentage"])
        self.assertEqual("measured", density["items"][0]["canonical_fit_judgment"]["status"])
        self.assertEqual("87.5", density["fit_percentage"])
        self.assertEqual(4.375, density["fit_rating"])
        self.assertEqual(structure["density"]["targets"], density["targets"])

    def test_unmeasured_or_uncertain_fit_is_not_projected_as_failure(self) -> None:
        structure = self.structure(chunks=("CHUNK-001",))
        calculation = self.calculation([{
            **self.calculated("CHUNK-001", None, None, None, None, None),
            "status": "uncertain",
        }], percentage=None)

        density = web_projection.build_density(structure, self.manifest(chunks=("CHUNK-001",)), calculation)
        judgment = density["items"][0]["canonical_fit_judgment"]

        self.assertIsNone(judgment["combined"])
        self.assertEqual("uncertain", judgment["status"])
        self.assertNotIn("outside_one_or_more_acceptable_bands", judgment.values())
        self.assertIsNone(density["fit_percentage"])
        self.assertIsNone(density["fit_rating"])

    @staticmethod
    def calculated(chunk_id, path_rate, occurrence_rate, path_fit, occurrence_fit, unit_fit) -> dict:
        return {
            "chunk_id": chunk_id,
            "path_rate": path_rate,
            "occurrence_rate": occurrence_rate,
            "path_fit_percentage": path_fit,
            "occurrence_fit_percentage": occurrence_fit,
            "unit_fit_percentage": unit_fit,
        }

    @staticmethod
    def calculation(chapters: list[dict], *, percentage) -> dict:
        return {"dimensions": [{
            "dimension_id": "editorial_selectivity",
            "components": [{
                "component_id": "density_fit",
                "percentage": percentage,
                "details": {"chapter_measurements": chapters},
            }],
        }]}

    @staticmethod
    def structure(*, chunks=("CHUNK-001", "CHUNK-002")) -> dict:
        return {"density": {
            "policy_status": "scored",
            "measurement_level": "chapter_or_approved_intellectual_unit",
            "targets": [{"metric": "paths"}, {"metric": "occurrences"}],
            "chapter_measurements": [
                {
                    "chunk_id": chunk_id,
                    "indexable_source_words": (index + 1) * 1000,
                    "locator_bearing_heading_paths": (index + 1) * 8,
                    "locator_occurrences": (index + 1) * 20,
                }
                for index, chunk_id in enumerate(chunks)
            ],
            "maximum_score_contribution": 5,
            "distribution_findings": [],
        }}

    @staticmethod
    def manifest(*, chunks=("CHUNK-001", "CHUNK-002")) -> dict:
        return {"chunks": [
            {
                "chunk_id": chunk_id,
                "title": f"Synthetic unit {index + 1}",
                "source_units": [f"unit-{index + 1}"],
                "owned_document_page_ranges": [[index + 1, index + 1]],
            }
            for index, chunk_id in enumerate(chunks)
        ]}


if __name__ == "__main__":
    unittest.main()
