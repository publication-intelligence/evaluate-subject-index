from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dimension_score_v8_cli as score_cli  # noqa: E402
import web_projection  # noqa: E402


class ReportingMetadataTests(unittest.TestCase):
    def test_projection_preserves_ordered_canonical_limitations_before_unique_cautions(self) -> None:
        canonical = [
            "Source-span limitation.",
            web_projection.DISPLAY_CAUTIONS[0],
            "Density-measurement limitation.",
        ]

        projected = web_projection._projection_limitations({"limitations": canonical})

        self.assertEqual(
            [canonical[0], canonical[1], canonical[2], *web_projection.DISPLAY_CAUTIONS[1:]],
            projected,
        )

    def test_public_density_distinguishes_current_precision_from_historical_rounding(self) -> None:
        structure = {
            "density": {
                "rounding": "nearest_0.5_after_aggregation",
                "chapter_measurements": [{"chunk_id": "CHUNK-001"}],
            }
        }
        calculation = {
            "calculation_profile": "subject-index-dimension-calculation-v7",
            "final_rounding": {"mode": "ROUND_HALF_UP", "quantum": "0.01"},
            "dimensions": [{
                "dimension_id": "editorial_selectivity",
                "components": [{
                    "component_id": "density_fit",
                    "percentage": "96.79542964790679102720301414",
                    "details": {"chapter_measurements": [{
                        "chunk_id": "CHUNK-001",
                        "path_fit_percentage": "100",
                        "occurrence_fit_percentage": "100",
                        "unit_fit_percentage": "100",
                    }]},
                }],
            }],
        }
        original = copy.deepcopy(structure)

        density = score_cli._public_density(structure, calculation)

        self.assertEqual(original, structure)
        self.assertEqual("none", density["rounding"])
        self.assertEqual(
            {
                "value": "nearest_0.5_after_aggregation",
                "source": "frozen_density_policy_and_structure",
                "applied_to_current_calculation": False,
            },
            density["historical_rounding"],
        )
        self.assertEqual(
            {
                "profile_id": "subject-index-dimension-calculation-v7",
                "density_fit_precision": "full_precision",
                "dimension_percentage_precision": "full_precision",
                "weighted_contribution_precision": "full_precision",
                "overall_percentage_rounding": {"mode": "ROUND_HALF_UP", "quantum": "0.01"},
            },
            density["current_calculation_profile"],
        )
        self.assertEqual("96.79542964790679102720301414", density["density_fit_percentage"])


if __name__ == "__main__":
    unittest.main()
