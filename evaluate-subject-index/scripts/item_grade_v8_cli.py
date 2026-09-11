#!/usr/bin/env python3
"""Build V8 diagnostic item projections from a frozen V8 calculation ledger."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import item_projection_core as items
import scoring_core as v5
from structure_locator_review import (
    StructureReviewError,
    canonical_hash as structure_review_hash,
    validate_structure_locator_review_semantics,
)
from heading_access_provenance import (
    HeadingAccessProvenanceError,
    build_structure_causal_projection,
    causal_provenance_by_node,
    validate_causal_projection_source,
    validate_heading_access_provenance,
)


SCHEMA_VERSION = "subject-index-item-assessments-v7"
GRADING_POLICY = "subject-index-item-grading-v4"


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else v5.decimal_value(value)


def _grade_score(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    score = value * Decimal(100)
    return int(score) if score == score.to_integral() else float(score)


def _reliability(calculation: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = [
        item
        for item in calculation.get("dimensions", [])
        if item.get("dimension_id") == "page_reference_reliability"
    ]
    if len(matches) != 1:
        raise ValueError("v8_reliability_dimension_required")
    return matches[0]


def _score_text(value: int | float | None) -> str:
    if value is None:
        return "not measured"
    return str(value)


def _fit_rationale_required(assignment: Mapping[str, Any]) -> bool:
    treatment_score = _decimal(assignment.get("treatment_score"))
    fit_score = _decimal(assignment.get("fit_score"))
    return bool(
        treatment_score != fit_score
        or fit_score != Decimal("1")
        or assignment.get("supplemental_fit_decision_id")
        or "F-COMPAT-LEGACY-FIT-CONFLICT-TO-SUPPLEMENT-V1"
        in assignment.get("compatibility_rule_ids", [])
    )


def _mechanical_fit_rationale(assignment: Mapping[str, Any]) -> str:
    score = _grade_score(_decimal(assignment["fit_score"]))
    category = str(assignment["fit_category"]).replace("_", " ")
    return (
        f"{category.capitalize()} ({_score_text(score)}/100) follows mechanically from "
        f"{assignment['fit_rule_id']} and the structured complete-path judgment."
    )


def _locator_explanation(
    assessment: Mapping[str, Any],
    assignment: Mapping[str, Any],
    judgment: Mapping[str, Any] | None,
    supplemental_rationale: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    evidence_summary = str(
        (judgment or {}).get("evidence_summary", assessment.get("summary", ""))
    ).strip()
    if not evidence_summary:
        raise ValueError(f"locator_evidence_summary_required:{assignment['locator_id']}")
    rationale_required = _fit_rationale_required(assignment)
    legacy_compatibility = False
    if supplemental_rationale is not None:
        fit_rationale = str(supplemental_rationale["rationale"]).strip()
        fit_rationale_source = str(supplemental_rationale["source"])
    elif judgment is not None and str(judgment.get("fit_rationale", "")).strip():
        fit_rationale = str(judgment["fit_rationale"]).strip()
        fit_rationale_source = "authored_locator_audit"
    elif rationale_required:
        schema_version = None if judgment is None else judgment.get("_audit_schema_version")
        if schema_version == "locator-audit-v2":
            raise ValueError(f"fit_rationale_required:{assignment['locator_id']}")
        fit_rationale = None
        fit_rationale_source = "historical_contract_not_available"
        legacy_compatibility = True
    else:
        fit_rationale = _mechanical_fit_rationale(assignment)
        fit_rationale_source = "mechanical_structured_category_rule"

    treatment_score = _grade_score(_decimal(assignment["treatment_score"]))
    fit_score = _grade_score(_decimal(assignment["fit_score"]))
    diagnostic_score = assignment["diagnostic_grade"]
    evidence_ids = sorted(
        {
            *assessment.get("evidence_ids", []),
            assignment["locator_id"],
            *assignment["applicable_structured_defect_ids"],
            *assignment.get("supplemental_fit_evidence_ids", []),
        }
    )
    return (
        {
            "locator_id": assignment["locator_id"],
            "path_id": assessment["path_id"],
            "evidence_summary": evidence_summary,
            "page_treatment": {
                "category": assignment["treatment_category"],
                "score": treatment_score,
                "rule_id": assignment["treatment_rule_id"],
                "rationale": evidence_summary,
                "rationale_source": "authored_evidence_summary",
            },
            "complete_path_fit": {
                "category": assignment["fit_category"],
                "score": fit_score,
                "rule_id": assignment["fit_rule_id"],
                "rationale": fit_rationale,
                "rationale_source": fit_rationale_source,
            },
            "diagnostic_locator_grade": {
                "rule_id": assignment["mapping_rule_id"],
                "calculation": (
                    f"min({_score_text(treatment_score)}, {_score_text(fit_score)}) = "
                    f"{_score_text(diagnostic_score)}"
                ),
                "score": diagnostic_score,
                "credit": assignment["diagnostic_credit"],
            },
            "keep_rating_credit": {
                "keep_decision": assignment["judgment"] == "supported",
                "rule_id": assignment["rating_rule_id"],
                "credit": assignment["rating_credit"],
            },
            "evidence_ids": evidence_ids,
            "structured_defect_ids": list(
                assignment["applicable_structured_defect_ids"]
            ),
            "fit_rationale_required": rationale_required,
        },
        legacy_compatibility,
    )


def _locator_factor(
    assignment: Mapping[str, Any], explanation: Mapping[str, Any]
) -> list[dict[str, Any]]:
    return [
        {
            "factor_id": "page_treatment",
            "label": "Page treatment",
            "status": assignment["treatment_category"],
            "score": _grade_score(_decimal(assignment["treatment_score"])),
            "weight": 0,
            "explanation": explanation["evidence_summary"],
            "evidence_ids": explanation["evidence_ids"],
        },
        {
            "factor_id": "complete_path_fit",
            "label": "Complete-path fit",
            "status": assignment["fit_category"],
            "score": _grade_score(_decimal(assignment["fit_score"])),
            "weight": 0,
            "explanation": (
                explanation["complete_path_fit"]["rationale"]
                or explanation["evidence_summary"]
            ),
            "evidence_ids": explanation["evidence_ids"],
        },
        {
            "factor_id": "diagnostic_locator_grade",
            "label": "Diagnostic locator grade",
            "status": assignment["disposition"],
            "score": assignment["diagnostic_grade"],
            "weight": 0,
            "explanation": explanation["diagnostic_locator_grade"]["calculation"],
            "evidence_ids": explanation["evidence_ids"],
        },
    ]


def _structure_metric_summary(review: Mapping[str, Any]) -> str:
    displayed = review["displayed_locator_count"]
    atomic = review["atomic_assignment_count"]
    maximum = review["maximum_range_span"]
    return (
        f"{displayed} displayed locator(s); {atomic} expanded atomic page assignment(s); "
        f"longest continuous range {maximum} page(s). Displayed locators drive locator-string review; "
        "range span drives the separate long-range review. Neither numerical trigger alone is a defect."
    )


def build_v8_assessments(
    base_items: Mapping[str, Any],
    calculation: Mapping[str, Any],
    structure_review: Mapping[str, Any],
    structure_document: Mapping[str, Any],
    locator_documents: list[Mapping[str, Any]] | None = None,
    missing_documents: list[Mapping[str, Any]] | None = None,
    supplemental_fit_rationales: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project item diagnostics and score-free causal provenance."""

    if base_items.get("schema_version") != "subject-index-item-assessments-v3":
        raise ValueError("base_item_assessments_required")
    if calculation.get("schema_version") != "subject-index-dimension-calculations-v5":
        raise ValueError("v8_calculation_required")
    if base_items.get("evaluation_id") != calculation.get("evaluation_id"):
        raise ValueError("item_calculation_evaluation_mismatch")
    if base_items.get("evidence_identity") != calculation.get("evidence_identity"):
        raise ValueError("item_calculation_evidence_identity_mismatch")
    locator_documents = locator_documents or []
    missing_documents = missing_documents or []
    validate_heading_access_provenance(
        structure_document, locator_documents, missing_documents
    )

    result = deepcopy(base_items)
    provenance = _reliability(calculation)["reliability_provenance"]
    assignments = {
        item["locator_id"]: item
        for item in provenance["locator_utility_assignments"]
    }
    item_ids = {item.get("locator_id") for item in result.get("locator_assessments", [])}
    if item_ids != set(assignments):
        raise ValueError("item_locator_utility_ledger_mismatch")

    judgments: dict[str, dict[str, Any]] = {}
    for document in locator_documents:
        schema_version = document.get("schema_version")
        for record in document.get("judgments", []):
            enriched = deepcopy(record)
            enriched["_audit_schema_version"] = schema_version
            if enriched.get("locator_id") in judgments:
                raise ValueError("duplicate_locator_explanation_source")
            judgments[enriched["locator_id"]] = enriched
    supplemental_fit_rationales = supplemental_fit_rationales or {}
    legacy_compatibility_mode = False
    for assessment in result["locator_assessments"]:
        assignment = assignments[assessment["locator_id"]]
        explanation, legacy_compatibility = _locator_explanation(
            assessment,
            assignment,
            judgments.get(assessment["locator_id"]),
            supplemental_fit_rationales.get(assessment["locator_id"]),
        )
        legacy_compatibility_mode = legacy_compatibility_mode or legacy_compatibility
        score = assignment["diagnostic_grade"]
        assessment["grade"] = items.grade(score)
        assessment["dimension_reliability_credit"] = assignment["rating_credit"]
        assessment["locator_utility"] = deepcopy(assignment)
        assessment["locator_explanation"] = explanation
        assessment["summary"] = explanation["evidence_summary"]
        assessment["popover"]["summary"] = explanation["evidence_summary"]
        assessment["popover"]["grade"] = assessment["grade"]
        assessment["popover"]["factors"] = _locator_factor(assignment, explanation)
        assessment.pop("credit_tier", None)
        assessment.pop("disqualifying_codes", None)
        assessment.pop("disqualifying_defect_ids", None)

    review_by_path = {
        item["path_id"]: item for item in structure_review.get("path_reviews", [])
    }
    for path in result.get("path_assessments", []):
        page_component = next(
            (
                item
                for item in path.get("component_results", [])
                if item.get("dimension_id") == "page_reference_reliability"
            ),
            None,
        )
        if page_component is not None:
            page_component["score"] = None
            page_component["measurement_status"] = "locator_level_only"
            page_component["summary"] = (
                "V8 exposes each locator grade as a diagnostic of treatment and complete-path fit. "
                "No path-level average is canonical, and Page-reference Reliability is reconstructed "
                "only from binary keep credit plus expected-treatment recall."
            )
            page_factor = next(
                (
                    item
                    for item in path.get("popover", {}).get("factors", [])
                    if item.get("factor_id") == "page_reference_reliability"
                ),
                None,
            )
            if page_factor is not None:
                page_factor["score"] = None
                page_factor["status"] = "locator_level_only"
                page_factor["explanation"] = page_component["summary"]
            path_score = items.weighted_mean(
                (item.get("score"), item.get("weight", 0))
                for item in path.get("component_results", [])
            )
            path["grade"] = items.grade(path_score)
            path["popover"]["grade"] = deepcopy(path["grade"])
            path["popover"]["summary"] = (
                "Complete-path display summary from non-reliability diagnostics only. "
                "Locator utility remains individually displayed and is not averaged here."
            )
        metric = review_by_path.get(path.get("path_id"))
        if metric is not None:
            path["locator_string_review"] = {
                key: deepcopy(metric[key])
                for key in (
                    "delivered_displayed_locator_ids",
                    "displayed_locator_count",
                    "displayed_locators",
                    "expanded_atomic_locator_ids",
                    "atomic_assignment_count",
                    "maximum_range_span",
                    "long_displayed_locator_string_review_trigger",
                    "long_continuous_range_review_trigger",
                    "independent_architecture_evidence",
                    "final_architecture_disposition",
                    "applicable_structured_defect_ids",
                    "deterministic_derivation_rule_ids",
                    "deterministic_mapping_rule_id",
                )
            }
            path["popover"]["factors"].append(
                {
                    "factor_id": "locator_string_and_range_review",
                    "label": "Locator-string and range review",
                    "status": metric["final_architecture_disposition"],
                    "score": None,
                    "weight": 0,
                    "explanation": _structure_metric_summary(metric),
                    "evidence_ids": [
                        *metric["delivered_displayed_locator_ids"],
                        *metric["expanded_atomic_locator_ids"],
                        *metric["applicable_structured_defect_ids"],
                    ],
                }
            )

    causal_by_node = {
        item["node_id"]: item
        for item in causal_provenance_by_node(structure_document)
    }
    assessment_node_ids = {
        item.get("node_id") for item in result.get("heading_node_assessments", [])
    }
    if assessment_node_ids != set(causal_by_node):
        raise ValueError("item_heading_access_provenance_node_mismatch")
    for assessment in result.get("heading_node_assessments", []):
        node_causality = causal_by_node[assessment["node_id"]]
        assessment["heading_access_status"] = node_causality["status"]
        assessment["heading_access_causal_findings"] = deepcopy(
            node_causality["causal_findings"]
        )
        if "primary_finding_id" in node_causality:
            assessment["heading_access_primary_finding_id"] = node_causality[
                "primary_finding_id"
            ]
            assessment["heading_access_primary_basis"] = deepcopy(
                node_causality["primary_basis"]
            )

    result["schema_version"] = SCHEMA_VERSION
    result["grading_policy"] = GRADING_POLICY
    result["explanation_contract"] = {
        "contract_version": "locator-explanations-v2",
        "heading_access_causal_contract": "heading-access-causal-findings-v1",
        "authored_evidence_is_primary": True,
        "prose_used_in_scoring": False,
        "causal_provenance_used_in_scoring": False,
        "legacy_compatibility_mode": legacy_compatibility_mode,
    }
    result["grade_disclosure"] = (
        "V8 locator grades equal 100 times min(page-treatment score, complete-path-fit score) and remain diagnostic. "
        "They are not averaged to reconstruct Page-reference Reliability; its precision input uses binary "
        "locator_utility_assignments[].rating_credit, where supported means keep unchanged. Editorial Selectivity remains separate."
    )
    result["locator_grading_provenance"] = {
        "model": "two_axis_diagnostic_minimum_with_binary_keep_credit_v1",
        "page_treatment_mapping": {
            "substantive": "1",
            "mixed": "0.7",
            "weak_presence": "0.25",
            "absent": "0",
            "invalid_destination": "0",
            "uninspectable": None,
        },
        "complete_path_fit_mapping": {
            "exact_fit": "1",
            "material_partial_fit": "0.7",
            "material_mismatch": "0.35",
            "severe_mismatch": "0.15",
            "no_fit": "0",
            "uninspectable": None,
        },
        "diagnostic_combination_rule": "min(page_treatment_score, complete_path_fit_score)",
        "diagnostic_grade_rule": "100 * diagnostic_credit",
        "rating_credit_rule": "supported=1; partially_supported=0; unsupported=0; uninspectable/not_measured=null",
        "calculation_locator_utility_ledger_sha256": v5.canonical_hash(
            {"locator_utility_assignments": provenance["locator_utility_assignments"]}
        ),
        "diagnostic_grades_used_in_dimension_arithmetic": False,
        "selectivity_mapping_unchanged": True,
        "weak_presence_selectivity_credit": 0,
        "counts_by_treatment_tier": deepcopy(provenance["counts_by_treatment_tier"]),
        "counts_by_fit_tier": deepcopy(provenance["counts_by_fit_tier"]),
        "counts_by_diagnostic_credit_value": deepcopy(
            provenance["counts_by_diagnostic_credit_value"]
        ),
        "counts_by_rating_credit_value": deepcopy(
            provenance["counts_by_rating_credit_value"]
        ),
    }
    result["structure_locator_review_binding"] = {
        "schema_version": structure_review["schema_version"],
        "review_id": structure_review["review_id"],
        "review_sha256": structure_review["review_sha256"],
    }
    if "locator_fit_compatibility" in calculation:
        result["locator_fit_compatibility"] = deepcopy(
            calculation["locator_fit_compatibility"]
        )
    if "locator_fit_supplement" in calculation:
        result["locator_fit_supplement"] = deepcopy(
            calculation["locator_fit_supplement"]
        )
    result["heading_access_causal_provenance"] = list(causal_by_node.values())
    items.rebuild_summary(result)
    def credit_tier(item: Mapping[str, Any], field: str) -> str:
        if item["disposition"] == "bounded":
            return "uninspectable"
        if item["disposition"] == "not_measured":
            return "not_measured"
        return str(item[field])

    result["summary"]["locator_utility_tiers"] = {
        "treatment": dict(sorted(Counter(item["treatment_category"] for item in assignments.values()).items())),
        "fit": dict(sorted(Counter(item["fit_category"] for item in assignments.values()).items())),
        "diagnostic_credit": dict(sorted(Counter(credit_tier(item, "diagnostic_credit") for item in assignments.values()).items())),
        "rating_credit": dict(sorted(Counter(credit_tier(item, "rating_credit") for item in assignments.values()).items())),
    }
    return result


