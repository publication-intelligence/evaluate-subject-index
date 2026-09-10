from __future__ import annotations

import sys
import unittest
import copy
from decimal import Decimal
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TESTS = ROOT / "tests"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS))

from locator_utility import FIT_SCORES, assign_locator_utility  # noqa: E402

try:
    import scoring_core as v5  # noqa: E402
    import dimension_score_v8_cli as v8  # noqa: E402
    import item_grade_v8_cli as item_v8  # noqa: E402
except ModuleNotFoundError:
    v5 = None
    v8 = None
    item_v8 = None

HAS_SCORING_DEPENDENCIES = v5 is not None and v8 is not None and item_v8 is not None


def state(
    judgment: str,
    treatment: str,
    *,
    scope: str = "indexable",
    codes: list[str] | None = None,
    severity: str = "none",
    locator_id: str = "LOC-TEST",
) -> dict:
    return {
        "locator_id": locator_id,
        "judgment": judgment,
        "treatment_class": treatment,
        "source_scope_status": scope,
        "error_codes": list(codes or []),
        "severity": severity,
    }


def defect(
    code: str,
    kind: str,
    severity: str,
    *,
    locator_id: str = "LOC-TEST",
    defect_id: str = "DEFECT-TEST",
    root_cause_family: str = "synthetic_fit_failure",
) -> dict:
    return {
        "defect_id": defect_id,
        "code": code,
        "dimension_owner": "page_reference_reliability",
        "defect_kind": kind,
        "severity": severity,
        "root_cause_family": root_cause_family,
        "affected_item_ids": [locator_id],
    }


def reliability_ledgers(
    locator_states: list[dict],
    treatment_statuses: list[tuple[str, str]] | None = None,
    *,
    locator_not_measured: list[str] | None = None,
    defects: list[dict] | None = None,
    attempt: str = "meaningful_attempt",
) -> dict:
    locators = []
    for index, locator_state in enumerate(locator_states, start=1):
        record = copy.deepcopy(locator_state)
        record.setdefault("locator_id", f"LOC-{index:04d}")
        record.setdefault("error_codes", [])
        record.setdefault("source_scope_status", "indexable")
        record["_source_unit_id"] = "CHUNK-001"
        locators.append(record)
    statuses = treatment_statuses or [("found", "principal")]
    treatments = [
        {
            "treatment_id": f"TREAT-{index:04d}",
            "status": status,
            "locator_class": locator_class,
        }
        for index, (status, locator_class) in enumerate(statuses, start=1)
    ]
    return {
        "locators": locators,
        "locator_original": len(locators) + len(locator_not_measured or []),
        "locator_not_measured": list(locator_not_measured or []),
        "locator_not_measured_units": ["CHUNK-001"] * len(locator_not_measured or []),
        "treatments": treatments,
        "treatment_original": len(treatments),
        "treatment_not_measured": [],
        "defects": list(defects or []),
        "source_units": ["CHUNK-001"],
        "context": {"candidate_attempt": {"status": attempt, "evidence_ids": []}},
    }


def reliability_value(result: dict, field: str) -> Decimal:
    return Decimal(result["reliability_provenance"][field])


@unittest.skipUnless(HAS_SCORING_DEPENDENCIES, "scoring runtime dependencies are unavailable")
class V8SensitivityTests(unittest.TestCase):
    def test_approved_fit_values_are_frozen_regression_expectations(self) -> None:
        self.assertEqual(
            {
                "exact_fit": Decimal("1.00"),
                "material_partial_fit": Decimal("0.70"),
                "material_mismatch": Decimal("0.35"),
                "severe_mismatch": Decimal("0.15"),
                "no_fit": Decimal("0.00"),
            },
            FIT_SCORES,
        )

    def test_locator_diagnostics_and_rating_credit_are_independent(self) -> None:
        cases = [
            (state("supported", "substantive"), [], 100, "1"),
            (state("supported", "mixed"), [], 70, "1"),
            (state("unsupported", "attribution_only", severity="minor"), [], 25, "0"),
            (
                state("unsupported", "substantive", codes=["STA"], severity="major"),
                [defect("STA", "stance_reversal", "major")],
                15,
                "0",
            ),
        ]
        for locator, defects, diagnostic_grade, rating_credit in cases:
            with self.subTest(locator=locator, diagnostic_grade=diagnostic_grade):
                assignment = assign_locator_utility(locator, defects).as_dict()
                self.assertEqual(diagnostic_grade, assignment["diagnostic_grade"])
                self.assertEqual(rating_credit, assignment["rating_credit"])

    def test_contentless_incidental_example_is_weak_and_not_kept(self) -> None:
        assignment = assign_locator_utility(
            state("unsupported", "incidental_example", severity="minor")
        ).as_dict()
        self.assertEqual("weak_presence", assignment["treatment_category"])
        self.assertEqual("exact_fit", assignment["fit_category"])
        self.assertEqual(25, assignment["diagnostic_grade"])
        self.assertEqual("0", assignment["rating_credit"])

    def test_policy_hash_copy_in_worker_provenance_is_not_a_gate(self) -> None:
        frozen_ledgers = {
            "identity": {"policy_sha256": "a" * 64},
        }
        loaded = {
            "policy": {"policy_sha256": "b" * 64},
            "config": {"audit_mode": "full"},
        }
        with mock.patch.object(v8.v5, "preflight_loaded", return_value=(frozen_ledgers, [])), \
             mock.patch.object(v8, "locator_state_requirements", return_value=[]):
            ledgers, missing = v8.preflight_loaded(loaded)
        self.assertIs(ledgers, frozen_ledgers)
        self.assertEqual([], missing)


