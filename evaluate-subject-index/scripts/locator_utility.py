"""Deterministic V8 locator diagnostics and binary keep credit."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping


WEAK_PRESENCE_CLASSES = frozenset(
    {"passing_mention", "attribution_only", "citation_only", "incidental_example"}
)
MATERIAL_TREATMENT_CLASSES = frozenset({"substantive", "mixed"})
VALID_TREATMENT_CLASSES = MATERIAL_TREATMENT_CLASSES | WEAK_PRESENCE_CLASSES | {"absent", "unavailable"}
VALID_JUDGMENTS = frozenset({"supported", "partially_supported", "unsupported", "uninspectable"})
VALID_SCOPE_STATUSES = frozenset({"indexable", "excluded", "unavailable", "ambiguous"})
VALID_SEVERITIES = frozenset({"none", "cosmetic", "minor", "major", "critical"})
VALID_CODES = frozenset({"SCP", "COV", "SEL", "CON", "STA", "LOC_POS", "LOC_NEG", "CMP", "HED", "SUB", "XRF", "DEN", "MEC"})
INVALID_LOCATOR_FIT_CODES = frozenset({"COV", "LOC_NEG", "XRF", "DEN"})
VALID_DEFECT_KINDS = frozenset({
    "generic", "central_omission", "fabricated_locator", "nonexistent_locator",
    "out_of_scope_locator", "stance_reversal", "misleading_relationship",
    "substitutive_see", "circular_or_chained_reference", "misleading_access_route",
    "unsupported_reference", "mechanical_invariant", "representation_corruption",
    "clutter_pattern", "density_distribution", "scope_failure",
})
INVALID_DESTINATION_KINDS = frozenset({"fabricated_locator", "nonexistent_locator", "out_of_scope_locator", "scope_failure"})
INVALID_LOCATOR_DEFECT_KINDS = frozenset({"central_omission", "substitutive_see", "circular_or_chained_reference", "unsupported_reference"})

TREATMENT_SCORES = {
    "substantive": Decimal("1.00"),
    "mixed": Decimal("0.70"),
    "weak_presence": Decimal("0.25"),
    "absent": Decimal("0.00"),
    "invalid_destination": Decimal("0.00"),
}
FIT_SCORES = {
    "exact_fit": Decimal("1.00"),
    "material_partial_fit": Decimal("0.70"),
    "material_mismatch": Decimal("0.35"),
    "severe_mismatch": Decimal("0.15"),
    "no_fit": Decimal("0.00"),
}
FIT_RULES = {
    "exact_fit": "F-EXACT-100",
    "material_partial_fit": "F-PARTIAL-070",
    "material_mismatch": "F-MISMATCH-035",
    "severe_mismatch": "F-SEVERE-015",
    "no_fit": "F-NO-FIT-000",
    "uninspectable": "F-UNINSPECTABLE-BOUND",
}


def decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == value.to_integral():
        return str(value.quantize(Decimal(1)))
    return format(value.normalize(), "f")


def inspectability_state(scope: str, treatment: str) -> str:
    if scope == "excluded":
        return "known_excluded_nonindexable"
    if scope == "unavailable" or treatment == "unavailable":
        return "uninspectable_unavailable"
    if scope == "ambiguous":
        return "uninspectable_ambiguous"
    return "inspectable"


def relevant_structured_defects(locator_id: str, defects: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        defect
        for defect in defects
        if locator_id in defect.get("affected_item_ids", [])
    ]


def _defect_errors(locator_id: str, defects: Iterable[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    matched = relevant_structured_defects(locator_id, defects)
    ids = [item.get("defect_id") for item in matched]
    if len(ids) != len(set(ids)):
        errors.append("invalid:duplicate_defect_id")
    for index, defect in enumerate(matched):
        label = f"defect[{index}]"
        if not isinstance(defect.get("defect_id"), str) or not str(defect["defect_id"]).startswith("DEFECT-"):
            errors.append(f"invalid:{label}.defect_id")
        if defect.get("code") not in VALID_CODES:
            errors.append(f"invalid:{label}.code")
        if defect.get("defect_kind") not in VALID_DEFECT_KINDS:
            errors.append(f"invalid:{label}.defect_kind")
        if defect.get("severity") not in {"cosmetic", "minor", "major", "critical"}:
            errors.append(f"invalid:{label}.severity")
        if defect.get("code") in INVALID_LOCATOR_FIT_CODES:
            errors.append(f"invalid:locator_bound_{str(defect.get('code')).lower()}_defect")
        if defect.get("defect_kind") in INVALID_LOCATOR_DEFECT_KINDS:
            errors.append(f"invalid:locator_bound_{defect.get('defect_kind')}_defect")
    return errors


def combined_state_errors(record: Mapping[str, Any], defects: Iterable[Mapping[str, Any]] = ()) -> list[str]:
    required = {"locator_id", "judgment", "treatment_class", "complete_path_fit", "source_scope_status", "error_codes", "severity"}
    errors = [f"missing:{field}" for field in sorted(required - set(record))]
    if errors:
        return errors
    locator_id = record["locator_id"]
    judgment = record["judgment"]
    treatment = record["treatment_class"]
    fit = record["complete_path_fit"]
    scope = record["source_scope_status"]
    codes = record["error_codes"]
    severity = record["severity"]
    if not isinstance(locator_id, str) or not locator_id.startswith("LOC-"):
        errors.append("invalid:locator_id")
    if judgment not in VALID_JUDGMENTS:
        errors.append("invalid:judgment")
    if treatment not in VALID_TREATMENT_CLASSES:
        errors.append("invalid:treatment_class")
    if fit not in {*FIT_SCORES, "uninspectable"}:
        errors.append("invalid:complete_path_fit")
    if scope not in VALID_SCOPE_STATUSES:
        errors.append("invalid:source_scope_status")
    if not isinstance(codes, list) or len(codes) != len(set(codes)) or any(code not in VALID_CODES for code in codes):
        errors.append("invalid:error_codes")
    if severity not in VALID_SEVERITIES:
        errors.append("invalid:severity")
    errors.extend(_defect_errors(str(locator_id), defects))

    if judgment == "uninspectable":
        if fit != "uninspectable" or treatment != "unavailable" or scope not in {"unavailable", "ambiguous"}:
            errors.append("inconsistent:uninspectable_axes")
    elif fit == "uninspectable" or treatment == "unavailable" or scope in {"unavailable", "ambiguous"}:
        errors.append("inconsistent:inspectable_axes")
    if judgment == "supported" and fit != "exact_fit":
        errors.append("inconsistent:supported_requires_exact_fit")
    if judgment == "partially_supported" and fit != "material_partial_fit":
        errors.append("inconsistent:partially_supported_requires_material_partial_fit")
    if treatment == "absent" and fit != "no_fit":
        errors.append("inconsistent:absent_requires_no_fit")
    if scope == "excluded" and fit != "no_fit":
        errors.append("inconsistent:excluded_requires_no_fit")
    if judgment == "supported" and (treatment not in MATERIAL_TREATMENT_CLASSES or scope != "indexable"):
        errors.append("inconsistent:supported_requires_material_indexable_treatment")
    if judgment == "partially_supported" and (treatment in {"absent", "unavailable"} or scope != "indexable"):
        errors.append("inconsistent:partial_requires_present_indexable_treatment")
    if judgment == "unsupported" and fit == "material_partial_fit":
        errors.append("inconsistent:unsupported_cannot_use_partial_fit")
    if severity in {"none", "cosmetic"} and codes:
        errors.append("inconsistent:nontrivial_codes_require_nontrivial_severity")
    if severity in {"minor", "major", "critical"} and not codes and fit in {"exact_fit", "material_partial_fit"} and treatment in MATERIAL_TREATMENT_CLASSES:
        errors.append("inconsistent:nontrivial_severity_without_structured_cause")
    return sorted(set(errors))


@dataclass(frozen=True)
class LocatorUtilityAssignment:
    locator_id: str
    judgment: str
    treatment_class: str | None
    source_scope_status: str | None
    inspectability: str
    error_codes: tuple[str, ...]
    applicable_structured_defect_ids: tuple[str, ...]
    locator_severity: str | None
    treatment_category: str
    treatment_score: Decimal | None
    fit_category: str
    fit_score: Decimal | None
    treatment_rule_id: str
    fit_rule_id: str
    mapping_rule_id: str
    fit_classification_source: str
    diagnostic_credit: Decimal | None
    diagnostic_grade: int | float | None
    rating_credit: Decimal | None
    rating_rule_id: str
    disposition: str
    disposition_reason: str
    uncertainty_lower: Decimal
    uncertainty_upper: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "locator_id": self.locator_id,
            "judgment": self.judgment,
            "treatment_class": self.treatment_class,
            "source_scope_status": self.source_scope_status,
            "inspectability_state": self.inspectability,
            "error_codes": list(self.error_codes),
            "applicable_structured_defect_ids": list(self.applicable_structured_defect_ids),
            "locator_severity": self.locator_severity,
            "treatment_category": self.treatment_category,
            "treatment_score": decimal_text(self.treatment_score),
            "fit_category": self.fit_category,
            "fit_score": decimal_text(self.fit_score),
            "treatment_rule_id": self.treatment_rule_id,
            "fit_rule_id": self.fit_rule_id,
            "mapping_rule_id": self.mapping_rule_id,
            "fit_classification_source": self.fit_classification_source,
            "diagnostic_credit": decimal_text(self.diagnostic_credit),
            "diagnostic_grade": self.diagnostic_grade,
            "rating_credit": decimal_text(self.rating_credit),
            "rating_rule_id": self.rating_rule_id,
            "disposition": self.disposition,
            "disposition_reason": self.disposition_reason,
            "rating_credit_uncertainty_bounds": {
                "lower": decimal_text(self.uncertainty_lower),
                "upper": decimal_text(self.uncertainty_upper),
            },
        }


def _treatment_axis(treatment: str, *, uninspectable: bool, invalid_destination: bool) -> tuple[str, Decimal | None, str]:
    if uninspectable:
        return "uninspectable", None, "T-UNINSPECTABLE-BOUND"
    if invalid_destination:
        return "invalid_destination", Decimal("0"), "T-INVALID-DESTINATION-000"
    if treatment == "substantive":
        return "substantive", Decimal("1"), "T-SUBSTANTIVE-100"
    if treatment == "mixed":
        return "mixed", Decimal("0.7"), "T-MIXED-070"
    if treatment in WEAK_PRESENCE_CLASSES:
        return "weak_presence", Decimal("0.25"), "T-WEAK-025"
    if treatment == "absent":
        return "absent", Decimal("0"), "T-ABSENT-000"
    raise ValueError("invalid:treatment_axis_state")


def assign_locator_utility(record: Mapping[str, Any], defects: Iterable[Mapping[str, Any]] = ()) -> LocatorUtilityAssignment:
    defects = list(defects)
    errors = combined_state_errors(record, defects)
    if errors:
        raise ValueError(";".join(errors))
    locator_id = str(record["locator_id"])
    judgment = str(record["judgment"])
    treatment = str(record["treatment_class"])
    fit = str(record["complete_path_fit"])
    scope = str(record["source_scope_status"])
    codes = tuple(sorted(record["error_codes"]))
    matched = relevant_structured_defects(locator_id, defects)
    invalid_destination = scope == "excluded" or any(item.get("defect_kind") in INVALID_DESTINATION_KINDS for item in matched)
    uninspectable = judgment == "uninspectable"
    treatment_category, treatment_score, treatment_rule = _treatment_axis(treatment, uninspectable=uninspectable, invalid_destination=invalid_destination)
    fit_score = None if fit == "uninspectable" else FIT_SCORES[fit]
    fit_rule = FIT_RULES[fit]
    diagnostic_credit = None if treatment_score is None or fit_score is None else min(treatment_score, fit_score)
    grade_value = None if diagnostic_credit is None else diagnostic_credit * Decimal(100)
    diagnostic_grade = None if grade_value is None else int(grade_value) if grade_value == grade_value.to_integral() else float(grade_value)
    if judgment == "uninspectable":
        rating_credit = None
        rating_rule = "R-UNINSPECTABLE-BOUND"
        lower, upper = Decimal(0), Decimal(1)
        disposition = "bounded"
        reason = "The destination is uninspectable and enters neutral uncertainty bounds."
    elif judgment == "supported":
        rating_credit = Decimal(1)
        rating_rule = "R-SUPPORTED-KEEP-100"
        lower = upper = rating_credit
        disposition = "assessable"
        reason = "The native supported judgment keeps the delivered locator unchanged."
    else:
        rating_credit = Decimal(0)
        rating_rule = "R-NOT-KEPT-000"
        lower = upper = rating_credit
        disposition = "assessable"
        reason = "The native judgment does not keep the delivered locator unchanged."
    return LocatorUtilityAssignment(
        locator_id=locator_id,
        judgment=judgment,
        treatment_class=treatment,
        source_scope_status=scope,
        inspectability=inspectability_state(scope, treatment),
        error_codes=codes,
        applicable_structured_defect_ids=tuple(sorted(str(item["defect_id"]) for item in matched)),
        locator_severity=str(record["severity"]),
        treatment_category=treatment_category,
        treatment_score=treatment_score,
        fit_category=fit,
        fit_score=fit_score,
        treatment_rule_id=treatment_rule,
        fit_rule_id=fit_rule,
        mapping_rule_id=f"{treatment_rule}+{fit_rule}+MIN",
        fit_classification_source="native_complete_path_fit",
        diagnostic_credit=diagnostic_credit,
        diagnostic_grade=diagnostic_grade,
        rating_credit=rating_credit,
        rating_rule_id=rating_rule,
        disposition=disposition,
        disposition_reason=reason,
        uncertainty_lower=lower,
        uncertainty_upper=upper,
    )


def not_measured_assignment(locator_id: str) -> dict[str, Any]:
    return {
        "locator_id": locator_id,
        "judgment": "not_measured",
        "treatment_class": None,
        "source_scope_status": None,
        "inspectability_state": "not_measured",
        "error_codes": [],
        "applicable_structured_defect_ids": [],
        "locator_severity": None,
        "treatment_category": "not_measured",
        "treatment_score": None,
        "fit_category": "not_measured",
        "fit_score": None,
        "treatment_rule_id": "T-NOT-MEASURED-REJECT",
        "fit_rule_id": "F-NOT-MEASURED-REJECT",
        "mapping_rule_id": "T-NOT-MEASURED-REJECT+F-NOT-MEASURED-REJECT+MIN",
        "fit_classification_source": "not_measured",
        "diagnostic_credit": None,
        "diagnostic_grade": None,
        "rating_credit": None,
        "rating_rule_id": "R-NOT-MEASURED-REJECT",
        "disposition": "not_measured",
        "disposition_reason": "The required locator assignment was not measured.",
        "rating_credit_uncertainty_bounds": {"lower": "0", "upper": "1"},
    }