def command_build_assessments(args: argparse.Namespace) -> None:
    try:
        items_path = Path(args.base_items).resolve()
        calculation_path = Path(args.calculation).resolve()
        review_path = Path(args.structure_locator_review).resolve()
        structure_path = Path(args.structure_audit).resolve()
        output_path = Path(args.output).resolve()
        base_items = v5.load_json(items_path, "Base item assessments")
        calculation = v5.load_json(calculation_path, "V8 calculation")
        review = v5.load_json(review_path, "V8 structure-locator review")
        structure = v5.load_json(structure_path, "Frozen structure audit")
        locator_documents = []
        for index, stored in enumerate(args.locator_audit or []):
            document = v5.load_json(Path(stored).resolve(), f"Locator audit {index}")
            schema_name = {"locator-audit-v2": "locator-audit-v2.schema.json"}.get(document.get("schema_version"))
            v5.require(
                schema_name is not None,
                "unsupported_locator_audit_schema",
                "V8 item projection accepts current locator-audit-v2 only.",
            )
            v5.validate_schema_document(document, schema_name, f"Locator audit {index}")
            locator_documents.append(document)
        missing_documents = []
        for index, stored in enumerate(args.missing_access_audit or []):
            document = v5.load_json(Path(stored).resolve(), f"Missing-access audit {index}")
            v5.validate_schema_document(
                document,
                "missing-access-audit.schema.json",
                f"Missing-access audit {index}",
            )
            missing_documents.append(document)
        v5.validate_schema_document(
            base_items, "item-assessments-v3.schema.json", "Base item assessments"
        )
        v5.validate_schema_document(
            calculation, "dimension-calculations-v5.schema.json", "V8 calculation"
        )
        v5.validate_schema_document(
            review,
            "structure-locator-review-v1.schema.json",
            "V8 structure-locator review",
        )
        v5.validate_schema_document(
            structure, "structure-audit-v6.schema.json", "Frozen structure audit"
        )
        projection_source_path = None
        if "causal_projection" in structure:
            v5.require(
                bool(args.causal_projection_source),
                "causal_projection_source_required",
                "A projected structure audit requires its frozen V5 source for byte-identity validation.",
            )
            projection_source_path = Path(args.causal_projection_source).resolve()
            projection_source = v5.load_json(
                projection_source_path, "Frozen causal-projection source"
            )
            v5.validate_schema_document(
                projection_source,
                "structure-audit-v5.schema.json",
                "Frozen causal-projection source",
            )
            v5.require(
                structure["causal_projection"]["source_structure_audit_file_sha256"]
                == v5.sha256_file(projection_source_path),
                "causal_projection_source_hash_mismatch",
                "The projected structure audit does not bind the supplied frozen V5 source.",
            )
            validate_causal_projection_source(structure, projection_source)
        v5.require(
            calculation.get("calculation_sha256")
            == v5.canonical_hash(calculation, "calculation_sha256"),
            "calculation_self_hash_mismatch",
            "The V8 calculation self-hash does not reconstruct.",
        )
        v5.require(
            review.get("review_sha256")
            == structure_review_hash(review, "review_sha256"),
            "structure_review_hash_mismatch",
            "The V8 structure-locator review self-hash does not reconstruct.",
        )
        validate_structure_locator_review_semantics(review)
        structure_file_sha256 = v5.sha256_file(structure_path)
        projection_source_sha256 = structure.get("causal_projection", {}).get(
            "source_structure_audit_file_sha256"
        )
        valid_structure_bindings = {
            digest
            for digest in (structure_file_sha256, projection_source_sha256)
            if isinstance(digest, str)
        }
        v5.require(
            review.get("inputs", {}).get("structure_audit_file_sha256")
            in valid_structure_bindings,
            "structure_review_binding_mismatch",
            "The structure-locator review binds neither the supplied structure audit nor its frozen causal-projection source.",
        )
        v5.require(
            calculation.get("evidence_identity", {}).get(
                "structure_audit_file_sha256"
            )
            in valid_structure_bindings,
            "item_calculation_structure_binding_mismatch",
            "The V8 calculation binds neither the supplied structure audit nor its frozen causal-projection source.",
        )
        v5.require(
            not review.get("summary", {}).get("removed_historical_defect_ids"),
            "score_only_migration_item_projection_required",
            "Current item projection cannot consume a structure review that removes historical defects.",
        )
        result = build_v8_assessments(
            base_items,
            calculation,
            review,
            structure,
            locator_documents=locator_documents,
            missing_documents=missing_documents,
        )
        v5.validate_schema_document(
            result, "item-assessments-v7.schema.json", "Generated V8 item assessments"
        )
        v5.require(
            not v5.aliases_existing_file(
                output_path,
                {
                    items_path,
                    calculation_path,
                    review_path,
                    structure_path,
                    *({projection_source_path} if projection_source_path else set()),
                    *(Path(path).resolve() for path in (args.locator_audit or [])),
                    *(Path(path).resolve() for path in (args.missing_access_audit or [])),
                },
            ),
            "output_aliases_frozen_input",
            "V8 item assessments must not overwrite a bound input artifact.",
        )
        v5.write_json(output_path, result)
        v5.emit(
            {
                "command": "build-v8-item-assessments",
                "ok": True,
                "evaluation_id": result["evaluation_id"],
                "schema_version": result["schema_version"],
                "grading_policy": result["grading_policy"],
                "artifact_written": str(output_path),
            }
        )
    except (OSError, ValueError, v5.CalculationError, StructureReviewError, HeadingAccessProvenanceError) as exc:
        if isinstance(exc, (v5.CalculationError, StructureReviewError, HeadingAccessProvenanceError)):
            error = {"code": exc.code, "message": exc.message, "details": exc.details}
        else:
            error = {"code": "item_projection_error", "message": str(exc)}
        v5.emit(
            {"command": "build-v8-item-assessments", "ok": False, "error": error},
            1,
        )