@unittest.skipUnless(HAS_SCORING_DEPENDENCIES, "scoring runtime dependencies are unavailable")
class V8AdversarialMixtureTests(unittest.TestCase):
    def test_concordance_like_weak_locator_mix_uses_binary_keep_precision(self) -> None:
        locators = [
            state("supported", "substantive", locator_id=f"LOC-{index:04d}")
            for index in range(1, 11)
        ] + [
            state(
                "unsupported",
                "passing_mention",
                severity="minor",
                locator_id=f"LOC-{index:04d}",
            )
            for index in range(11, 101)
        ]
        result = v8.calculate_reliability(reliability_ledgers(locators), "full")
        self.assertEqual(Decimal("0.1"), reliability_value(result, "keep_precision"))
        self.assertEqual(10, result["reliability_provenance"]["keep_precision_numerator"])
        self.assertEqual(Decimal("1"), Decimal(str(result["final_rating"])))

    def test_high_locator_precision_with_poor_recall_is_depressed_by_unchanged_f1(self) -> None:
        locators = [
            state("supported", "substantive", locator_id=f"LOC-{index:04d}")
            for index in range(1, 10)
        ] + [
            state(
                "unsupported",
                "absent",
                codes=["LOC_POS"],
                severity="major",
                locator_id="LOC-0010",
            )
        ]
        result = v8.calculate_reliability(
            reliability_ledgers(
                locators,
                [("found", "supporting"), *[("missed", "supporting")] * 3],
            ),
            "full",
        )
        self.assertEqual(Decimal("0.9"), reliability_value(result, "keep_precision"))
        self.assertEqual(Decimal("0.25"), reliability_value(result, "treatment_recall"))
        self.assertEqual(
            Decimal("0.3913043478260869565217391304"),
            reliability_value(result, "reliability_f1"),
        )
        self.assertEqual(Decimal("2"), Decimal(str(result["final_rating"])))

    def test_one_fabricated_locator_keeps_critical_cap_despite_high_precision(self) -> None:
        locators = [
            state("supported", "substantive", locator_id=f"LOC-{index:04d}")
            for index in range(1, 100)
        ] + [
            state(
                "unsupported",
                "substantive",
                codes=["SCP"],
                severity="critical",
                locator_id="LOC-0100",
            )
        ]
        result = v8.calculate_reliability(
            reliability_ledgers(
                locators,
                defects=[
                    defect(
                        "SCP",
                        "fabricated_locator",
                        "critical",
                        locator_id="LOC-0100",
                        defect_id="DEFECT-FABRICATED",
                    )
                ],
            ),
            "full",
        )
        self.assertEqual(Decimal("0.99"), reliability_value(result, "keep_precision"))
        self.assertEqual("reliability.critical_locator", result["applied_cap"]["cap_id"])
        self.assertEqual(Decimal("2"), Decimal(str(result["final_rating"])))

    def test_wrong_relationship_and_stance_retain_treatment_but_receive_fit_penalties(self) -> None:
        result = v8.calculate_reliability(
            reliability_ledgers(
                [
                    state(
                        "unsupported",
                        "substantive",
                        codes=["CON"],
                        severity="minor",
                        locator_id="LOC-0001",
                    ),
                    state(
                        "unsupported",
                        "substantive",
                        codes=["STA"],
                        severity="major",
                        locator_id="LOC-0002",
                    ),
                ]
            ),
            "full",
        )
        assignments = result["reliability_provenance"]["locator_utility_assignments"]
        self.assertEqual(["1", "1"], [item["treatment_score"] for item in assignments])
        self.assertEqual(["0.35", "0.15"], [item["fit_score"] for item in assignments])
        self.assertEqual(["0.35", "0.15"], [item["diagnostic_credit"] for item in assignments])
        self.assertEqual(Decimal("0"), reliability_value(result, "keep_precision"))

    def test_weak_locator_mixture_obeys_quarter_ceiling_and_no_fit_floor(self) -> None:
        result = v8.calculate_reliability(
            reliability_ledgers(
                [
                    state(
                        "unsupported",
                        "passing_mention",
                        severity="minor",
                        locator_id="LOC-0001",
                    ),
                    state(
                        "partially_supported",
                        "citation_only",
                        severity="minor",
                        locator_id="LOC-0002",
                    ),
                    state(
                        "unsupported",
                        "incidental_example",
                        codes=["HED"],
                        severity="minor",
                        locator_id="LOC-0003",
                    ),
                    state(
                        "unsupported",
                        "attribution_only",
                        codes=["CON"],
                        severity="major",
                        locator_id="LOC-0004",
                    ),
                ],
                defects=[
                    defect(
                        "CON",
                        "generic",
                        "major",
                        locator_id="LOC-0004",
                        defect_id="DEFECT-NO-FIT",
                        root_cause_family="wrong_sense",
                    )
                ],
            ),
            "full",
        )
        assignments = result["reliability_provenance"]["locator_utility_assignments"]
        self.assertEqual(
            ["0.25", "0.25", "0.25", "0"],
            [item["diagnostic_credit"] for item in assignments],
        )
        self.assertEqual(["0", "0", "0", "0"], [item["rating_credit"] for item in assignments])
        self.assertEqual(Decimal("0"), reliability_value(result, "keep_precision"))

    def test_mixed_kept_locators_do_not_reduce_reliability(self) -> None:
        result = v8.calculate_reliability(
            reliability_ledgers(
                [
                    state("supported", "substantive", locator_id="LOC-0001"),
                    state("supported", "mixed", locator_id="LOC-0002"),
                ],
                [("found", "principal"), ("found", "supporting")],
            ),
            "full",
        )
        provenance = result["reliability_provenance"]
        self.assertEqual("1", provenance["keep_precision"])
        self.assertEqual(2, provenance["keep_precision_numerator"])
        self.assertEqual("0.85", provenance["mean_diagnostic_credit"])
        self.assertEqual(Decimal("5"), Decimal(str(result["final_rating"])))

    def test_uninspectable_locator_retains_neutral_keep_bounds(self) -> None:
        result = v8.calculate_reliability(
            reliability_ledgers(
                [
                    state("supported", "mixed", locator_id="LOC-0001"),
                    state(
                        "uninspectable",
                        "unavailable",
                        scope="unavailable",
                        severity="none",
                        locator_id="LOC-0002",
                    ),
                ]
            ),
            "pilot",
        )
        bounds = result["reliability_provenance"]["keep_precision_uncertainty"]
        self.assertEqual({"lower": "0.5", "central": "1", "upper": "1"}, bounds)

    def test_full_mode_rejects_not_measured_locator(self) -> None:
        report = v8.locator_fit_preflight(
            reliability_ledgers(
                [state("supported", "substantive", locator_id="LOC-0001")],
                locator_not_measured=["LOC-0002"],
            ),
            "full",
        )
        self.assertIn(
            "required_locator_not_measured",
            [item["code"] for item in report["invalid_or_contradictory_state"]],
        )

    def test_expected_treatment_without_locator_assignments_is_defined_zero(self) -> None:
        result = v8.calculate_reliability(
            reliability_ledgers([], [("missed", "supporting")]), "full"
        )
        keep_denominator = next(
            item for item in result["denominators"]["components"]
            if item["component_id"] == "keep_precision"
        )
        self.assertEqual(
            "expected_treatments_but_no_locator_assignments",
            keep_denominator["defined_zero_rule"],
        )
        self.assertEqual(0, result["final_rating"])

    def test_item_projection_keeps_diagnostic_grade_separate_from_rating_credit(self) -> None:
        assignment = assign_locator_utility(
            state("supported", "mixed", locator_id="LOC-0001")
        ).as_dict()
        evidence_identity = {"source_sha256": "a" * 64}
        blank_grade = {
            "score": 100,
            "rating": 5,
            "band": "excellent",
            "color_token": "grade_excellent",
            "status": "passes",
        }
        base = {
            "schema_version": "subject-index-item-assessments-v3",
            "evaluation_id": "EVAL-TEST",
            "evidence_identity": evidence_identity,
            "locator_assessments": [{
                "locator_id": "LOC-0001",
                "path_id": "PATH-0001",
                "summary": "Independently useful comparative fact.",
                "evidence_ids": [],
                "grade": blank_grade,
                "popover": {"summary": "old", "grade": blank_grade, "factors": []},
            }],
            "path_assessments": [],
            "heading_node_assessments": [],
            "cross_reference_assessments": [],
            "source_subject_assessments": [],
        }
        calculation = {
            "schema_version": "subject-index-dimension-calculations-v5",
            "evaluation_id": "EVAL-TEST",
            "evidence_identity": evidence_identity,
            "dimensions": [{
                "dimension_id": "page_reference_reliability",
                "reliability_provenance": {
                    "locator_utility_assignments": [assignment],
                    "counts_by_treatment_tier": {"mixed": 1},
                    "counts_by_fit_tier": {"exact_fit": 1},
                    "counts_by_diagnostic_credit_value": {"0.7": 1},
                    "counts_by_rating_credit_value": {"1": 1},
                },
            }],
        }
        review = {
            "schema_version": "subject-index-structure-locator-review-v1",
            "review_id": "STRUCTREV-AAAAAAAAAAAA",
            "review_sha256": "b" * 64,
            "path_reviews": [],
        }
        projected = item_v8.build_v8_assessments(base, calculation, review)
        locator = projected["locator_assessments"][0]
        self.assertEqual(70, locator["grade"]["score"])
        self.assertEqual("1", locator["dimension_reliability_credit"])
        self.assertEqual(70, locator["locator_explanation"]["diagnostic_locator_grade"]["score"])
        self.assertEqual("1", locator["locator_explanation"]["keep_rating_credit"]["credit"])

    def test_non_reliability_dimension_outputs_pass_through_unchanged(self) -> None:
        dimension_ids = [
            "meaningful_coverage",
            "editorial_selectivity",
            "conceptual_stance_fidelity",
            "findability_navigation",
            "mechanics_consistency",
        ]

        def sentinel(dimension_id: str) -> dict:
            return {
                "dimension_id": dimension_id,
                "status": "scored",
                "input_roles": ["structure_audit"],
                "awarded_points": 0,
                "unchanged_sentinel": dimension_id,
            }

        reliability = sentinel("page_reference_reliability")
        ledgers = {
            "identity": {
                field: "a" * 64 for field in v5.CALCULATION_EVIDENCE_IDENTITY_FIELDS
            },
            "expected_subject_ids": [],
        }
        loaded = {
            "config": {"evaluation_id": "EVAL-TEST", "audit_mode": "full"},
            "input_artifacts": [
                {"role": "policy", "path": "policy.json", "sha256": "b" * 64, "schema_version": "subject-index-evaluation-policy-v4"},
                {"role": "structure_audit", "path": "structure.json", "sha256": "c" * 64, "schema_version": "structure-audit-v5"},
            ],
        }
        fit_report = {
            "invalid_or_contradictory_state": [],
            "unresolved_complete_path_fit": [],
            "compatibility_classifications": [],
            "group_counts": {},
            "unresolved_reason_counts": {},
        }
        with mock.patch.object(v8, "preflight_loaded", return_value=(ledgers, [])), \
             mock.patch.object(v8, "locator_fit_preflight", return_value=fit_report), \
             mock.patch.object(v8, "calculate_reliability", return_value=reliability), \
             mock.patch.object(v8.v5, "calculate_coverage", return_value=sentinel(dimension_ids[0])), \
             mock.patch.object(v8.v5, "calculate_selectivity", return_value=sentinel(dimension_ids[1])), \
             mock.patch.object(v8.v5, "calculate_concept", return_value=sentinel(dimension_ids[2])), \
             mock.patch.object(v8.v5, "calculate_findability", return_value=sentinel(dimension_ids[3])), \
             mock.patch.object(v8.v5, "calculate_mechanics", return_value=sentinel(dimension_ids[4])):
            calculation = v8.calculate_loaded(loaded)
        observed = {
            item["dimension_id"]: item["unchanged_sentinel"]
            for item in calculation["dimensions"]
            if item["dimension_id"] != "page_reference_reliability"
        }
        self.assertEqual({dimension_id: dimension_id for dimension_id in dimension_ids}, observed)


if __name__ == "__main__":
    unittest.main()