def command_project_structure_causality(args: argparse.Namespace) -> None:
    """Create a V6 reporting projection without changing the frozen V5 audit."""

    try:
        structure_path = Path(args.structure_audit).resolve()
        projection_path = Path(args.projection_input).resolve()
        output_path = Path(args.output).resolve()
        structure = v5.load_json(structure_path, "Frozen structure audit")
        projection = v5.load_json(projection_path, "Heading-access causal projection input")
        v5.validate_schema_document(
            structure, "structure-audit-v5.schema.json", "Frozen structure audit"
        )
        v5.validate_schema_document(
            projection,
            "heading-access-causal-projection-input.schema.json",
            "Heading-access causal projection input",
        )
        v5.require(
            projection.get("structure_audit_file_sha256")
            == v5.sha256_file(structure_path),
            "causal_projection_source_hash_mismatch",
            "The causal projection input does not bind the supplied frozen structure bytes.",
        )
        locator_documents = []
        for index, stored in enumerate(args.locator_audit or []):
            document = v5.load_json(Path(stored).resolve(), f"Locator audit {index}")
            v5.validate_schema_document(
                document, "locator-audit-v2.schema.json", f"Locator audit {index}"
            )
            locator_documents.append(document)
        missing_documents = []
        for index, stored in enumerate(args.missing_access_audit or []):
            document = v5.load_json(
                Path(stored).resolve(), f"Missing-access audit {index}"
            )
            v5.validate_schema_document(
                document,
                "missing-access-audit.schema.json",
                f"Missing-access audit {index}",
            )
            missing_documents.append(document)
        result = build_structure_causal_projection(structure, projection)
        result["causal_projection"] = {
            "source_schema_version": "structure-audit-v5",
            "source_structure_audit_file_sha256": v5.sha256_file(structure_path),
            "projection_input_file_sha256": v5.sha256_file(projection_path),
            "scores_recomputed": False,
            "source_artifact_mutated": False,
            "scoring_fields_changed": False,
        }
        validate_causal_projection_source(result, structure)
        v5.validate_schema_document(
            result, "structure-audit-v6.schema.json", "Causal structure projection"
        )
        validate_heading_access_provenance(
            result, locator_documents, missing_documents
        )
        v5.require(
            not v5.aliases_existing_file(
                output_path,
                {
                    structure_path,
                    projection_path,
                    *(Path(path).resolve() for path in (args.locator_audit or [])),
                    *(Path(path).resolve() for path in (args.missing_access_audit or [])),
                },
            ),
            "output_aliases_frozen_input",
            "The causal projection must not overwrite a frozen input artifact.",
        )
        v5.write_json(output_path, result)
        v5.emit(
            {
                "command": "project-structure-causality",
                "ok": True,
                "evaluation_id": result["evaluation_id"],
                "schema_version": result["schema_version"],
                "artifact_written": str(output_path),
                "scores_recomputed": False,
                "frozen_inputs_mutated": False,
            }
        )
    except (OSError, ValueError, v5.CalculationError, HeadingAccessProvenanceError) as exc:
        if isinstance(exc, (v5.CalculationError, HeadingAccessProvenanceError)):
            error = {"code": exc.code, "message": exc.message, "details": exc.details}
        else:
            error = {"code": "causal_projection_error", "message": str(exc)}
        v5.emit({"command": "project-structure-causality", "ok": False, "error": error}, 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser(
        "build-assessments",
        help="Project current V8 diagnostic locator grades and binary keep credit.",
    )
    build.add_argument("--base-items", required=True)
    build.add_argument("--calculation", required=True)
    build.add_argument("--structure-locator-review", required=True)
    build.add_argument(
        "--structure-audit",
        required=True,
        help="Frozen structure-audit-v6 carrying heading-access causal findings.",
    )
    build.add_argument(
        "--causal-projection-source",
        help="Frozen structure-audit-v5 source when --structure-audit is a score-free V6 projection.",
    )
    build.add_argument(
        "--locator-audit",
        action="append",
        default=[],
        help="Frozen locator audit; repeat once per chunk. V2 carries authored fit rationale.",
    )
    build.add_argument(
        "--missing-access-audit",
        action="append",
        default=[],
        help="Frozen missing-access audit; repeat once per chunk for causal ID validation.",
    )
    build.add_argument("--output", required=True)
    build.set_defaults(func=command_build_assessments)
    project = subparsers.add_parser(
        "project-structure-causality",
        help="Add score-free heading-access causality to a frozen structure-audit-v5 copy.",
    )
    project.add_argument("--structure-audit", required=True)
    project.add_argument("--projection-input", required=True)
    project.add_argument("--locator-audit", action="append", default=[])
    project.add_argument("--missing-access-audit", action="append", default=[])
    project.add_argument("--output", required=True)
    project.set_defaults(func=command_project_structure_causality)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
