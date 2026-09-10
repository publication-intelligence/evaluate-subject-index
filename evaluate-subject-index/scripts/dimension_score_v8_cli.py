#!/usr/bin/env python3
"""Deterministic current V8 scoring and projection tooling.

V8 uses the frozen keep judgment as binary rating credit while retaining the
independent page-treatment and complete-path-fit minimum as a diagnostic grade.
Every non-reliability formula, cap, gate, recall rule, and rounding rule is
unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import item_grade_v8_cli as item_grades
import item_projection_core as item_projection
import scoring_core as core
from locator_utility import (
    FIT_SCORES,
    TREATMENT_SCORES,
    assign_locator_utility,
    combined_state_errors,
    not_measured_assignment,
)
from state_cli import (
    STAGES,
    artifact_id,
    evaluation_mutation_lock,
    load_state,
    next_stage,
    now,
    portable_relative_path,
    resolve_artifact_path,
    save_state,
    validate_state,
)
from structure_audit import (
    StructureAuditError,
    id_set_hash,
    materialize_structure_records,
    validate_structure_audit_semantics,
)


RUBRIC_VERSION = "subject-index-rubric-v8"
CALCULATION_PROFILE = "subject-index-dimension-calculation-v4"
CALCULATION_SCHEMA = "subject-index-dimension-calculations-v5"
ITEM_GRADING_POLICY = "subject-index-item-grading-v4"
POLICY_PROFILE = "subject-index-standard-policy-v8"

ZERO = Decimal(0)
ONE = Decimal(1)
TWO = Decimal(2)
FIVE = Decimal(5)

write_json = core.write_json


def _mapping_failure(locator: Mapping[str, Any], errors: Iterable[str]) -> dict[str, Any]:
    return {
        "code": "inconsistent_or_incomplete_locator_utility_state",
        "path": f"locator:{locator.get('locator_id', '<missing>')}",
        "message": "V8 requires an unambiguous structured treatment and complete-path-fit mapping.",
        "locator_id": locator.get("locator_id"),
        "path_id": locator.get("path_id"),
        "frozen_state": {
            field: deepcopy(locator.get(field))
            for field in (
                "judgment",
                "treatment_class",
                "complete_path_fit",
                "source_scope_status",
                "error_codes",
                "severity",
            )
        },
        "state_errors": sorted(set(str(error) for error in errors)),
        "prose_inference_permitted": False,
    }


def _deterministic_fit_record(
    locator: Mapping[str, Any], assignment: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "locator_id": assignment["locator_id"],
        "path_id": locator.get("path_id"),
        "fit_category": assignment["fit_category"],
        "fit_classification_source": assignment["fit_classification_source"],
        "prose_inference_used": False,
    }


def _locator_path_identity_errors(
    ledgers: Mapping[str, Any],
    candidate: Mapping[str, Any] | None,
    inventory: Mapping[str, Any] | None,
) -> dict[str, list[str]]:
    """Reject cross-artifact locator/path identity drift before set hashing."""

    if candidate is None or inventory is None:
        return {}

    candidate_paths_by_locator: dict[str, set[str]] = {}
    candidate_path_counts: Counter[str] = Counter()
    for record in candidate.get("records", []):
        if not isinstance(record, Mapping):
            continue
        path_id = record.get("path_id")
        if not isinstance(path_id, str):
            continue
        candidate_path_counts[path_id] += 1
        for assignment in record.get("locator_assignments", []):
            if not isinstance(assignment, Mapping):
                continue
            locator_id = assignment.get("locator_id")
            if isinstance(locator_id, str):
                candidate_paths_by_locator.setdefault(locator_id, set()).add(
                    path_id
                )

    inventory_paths_by_locator: dict[str, set[str]] = {}
    for locator in inventory.get("locators", []):
        if not isinstance(locator, Mapping):
            continue
        locator_id = locator.get("locator_id")
        path_id = locator.get("path_id")
        if isinstance(locator_id, str) and isinstance(path_id, str):
            inventory_paths_by_locator.setdefault(locator_id, set()).add(path_id)
    inventory_path_counts = Counter(
        item.get("path_id")
        for item in inventory.get("paths", [])
        if isinstance(item, Mapping) and isinstance(item.get("path_id"), str)
    )

    errors: dict[str, list[str]] = {}
    for locator in ledgers["locators"]:
        locator_id = locator.get("locator_id")
        path_id = locator.get("path_id")
        if not isinstance(locator_id, str):
            continue
        locator_errors: list[str] = []
        if not isinstance(path_id, str) or not path_id.startswith("PATH-"):
            locator_errors.append("invalid:complete_path_identity")
        else:
            if candidate_paths_by_locator.get(locator_id) != {path_id}:
                locator_errors.append(
                    "inconsistent:normalized_candidate_locator_path_identity"
                )
            if inventory_paths_by_locator.get(locator_id) != {path_id}:
                locator_errors.append(
                    "inconsistent:item_inventory_locator_path_identity"
                )
            if candidate_path_counts[path_id] != 1:
                locator_errors.append(
                    "inconsistent:normalized_candidate_complete_path_identity"
                )
            if inventory_path_counts[path_id] != 1:
                locator_errors.append(
                    "inconsistent:item_inventory_complete_path_identity"
                )
        if locator_errors:
            errors[locator_id] = sorted(set(locator_errors))
    return errors


def locator_fit_preflight(
    ledgers: dict[str, Any],
    audit_mode: str,
    *,
    candidate: Mapping[str, Any] | None = None,
    inventory: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate native structured fit judgments without consulting prose."""

    invalid: list[dict[str, Any]] = []
    deterministic: list[dict[str, Any]] = []
    path_identity_errors = _locator_path_identity_errors(
        ledgers, candidate, inventory
    )
    for locator in sorted(
        ledgers["locators"], key=lambda item: str(item.get("locator_id", ""))
    ):
        locator_id = locator.get("locator_id")
        if isinstance(locator_id, str) and locator_id in path_identity_errors:
            invalid.append(
                _mapping_failure(locator, path_identity_errors[locator_id])
            )
            continue
        errors = combined_state_errors(locator, ledgers["defects"])
        if errors:
            invalid.append(_mapping_failure(locator, errors))
            continue
        try:
            assignment = assign_locator_utility(locator, ledgers["defects"]).as_dict()
        except ValueError as exc:
            invalid.append(_mapping_failure(locator, str(exc).split(";")))
            continue
        deterministic.append(_deterministic_fit_record(locator, assignment))
    if audit_mode == "full" and ledgers["locator_not_measured"]:
        invalid.append(
            {
                "code": "required_locator_not_measured",
                "path": "locator_not_measured",
                "message": "Full V8 scoring requires every frozen locator assignment to be measured.",
                "locator_ids": sorted(ledgers["locator_not_measured"]),
                "prose_inference_permitted": False,
            }
        )
    deterministic_ids = {item["locator_id"] for item in deterministic}
    invalid_ids = {
        item["locator_id"]
        for item in invalid
        if isinstance(item.get("locator_id"), str)
    }
    core.require(
        not (deterministic_ids & invalid_ids),
        "locator_fit_preflight_group_overlap",
        "Each frozen locator record must appear in exactly one V8 fit-preflight group.",
    )
    locator_invalid_count = sum(
        item.get("code") == "inconsistent_or_incomplete_locator_utility_state"
        for item in invalid
    )
    core.require(
        len(deterministic) + locator_invalid_count
        == len(ledgers["locators"]),
        "locator_fit_preflight_group_coverage_invalid",
        "Every frozen locator record must appear exactly once in a V8 fit-preflight group.",
    )
    return {
        "schema_version": "subject-index-v8-locator-fit-preflight-v1",
        "validated_complete_path_fit": deterministic,
        "invalid_or_contradictory_state": invalid,
        "group_counts": {
            "validated_complete_path_fit": len(deterministic),
            "invalid_or_contradictory_state": len(invalid),
        },
        "aggregate_v8_score_available": False,
        "prose_inference_used": False,
        "_locator_records_by_id": {
            item["locator_id"]: item for item in ledgers["locators"]
        },
    }


def public_locator_fit_preflight(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return the strict public contract without in-memory locator objects."""

    return {
        key: deepcopy(value)
        for key, value in report.items()
        if not key.startswith("_")
    }


def locator_state_requirements(
    ledgers: dict[str, Any],
    audit_mode: str,
) -> list[dict[str, Any]]:
    """Return precise V8 mapping failures without consulting prose."""

    return locator_fit_preflight(ledgers, audit_mode)["invalid_or_contradictory_state"]


def raw_locator_state_requirements(
    config_path: Path,
) -> tuple[str | None, list[dict[str, Any]], list[Path]]:
    """Pre-scan raw audits for actionable V8 field and mapping failures."""

    try:
        config = core.load_json(config_path, "V8 calculation input")
    except (OSError, core.CalculationError):
        return None, [], []
    references = config.get("inputs", {}).get("locator_audits", [])
    if not isinstance(references, list):
        return config.get("evaluation_id"), [], []
    failures: list[dict[str, Any]] = []
    paths: list[Path] = []
    for batch_index, reference in enumerate(references):
        stored = reference.get("path") if isinstance(reference, dict) else None
        if not isinstance(stored, str) or not stored:
            continue
        path = (config_path.parent / stored).resolve()
        paths.append(path)
        try:
            document = core.load_json(path, f"Raw locator audit {batch_index}")
        except (OSError, core.CalculationError):
            continue
        judgments = document.get("judgments")
        if not isinstance(judgments, list):
            failures.append(
                {
                    "code": "missing_locator_judgment_collection",
                    "path": f"locator_audit[{batch_index}].judgments",
                        "message": "V8 scoring requires the frozen locator judgment array.",
                    "state_errors": ["missing:judgments"],
                }
            )
            continue
        for judgment_index, locator in enumerate(judgments):
            if not isinstance(locator, dict):
                failures.append(
                    {
                        "code": "invalid_locator_record",
                        "path": f"locator_audit[{batch_index}].judgments[{judgment_index}]",
                        "message": "V8 requires an object for every locator judgment.",
                        "state_errors": ["invalid:locator_record"],
                    }
                )
                continue
            required = {
                "locator_id",
                "judgment",
                "treatment_class",
                "complete_path_fit",
                "source_scope_status",
                "error_codes",
                "severity",
            }
            absent = sorted(required - set(locator))
            if absent:
                failures.append(
                    _mapping_failure(locator, [f"missing:{field}" for field in absent])
                    | {"path": f"locator_audit[{batch_index}].judgments[{judgment_index}]"}
                )
    return config.get("evaluation_id"), failures, paths


def validate_v8_policy(policy_document: dict[str, Any]) -> None:
    """Validate the frozen policy itself, independent of Markdown wording."""
    core.validate_schema_document(
        policy_document, "evaluation-policy-v4.schema.json", "policy"
    )
    core.require(
        policy_document.get("policy_sha256")
        == core.canonical_hash(policy_document, "policy_sha256"),
        "policy_self_hash_mismatch",
        "The V8 evaluation policy self-hash does not reconstruct.",
    )
    core.require(
        policy_document.get("policy_profile", {}).get("id") == POLICY_PROFILE,
        "policy_profile_mismatch",
        f"The V8 evaluation policy must use profile {POLICY_PROFILE}.",
    )


def load_v8_inputs(config_path: Path) -> dict[str, Any]:
    """Load current V8 inputs and validate each trust boundary once."""

    config = core.load_json(config_path, "Dimension calculation input")
    core.validate_config_shape(config)
    core.validate_schema_document(
        config,
        "dimension-calculation-input.schema.json",
        "Dimension calculation input",
    )
    inputs = config["inputs"]
    policy_path, policy_document, policy_artifact = core.resolve_input(
        config_path, inputs["policy"], "policy"
    )
    validate_v8_policy(policy_document)
    structure_ref = inputs["structure_audit"]
    structure_path, structure_document, structure_artifact = core.resolve_input(
        config_path, structure_ref, "structure_audit"
    )
    core.require(
        structure_document.get("schema_version") == "structure-audit-v5",
        "unsupported_structure_audit_schema",
        "Current V8 scoring requires structure-audit-v5.",
    )
    core.validate_schema_document(
        structure_document, "structure-audit-v5.schema.json", "structure_audit"
    )
    locator_entries: list[tuple[dict[str, Any], dict[str, Any], Path]] = []
    missing_entries: list[tuple[dict[str, Any], dict[str, Any], Path]] = []
    for index, record in enumerate(inputs["locator_audits"]):
        path, document, artifact = core.resolve_input(
            config_path, record, f"locator_audit[{index}]"
        )
        core.validate_schema_document(
            document, "locator-audit-v2.schema.json", f"locator_audit[{index}]"
        )
        locator_entries.append((document, artifact, path))
    for index, record in enumerate(inputs["missing_access_audits"]):
        path, document, artifact = core.resolve_input(
            config_path, record, f"missing_access_audit[{index}]"
        )
        core.validate_schema_document(
            document,
            "missing-access-audit.schema.json",
            f"missing_access_audit[{index}]",
        )
        missing_entries.append((document, artifact, path))
    locator_entries.sort(key=lambda item: str(item[0].get("chunk_id", "")))
    missing_entries.sort(key=lambda item: str(item[0].get("chunk_id", "")))
    artifacts: list[dict[str, Any]] = [policy_artifact]
    paths: list[Path] = [policy_path]
    for prefix, entries in (
        ("locator_audit", locator_entries),
        ("missing_access_audit", missing_entries),
    ):
        for index, (_, artifact, path) in enumerate(entries):
            artifact["role"] = f"{prefix}[{index}]"
            artifacts.append(artifact)
            paths.append(path)
    artifacts.append(structure_artifact)
    paths.append(structure_path)
    chunk_manifest = None
    if "chunk_manifest" in inputs:
        chunk_path, chunk_manifest, chunk_artifact = core.resolve_input(
            config_path, inputs["chunk_manifest"], "chunk_manifest"
        )
        core.validate_schema_document(
            chunk_manifest, "chunk-manifest.schema.json", "chunk_manifest"
        )
        core.require(
            chunk_manifest.get("chunk_manifest_sha256")
            == core.canonical_hash(chunk_manifest, "chunk_manifest_sha256"),
            "chunk_manifest_self_hash_mismatch",
            "The canonical chunk manifest self-hash does not reconstruct.",
        )
        artifacts.append(chunk_artifact)
        paths.append(chunk_path)
    core.require(
        len(paths) == len(set(paths)),
        "duplicate_input_artifact",
        "Each calculation input path may select only one artifact.",
    )
    return {
        "config": config,
        "policy": policy_document,
        "locator_documents": [item[0] for item in locator_entries],
        "missing_documents": [item[0] for item in missing_entries],
        "structure": structure_document,
        "chunk_manifest": chunk_manifest,
        "locator_input_entries": locator_entries,
        "missing_input_entries": missing_entries,
        "input_artifacts": artifacts,
        "input_paths": paths,
        "config_path": config_path,
    }


def preflight_loaded(
    loaded: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    ledgers, missing = core.preflight_loaded(loaded)
    if ledgers is None:
        return None, missing
    missing = [
        *missing,
        *locator_state_requirements(
            ledgers,
            loaded["config"]["audit_mode"],
        ),
    ]
    return (ledgers if not missing else None), missing


def utility_assignments(
    ledgers: dict[str, Any],
) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    for locator in sorted(ledgers["locators"], key=lambda item: item["locator_id"]):
        try:
            assignment = assign_locator_utility(locator, ledgers["defects"])
        except ValueError as exc:
            raise core.CalculationError(
                "inconsistent_locator_utility_state",
                f"Locator {locator.get('locator_id')} cannot receive a V8 diagnostic and rating assignment.",
                _mapping_failure(locator, str(exc).split(";")),
            ) from exc
        assignments.append(assignment.as_dict())
    assignments.extend(
        not_measured_assignment(locator_id)
        for locator_id in sorted(ledgers["locator_not_measured"])
    )
    return sorted(assignments, key=lambda item: item["locator_id"])


def _complete_counts(values: Iterable[str], keys: Sequence[str]) -> dict[str, int]:
    counts = Counter(values)
    return {key: counts.get(key, 0) for key in keys}


def _uncertainty_triple(
    numerator: Decimal,
    assessed: int,
    unknown: int,
) -> dict[str, str]:
    denominator = assessed + unknown
    central = numerator / Decimal(assessed) if assessed else ZERO
    lower = numerator / Decimal(denominator) if denominator else ZERO
    upper = (numerator + Decimal(unknown)) / Decimal(denominator) if denominator else ZERO
    return {
        "lower": core.decimal_text(lower),
        "central": core.decimal_text(central),
        "upper": core.decimal_text(upper),
    }


def calculate_reliability(
    ledgers: dict[str, Any],
    audit_mode: str,
) -> dict[str, Any]:
    assignments = utility_assignments(ledgers)
    by_id = {item["locator_id"]: item for item in assignments}
    measured_locators = [
        item for item in ledgers["locators"] if item.get("judgment") in {"supported", "partially_supported", "unsupported"}
    ]
    uninspectable_locators = [
        item for item in ledgers["locators"] if item.get("judgment") == "uninspectable"
    ]
    locator_not_measured = ledgers["locator_not_measured"]
    keep_denom = core.component_denominators(
        "keep_precision",
        ledgers["locator_original"],
        ledgers["locator_original"],
        len(measured_locators),
        len(uninspectable_locators),
        len(locator_not_measured),
        {},
    )

    measured_treatments = [
        item for item in ledgers["treatments"] if item.get("status") in {"found", "missed"}
    ]
    uninspectable_treatments = [
        item for item in ledgers["treatments"] if item.get("status") == "uninspectable"
    ]
    explicit_treatment_not_measured_records = [
        item for item in ledgers["treatments"] if item.get("status") is None
    ]
    explicit_treatment_not_measured = [
        item["treatment_id"] for item in explicit_treatment_not_measured_records
    ]
    treatment_not_measured = ledgers["treatment_not_measured"] + explicit_treatment_not_measured
    recall_denom = core.component_denominators(
        "expected_treatment_recall",
        ledgers["treatment_original"],
        ledgers["treatment_original"],
        len(measured_treatments),
        len(uninspectable_treatments),
        len(treatment_not_measured),
        {},
    )

    assessed_assignments = [by_id[item["locator_id"]] for item in measured_locators]
    diagnostic_numerator = sum(
        (core.decimal_value(item["diagnostic_credit"]) for item in assessed_assignments), ZERO
    )
    treatment_numerator = sum(
        (core.decimal_value(item["treatment_score"]) for item in assessed_assignments), ZERO
    )
    fit_numerator = sum(
        (core.decimal_value(item["fit_score"]) for item in assessed_assignments), ZERO
    )
    supported = sum(item["judgment"] == "supported" for item in measured_locators)
    found = sum(item["status"] == "found" for item in measured_treatments)
    assessable = len(measured_locators)
    mean_diagnostic = diagnostic_numerator / Decimal(assessable) if assessable else ZERO
    mean_treatment = treatment_numerator / Decimal(assessable) if assessable else ZERO
    mean_fit = fit_numerator / Decimal(assessable) if assessable else ZERO
    keep_precision = core.rate(supported, assessable)
    recall = core.rate(found, len(measured_treatments))

    unknown_loc = len(uninspectable_locators) + len(locator_not_measured)
    unknown_treat = len(uninspectable_treatments) + len(treatment_not_measured)
    locator_bound_denominator = assessable + unknown_loc
    keep_lower = core.rate(supported, locator_bound_denominator)
    keep_upper = core.rate(supported + unknown_loc, locator_bound_denominator)
    recall_lower = core.rate(found, len(measured_treatments) + unknown_treat)
    recall_upper = core.rate(found + unknown_treat, len(measured_treatments) + unknown_treat)

    expected_treatments = ledgers["treatment_original"]
    no_locator_assignments = ledgers["locator_original"] == 0
    attempt = ledgers["context"]["candidate_attempt"]["status"]
    if expected_treatments > 0 and no_locator_assignments:
        central_base = lower_base = upper_base = ZERO
        core.mark_defined_zero(keep_denom, "expected_treatments_but_no_locator_assignments")
    else:
        central_base = FIVE * core.f1(keep_precision, recall)
        lower_base = FIVE * core.f1(keep_lower, recall_lower)
        upper_base = FIVE * core.f1(keep_upper, recall_upper)
    if attempt in {"empty", "structurally_incomplete", "unparseable"}:
        central_base = lower_base = upper_base = ZERO
        for denominator in (keep_denom, recall_denom):
            core.mark_defined_zero(denominator, f"candidate_attempt:{attempt}", non_attempt=True)

    high_measured = [
        item for item in measured_treatments if item.get("locator_class") in {"principal", "synthesis_or_conclusion"}
    ]
    high_unknown = [
        item for item in uninspectable_treatments if item.get("locator_class") in {"principal", "synthesis_or_conclusion"}
    ]
    high_not_measured_ids = [
        item["treatment_id"]
        for item in explicit_treatment_not_measured_records
        if item.get("locator_class") in {"principal", "synthesis_or_conclusion"}
    ] + ledgers["treatment_not_measured"]
    high_found = sum(item["status"] == "found" for item in high_measured)
    critical = core.defect_subset(
        ledgers,
        "page_reference_reliability",
        severities={"critical"},
        kinds={"fabricated_locator", "nonexistent_locator", "out_of_scope_locator"},
    )
    # Preserve the exact cap trigger; V8 changes precision credit, not cap evidence.
    pattern = [
        item
        for item in measured_locators
        if item.get("judgment") == "unsupported"
        and set(item.get("error_codes", [])) & core.RELIABILITY_CODES
    ]
    pattern_units = {item.get("_source_unit_id") for item in pattern if item.get("_source_unit_id")}
    unknown_locator_units = {
        item.get("_source_unit_id") for item in uninspectable_locators if item.get("_source_unit_id")
    } | {item for item in ledgers["locator_not_measured_units"] if item}
    unit_denominator = max(1, len(ledgers["source_units"]))

    def caps(
        high_found_value: int,
        high_total: int,
        pattern_count: int,
        locator_total: int,
        units: int,
        high_miss_evidence: Sequence[str],
        pattern_evidence: Sequence[str],
    ) -> list[dict[str, Any]]:
        high_max, high_triggered, high_band = core.high_value_cap(high_found_value, high_total)
        pattern_max, pattern_triggered, pattern_band = core.reliability_pattern_cap(
            pattern_count, locator_total, units, unit_denominator
        )
        return [
            core.cap_record(
                "reliability.critical_locator",
                Decimal(2),
                bool(critical),
                {"severity": "critical", "defect_kinds": ["fabricated_locator", "nonexistent_locator", "out_of_scope_locator"]},
                {"defect_count": len(critical)},
                [item["defect_id"] for item in critical],
            ),
            core.cap_record(
                "reliability.high_value_treatment_recall",
                high_max,
                high_triggered,
                {"table": "pooled_principal_and_synthesis_recall_v1", "band": high_band},
                {"found": high_found_value, "expected": high_total, "rate": core.decimal_text(core.rate(high_found_value, high_total))},
                high_miss_evidence,
            ),
            core.cap_record(
                "reliability.distributed_unsupported_pattern",
                pattern_max,
                pattern_triggered,
                {"minimum_source_unit_rate": "0.25", "rate_table": "reliability_owned_unsupported_v1", "band": pattern_band},
                {
                    "unsupported_count": pattern_count,
                    "assessable_locator_denominator": locator_total,
                    "rate": core.decimal_text(core.rate(pattern_count, locator_total)),
                    "affected_source_units": units,
                    "source_unit_denominator": unit_denominator,
                    "source_unit_rate": core.decimal_text(core.rate(units, unit_denominator)),
                },
                pattern_evidence,
            ),
        ]

    known_high_misses = [item["treatment_id"] for item in high_measured if item["status"] == "missed"]
    known_pattern_ids = [item["locator_id"] for item in pattern]
    central_caps = caps(high_found, len(high_measured), len(pattern), assessable, len(pattern_units), known_high_misses, known_pattern_ids)
    lower_caps = caps(
        high_found,
        len(high_measured) + len(high_unknown) + len(high_not_measured_ids),
        len(pattern) + unknown_loc,
        assessable + unknown_loc,
        len(pattern_units | unknown_locator_units),
        known_high_misses + [item["treatment_id"] for item in high_unknown] + high_not_measured_ids,
        known_pattern_ids + [item["locator_id"] for item in uninspectable_locators] + locator_not_measured,
    )
    upper_caps = caps(
        high_found + len(high_unknown) + len(high_not_measured_ids),
        len(high_measured) + len(high_unknown) + len(high_not_measured_ids),
        len(pattern),
        assessable + unknown_loc,
        len(pattern_units),
        known_high_misses,
        known_pattern_ids,
    )

    result = core.finish_dimension(
        "page_reference_reliability",
        [keep_denom, recall_denom],
        central_base,
        lower_base,
        upper_base,
        central_caps,
        lower_caps,
        upper_caps,
        audit_mode,
    )
    result["formula_id"] = f"{CALCULATION_PROFILE}:page_reference_reliability"
    result["input_roles"] = ["locator_audit", "missing_access_audit", "structure_audit"]

    treatment_tiers = ("substantive", "mixed", "weak_presence", "absent", "invalid_destination", "uninspectable", "not_measured")
    fit_tiers = ("exact_fit", "material_partial_fit", "material_mismatch", "severe_mismatch", "no_fit", "uninspectable", "not_measured")
    diagnostic_values = ("1", "0.7", "0.35", "0.25", "0.15", "0", "uninspectable", "not_measured")
    rating_values = ("1", "0", "uninspectable", "not_measured")

    def credit_count_key(item: dict[str, Any], field: str) -> str:
        if item["disposition"] == "bounded":
            return "uninspectable"
        if item["disposition"] == "not_measured":
            return "not_measured"
        return str(item[field])

    treatment_counts = _complete_counts((item["treatment_category"] for item in assignments), treatment_tiers)
    fit_counts = _complete_counts((item["fit_category"] for item in assignments), fit_tiers)
    diagnostic_counts = _complete_counts(
        (credit_count_key(item, "diagnostic_credit") for item in assignments),
        diagnostic_values,
    )
    rating_counts = _complete_counts(
        (credit_count_key(item, "rating_credit") for item in assignments),
        rating_values,
    )
    result["raw_status_counts"] = {
        "locator_support": dict(Counter(item["judgment"] for item in ledgers["locators"])),
        "locator_treatment_class": dict(Counter(item.get("treatment_class") for item in ledgers["locators"])),
        "treatment_tier": treatment_counts,
        "fit_tier": fit_counts,
        "diagnostic_credit": diagnostic_counts,
        "rating_credit": rating_counts,
        "treatment_recall": dict(Counter(item.get("status") or "not_measured" for item in ledgers["treatments"])),
        "not_measured_locators": len(locator_not_measured),
        "not_measured_treatments": len(treatment_not_measured),
    }
    result["credit_mappings"] = {
        "page_treatment": {key: core.decimal_text(value) for key, value in TREATMENT_SCORES.items()} | {"uninspectable": "neutral_uncertainty_bounds"},
        "complete_path_fit": {key: core.decimal_text(value) for key, value in FIT_SCORES.items()} | {"uninspectable": "neutral_uncertainty_bounds"},
        "diagnostic_combination": {"rule": "minimum", "formula": "D_j=min(T_j,F_j)"},
        "rating_credit": {"supported": "1", "partially_supported": "0", "unsupported": "0"},
        "treatment_recall": {"found": "1", "missed": "0"},
    }
    f1_denominator = keep_precision + recall
    result["components"] = [
        {
            "component_id": "keep_precision",
            "raw_numerator": core.decimal_text(Decimal(supported)),
            "raw_denominator": core.decimal_text(Decimal(assessable)),
            "normalized_value": core.decimal_text(keep_precision),
            "weight": "harmonic_mean",
            "effective_weight": "harmonic_mean",
            "weight_renormalized": False,
        },
        {
            "component_id": "page_treatment_axis_diagnostic",
            "raw_numerator": core.decimal_text(treatment_numerator),
            "raw_denominator": core.decimal_text(Decimal(assessable)),
            "normalized_value": core.decimal_text(mean_treatment),
            "weight": "reported_diagnostic_only",
            "effective_weight": "not_used_independently_in_dimension_arithmetic",
            "weight_renormalized": False,
        },
        {
            "component_id": "complete_path_fit_axis_diagnostic",
            "raw_numerator": core.decimal_text(fit_numerator),
            "raw_denominator": core.decimal_text(Decimal(assessable)),
            "normalized_value": core.decimal_text(mean_fit),
            "weight": "reported_diagnostic_only",
            "effective_weight": "not_used_independently_in_dimension_arithmetic",
            "weight_renormalized": False,
        },
        {
            "component_id": "diagnostic_locator_credit_mean",
            "raw_numerator": core.decimal_text(diagnostic_numerator),
            "raw_denominator": core.decimal_text(Decimal(assessable)),
            "normalized_value": core.decimal_text(mean_diagnostic),
            "weight": "reported_diagnostic_only",
            "effective_weight": "not_used_in_dimension_arithmetic",
            "weight_renormalized": False,
        },
        {
            "component_id": "expected_treatment_recall",
            "raw_numerator": core.decimal_text(Decimal(found)),
            "raw_denominator": core.decimal_text(Decimal(len(measured_treatments))),
            "normalized_value": core.decimal_text(recall),
            "weight": "harmonic_mean",
            "effective_weight": "harmonic_mean",
            "weight_renormalized": False,
        },
        {
            "component_id": "reliability_f1",
            "raw_numerator": core.decimal_text(TWO * keep_precision * recall),
            "raw_denominator": core.decimal_text(f1_denominator),
            "normalized_value": core.decimal_text(core.f1(keep_precision, recall)),
            "weight": "base_rating_times_5",
            "effective_weight": "base_rating_times_5",
            "weight_renormalized": False,
        },
        {
            "component_id": "high_value_treatment_recall_safeguard",
            "raw_numerator": core.decimal_text(Decimal(high_found)),
            "raw_denominator": core.decimal_text(Decimal(len(high_measured))),
            "normalized_value": core.decimal_text(core.rate(high_found, len(high_measured))),
            "weight": "cap_only",
            "effective_weight": "cap_only",
            "weight_renormalized": False,
        },
    ]
    result["reliability_provenance"] = {
        "model": "binary_keep_precision_with_two_axis_diagnostics_v1",
        "original_locator_denominator": ledgers["locator_original"],
        "assessable_locator_denominator": assessable,
        "uninspectable_locator_count": len(uninspectable_locators),
        "not_measured_locator_count": len(locator_not_measured),
        "counts_by_judgment": _complete_counts(
            (item.get("judgment") for item in ledgers["locators"]),
            ("supported", "partially_supported", "unsupported", "uninspectable"),
        ) | {"not_measured": len(locator_not_measured)},
        "counts_by_treatment_class": dict(sorted(Counter(item.get("treatment_class") for item in ledgers["locators"]).items())) | ({"not_measured": len(locator_not_measured)} if locator_not_measured else {}),
        "counts_by_treatment_tier": treatment_counts,
        "counts_by_fit_tier": fit_counts,
        "counts_by_diagnostic_credit_value": diagnostic_counts,
        "counts_by_rating_credit_value": rating_counts,
        "locator_utility_assignments": assignments,
        "mapping_rejections": [],
        "treatment_score_numerator": core.decimal_text(treatment_numerator),
        "treatment_score_denominator": assessable,
        "mean_treatment_score": core.decimal_text(mean_treatment),
        "fit_score_numerator": core.decimal_text(fit_numerator),
        "fit_score_denominator": assessable,
        "mean_fit_score": core.decimal_text(mean_fit),
        "diagnostic_credit_numerator": core.decimal_text(diagnostic_numerator),
        "diagnostic_credit_denominator": assessable,
        "mean_diagnostic_credit": core.decimal_text(mean_diagnostic),
        "keep_precision_numerator": supported,
        "keep_precision_denominator": assessable,
        "keep_precision": core.decimal_text(keep_precision),
        "treatment_recall_numerator": found,
        "treatment_recall_denominator": len(measured_treatments),
        "treatment_recall": core.decimal_text(recall),
        "reliability_f1": core.decimal_text(core.f1(keep_precision, recall)),
        "treatment_score_uncertainty": _uncertainty_triple(treatment_numerator, assessable, unknown_loc),
        "fit_score_uncertainty": _uncertainty_triple(fit_numerator, assessable, unknown_loc),
        "diagnostic_credit_uncertainty": _uncertainty_triple(diagnostic_numerator, assessable, unknown_loc),
        "keep_precision_uncertainty": {"lower": core.decimal_text(keep_lower), "central": core.decimal_text(keep_precision), "upper": core.decimal_text(keep_upper)},
        "treatment_recall_uncertainty": {"lower": core.decimal_text(recall_lower), "central": core.decimal_text(recall), "upper": core.decimal_text(recall_upper)},
        "rating_credit_source": "locator_utility_assignments[].rating_credit",
        "diagnostic_grade_formula": "100 * diagnostic_credit",
        "diagnostic_grades_used_in_dimension_arithmetic": False,
        "pre_cap_rating": result["pre_cap_rating"],
        "cap_evaluations": result["cap_evaluations"],
        "applied_cap": result["applied_cap"],
        "uncertainty_lower": result["missing_data_bounds"]["lower"],
        "uncertainty_upper": result["missing_data_bounds"]["upper"],
        "rounding": result["rounding"],
        "final_rating": result["final_rating"],
        "dimension_weight": result["dimension_weight"],
        "awarded_points": result["awarded_points"],
    }
    return result


def calculate_loaded(
    loaded: dict[str, Any],
) -> dict[str, Any]:
    ledgers, missing = preflight_loaded(loaded)
    core.require(
        ledgers is not None and not missing,
        "v8_inputs_insufficient",
        "The frozen ledgers do not satisfy the V8 diagnostic-and-rating calculation contract.",
        missing,
    )
    audit_mode = loaded["config"]["audit_mode"]
    fit_preflight = locator_fit_preflight(ledgers, audit_mode)
    core.require(
        not fit_preflight["invalid_or_contradictory_state"],
        "v8_inputs_insufficient",
        "The frozen ledgers contain invalid or contradictory V8 locator states.",
        fit_preflight["invalid_or_contradictory_state"],
    )
    calculation_artifacts = deepcopy(loaded["input_artifacts"])
    dimensions = [
        core.calculate_coverage(ledgers, audit_mode),
        core.calculate_selectivity(ledgers, audit_mode),
        core.calculate_concept(ledgers, audit_mode),
        calculate_reliability(ledgers, audit_mode),
        core.calculate_findability(ledgers, audit_mode),
        core.calculate_mechanics(ledgers, audit_mode),
    ]
    for dimension in dimensions:
        dimension["formula_id"] = f"{CALCULATION_PROFILE}:{dimension['dimension_id']}"
        selected: list[dict[str, Any]] = []
        for artifact in calculation_artifacts:
            role = artifact["role"]
            include = role == "policy" or any(
                role == "chunk_manifest"
                or (requested == "locator_audit" and role.startswith("locator_audit["))
                or (requested == "missing_access_audit" and role.startswith("missing_access_audit["))
                or (requested == "structure_audit" and role == "structure_audit")
                for requested in dimension["input_roles"]
            )
            if include and artifact not in selected:
                selected.append(artifact)
        core.require(bool(selected), "dimension_input_binding_failed", f"{dimension['dimension_id']} did not resolve frozen inputs.")
        dimension["input_artifacts"] = selected

    all_scored = all(item["status"] == "scored" for item in dimensions)
    total = (
        core.round_points(sum((core.decimal_value(item["awarded_points"]) for item in dimensions), ZERO))
        if all_scored
        else None
    )
    result = {
        "schema_version": CALCULATION_SCHEMA,
        "calculation_id": f"CALC-{core.canonical_hash({'evaluation_id': loaded['config']['evaluation_id'], 'audit_mode': audit_mode, 'rubric_version': RUBRIC_VERSION, 'calculation_profile': CALCULATION_PROFILE, 'inputs': calculation_artifacts})[:12].upper()}",
        "evaluation_id": loaded["config"]["evaluation_id"],
        "rubric_version": RUBRIC_VERSION,
        "calculation_profile": CALCULATION_PROFILE,
        "audit_mode": audit_mode,
        "status": "scored" if all_scored else "not_scored_insufficient_evidence",
        "evidence_identity": {field: ledgers["identity"][field] for field in core.CALCULATION_EVIDENCE_IDENTITY_FIELDS},
        "input_artifacts": calculation_artifacts,
        "diagnostic_item_grades": {
            "used_in_dimension_arithmetic": False,
            "policy": "separate_non_additive_display_layer_independent_of_binary_rating_credit",
            "required_policy_version": ITEM_GRADING_POLICY,
            "expected_source_subjects": {
                "count": len(ledgers["expected_subject_ids"]),
                "id_set_sha256": core.canonical_hash({"ids": ledgers["expected_subject_ids"]}),
            },
        },
        "publication_readiness_gates": {
            "used_in_score_arithmetic": False,
            "policy": "separate_claim_restrictions",
        },
        "dimensions": dimensions,
        "total_score": core.displayed_number(total, Decimal("0.01")) if total is not None else None,
        "maximum_score": 100,
        "arithmetic_check": all_scored and total == sum((core.decimal_value(item["awarded_points"]) for item in dimensions), ZERO).quantize(Decimal("0.01"), rounding=core.ROUND_HALF_UP),
    }
    architecture = loaded["structure"]["locator_architecture"]
    result["structure_audit"] = {
        "schema_version": loaded["structure"]["schema_version"],
        "candidate_denominator": deepcopy(loaded["structure"]["candidate_denominator"]),
        "full_scope_attestation": deepcopy(loaded["structure"]["full_scope_attestation"]),
        "locator_architecture": deepcopy(architecture),
        "uncertainties": deepcopy(loaded["structure"]["uncertainties"]),
    }
    result["calculation_sha256"] = core.canonical_hash(result, "calculation_sha256")
    return result


def reliability_dimension(calculation: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in calculation.get("dimensions", []) if item.get("dimension_id") == "page_reference_reliability"]
    core.require(len(matches) == 1, "v8_reliability_dimension_required", "A V8 calculation must contain exactly one Page-reference Reliability dimension.")
    return matches[0]


def command_preflight(args: argparse.Namespace) -> None:
    config_path = Path(args.input).resolve()
    try:
        raw_evaluation_id, raw_missing, raw_paths = raw_locator_state_requirements(config_path)
        if raw_missing:
            result = {
                "command": "v8-calculation-sufficiency-preflight",
                "ok": True,
                "evaluation_id": raw_evaluation_id,
                "target_rubric_version": RUBRIC_VERSION,
                "target_calculation_profile": CALCULATION_PROFILE,
                "sufficient": False,
                "missing_requirements": raw_missing,
                "aggregate_v8_score_available": False,
                "source_reopened": False,
                "prose_inference_used": False,
                "frozen_evidence_mutated": False,
            }
            if args.output:
                output_path = Path(args.output).resolve()
                core.require(not core.aliases_existing_file(output_path, {config_path, *raw_paths}), "output_aliases_frozen_input", "Preflight output must not overwrite frozen evidence.")
                write_json(output_path, result)
                result["artifact_written"] = str(output_path)
            core.emit(result)
        loaded = load_v8_inputs(config_path)
        ledgers, base_missing = core.preflight_loaded(loaded)
        fit_report = (
            locator_fit_preflight(ledgers, loaded["config"]["audit_mode"])
            if ledgers is not None
            else {
                "schema_version": "subject-index-v8-locator-fit-preflight-v1",
                "validated_complete_path_fit": [],
                "invalid_or_contradictory_state": [],
                "group_counts": {
                    "validated_complete_path_fit": 0,
                    "invalid_or_contradictory_state": 0,
                },
                "aggregate_v8_score_available": False,
                "prose_inference_used": False,
            }
        )
        missing = [*base_missing, *fit_report["invalid_or_contradictory_state"]]
        public_fit_report = public_locator_fit_preflight(fit_report)
        core.validate_schema_document(
            public_fit_report,
            "v8-locator-fit-preflight.schema.json",
            "V8 locator-fit preflight",
        )
        result = {
            "command": "v8-calculation-sufficiency-preflight",
            "ok": True,
            "evaluation_id": loaded["config"]["evaluation_id"],
            "target_rubric_version": RUBRIC_VERSION,
            "target_calculation_profile": CALCULATION_PROFILE,
            "sufficient": not missing,
            "missing_requirements": missing,
            "locator_fit_preflight": public_fit_report,
            "aggregate_v8_score_available": False,
            "required_locator_fields": ["judgment", "treatment_class", "complete_path_fit", "source_scope_status", "error_codes", "severity", "applicable_structured_defects"],
            "source_reopened": False,
            "prose_inference_used": False,
            "frozen_evidence_mutated": False,
        }
        if args.output:
            output_path = Path(args.output).resolve()
            core.require(not core.aliases_existing_file(output_path, {loaded["config_path"], *loaded["input_paths"]}), "output_aliases_frozen_input", "Preflight output must not overwrite frozen evidence.")
            write_json(output_path, result)
            result["artifact_written"] = str(output_path)
        core.emit(result)
    except (OSError, core.CalculationError) as exc:
        error = {"code": exc.code, "message": exc.message, "details": exc.details} if isinstance(exc, core.CalculationError) else {"code": "file_error", "message": str(exc)}
        core.emit({"command": "v8-calculation-sufficiency-preflight", "ok": False, "error": error}, 1)


def command_calculate(args: argparse.Namespace) -> None:
    try:
        loaded = load_v8_inputs(Path(args.input).resolve())
        result = calculate_loaded(loaded)
        core.validate_schema_document(result, "dimension-calculations-v5.schema.json", "Generated V8 dimension calculations")
        if args.output:
            output_path = Path(args.output).resolve()
            core.require(not core.aliases_existing_file(output_path, {loaded["config_path"], *loaded["input_paths"]}), "output_aliases_frozen_input", "Calculation output must not overwrite frozen evidence.")
            write_json(output_path, result)
            response = {"command": "calculate-v8-dimensions", "ok": True, "evaluation_id": result["evaluation_id"], "status": result["status"], "total_score": result["total_score"], "calculation_sha256": result["calculation_sha256"], "artifact_written": str(output_path)}
        else:
            response = {"command": "calculate-v8-dimensions", "ok": True, **result}
        core.emit(response)
    except (OSError, core.CalculationError) as exc:
        error = {"code": exc.code, "message": exc.message, "details": exc.details} if isinstance(exc, core.CalculationError) else {"code": "file_error", "message": str(exc)}
        core.emit({"command": "calculate-v8-dimensions", "ok": False, "error": error}, 1)


def _json_bytes(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(core.json_output_value(document), indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _transition_state(state_path: Path, stage: str) -> tuple[dict[str, Any], list[str]]:
    state = load_state(state_path)
    errors, warnings = validate_state(state, state_path=state_path)
    core.require(not errors, "canonical_state_invalid", "Canonical evaluation state is invalid.", errors)
    core.require(state["stages"][stage]["status"] != "completed", "stage_already_completed", f"{stage} is already completed.")
    stage_index = STAGES.index(stage)
    unmet = [name for name in STAGES[:stage_index] if state["stages"][name]["status"] != "completed"]
    core.require(not unmet, "stage_dependencies_incomplete", f"Complete these stages before {stage}: {', '.join(unmet)}", unmet)
    active = [name for name, value in state["stages"].items() if value.get("status") == "in_progress" and name != stage]
    core.require(not active, "another_stage_in_progress", f"Another stage is in progress: {', '.join(active)}", active)
    return state, warnings


def _registered_documents(
    state: Mapping[str, Any],
    state_path: Path,
    *,
    stage: str,
    schema_version: str,
    schema_name: str,
    many: bool = False,
) -> list[tuple[dict[str, Any], dict[str, Any], Path]]:
    records = [
        item for item in state.get("artifacts", [])
        if item.get("stage") == stage and item.get("schema_version") == schema_version
    ]
    core.require(bool(records), "registered_artifact_missing", f"No registered {schema_version} artifact exists for {stage}.")
    core.require(many or len(records) == 1, "duplicate_registered_artifact", f"Expected exactly one registered {schema_version} artifact for {stage}.", [item["path"] for item in records])
    result = []
    for record in sorted(records, key=lambda item: item["path"]):
        path = resolve_artifact_path(state_path, record["path"]).resolve()
        core.require(path.is_file(), "registered_artifact_missing", f"Registered artifact is unavailable: {record['path']}")
        actual = core.sha256_file(path)
        core.require(actual == record["sha256"], "registered_artifact_hash_mismatch", f"Registered artifact bytes changed: {record['path']}", {"expected_sha256": record["sha256"], "actual_sha256": actual})
        document = core.load_json(path, schema_version)
        core.validate_schema_document(document, schema_name, schema_version)
        result.append((document, deepcopy(record), path))
    return result


def _state_output_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise core.CalculationError("output_outside_evaluation_directory", "Generated artifacts must remain inside the evaluation directory.", str(path)) from exc
    return path


def _artifact_record(
    root: Path,
    path: Path,
    payload: bytes,
    *,
    stage: str,
    artifact_type: str,
    schema_version: str,
    stamp: str,
    visibility: str = "private",
    input_sha256: Iterable[str] = (),
) -> dict[str, Any]:
    relative = portable_relative_path(path, root)
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "artifact_id": artifact_id(relative, digest),
        "stage": stage,
        "artifact_type": artifact_type,
        "path": relative,
        "sha256": digest,
        "media_type": "application/json",
        "schema_version": schema_version,
        "visibility": visibility,
        "retention": "required",
        "frozen": True,
        "recorded_at": stamp,
        **({"input_sha256": sorted(set(input_sha256))} if input_sha256 else {}),
    }


def _add_records_and_complete(
    state: dict[str, Any],
    state_path: Path,
    stage: str,
    records: Sequence[dict[str, Any]],
    note: str,
) -> dict[str, Any]:
    updated = deepcopy(state)
    new_paths = {record["path"] for record in records}
    collisions = [item["path"] for item in updated["artifacts"] if item.get("path") in new_paths]
    core.require(not collisions, "registered_output_collision", "Generated output would replace an already registered artifact.", collisions)
    updated["artifacts"].extend(records)
    updated["artifacts"].sort(key=lambda item: item["path"])
    stamp = records[0]["recorded_at"]
    updated["stages"][stage] = {"status": "completed", "updated_at": stamp, "notes": [note]}
    updated["updated_at"] = stamp
    errors, _ = validate_state(updated, state_path=state_path, check_files=False)
    core.require(not errors, "canonical_state_invalid", f"Completing {stage} would leave invalid canonical state.", errors)
    return updated


def _completeness(records: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    identities = [str(item[field]) for item in records]
    core.require(len(identities) == len(set(identities)), "duplicate_item_identity", f"Duplicate {field} in item-assessment denominator.")
    return {
        "expected": len(identities),
        "assessed": len(identities),
        "unique": True,
        "complete": True,
        "id_set_sha256": core.canonical_hash({"ids": sorted(identities)}),
    }


def _assessed_item(
    title: str,
    grade_scope: str,
    score: float | None,
    *,
    confidence: str | None = None,
    evidence_ids: Iterable[str] = (),
    summary: str = "",
    navigation: Mapping[str, Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    grade = item_projection.grade(score)
    evidence = sorted(set(evidence_ids))
    return {
        **fields,
        "grade": grade,
        "grade_scope": grade_scope,
        "confidence": confidence,
        "evidence_ids": evidence,
        "summary": summary,
        "popover": {
            "title": title,
            "summary": summary,
            "grade": deepcopy(grade),
            "grade_scope": grade_scope,
            "confidence": confidence,
            "factors": [],
            "evidence_ids": evidence,
            "navigation": dict(navigation or {}),
        },
    }


def _current_item_assessments(
    inventory: Mapping[str, Any],
    inventory_record: Mapping[str, Any],
    calculation: Mapping[str, Any],
    structure: Mapping[str, Any],
    locator_documents: Sequence[Mapping[str, Any]],
    missing_documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    locator_by_id = {item["locator_id"]: item for document in locator_documents for item in document["judgments"]}
    subject_by_id = {item["subject_id"]: item for document in missing_documents for item in document["subject_judgments"]}
    nodes, references, _, _ = materialize_structure_records(structure)
    node_by_id = {item["node_id"]: item for item in nodes}
    reference_by_id = {item["reference_id"]: item for item in references}
    status_score = {"passes": 100.0, "cosmetic_issues": 95.0, "minor_issues": 85.0, "major_issues": 55.0, "fails": 0.0, "supported": 100.0, "partially_supported": 50.0, "unsupported": 0.0}
    coverage_score = {"complete": 100.0, "partial": 50.0, "missing": 0.0}

    locators = []
    for item in inventory["locators"]:
        judgment = locator_by_id[item["locator_id"]]
        locators.append(_assessed_item(
            f"Locator {item.get('source_page_label')}",
            "one_complete_heading_path_and_source_page_assignment",
            None,
            confidence=judgment["confidence"],
            evidence_ids=judgment["evidence_ids"],
            summary=judgment["evidence_summary"],
            navigation={"path_id": item["path_id"], "node_ids": item["node_ids"]},
            **item,
            judgment=judgment["judgment"],
        ))

    node_assessments = []
    for item in inventory["heading_nodes"]:
        judgment = node_by_id[item["node_id"]]
        component_results = []
        scores = []
        for dimension, component in judgment["component_judgments"].items():
            score = status_score.get(component["status"])
            scores.append(score)
            component_results.append({"dimension_id": dimension, "status": component["status"], "score": score, "weight": 1, "summary": component["summary"], "evidence_ids": component["evidence_ids"]})
        measured = [value for value in scores if value is not None]
        node_assessments.append(_assessed_item(
            " — ".join(item["heading_path"]),
            "heading_wording_and_structural_role",
            sum(measured) / len(measured) if measured else None,
            confidence=judgment["confidence"],
            evidence_ids=judgment["evidence_ids"],
            summary=judgment["summary"],
            navigation={"node_id": item["node_id"], "path_ids": item["path_ids"]},
            **item,
            component_results=component_results,
        ))

    reference_assessments = []
    for item in inventory["cross_references"]:
        judgment = reference_by_id[item["reference_id"]]
        reference_assessments.append(_assessed_item(
            f"{item['reference_type']} {item['target_display']}",
            "one_cross_reference_relationship",
            status_score.get(judgment["judgment"]),
            confidence=judgment["confidence"],
            evidence_ids=judgment["evidence_ids"],
            summary=judgment["summary"],
            navigation={"source_path_id": item["source_path_id"], "target_path_id": item["target_path_id"]},
            **item,
            judgment=judgment["judgment"],
        ))

    subject_assessments = []
    for subject_id in sorted(subject_by_id):
        judgment = subject_by_id[subject_id]
        subject_assessments.append(_assessed_item(
            f"Source subject {subject_id}",
            "access_to_one_frozen_source_subject",
            coverage_score.get(judgment["coverage"]),
            confidence=judgment["confidence"],
            evidence_ids=judgment["evidence_ids"],
            summary=f"Frozen benchmark subject access is {judgment['coverage']}.",
            navigation={"matched_path_ids": judgment["matched_path_ids"]},
            subject_id=subject_id,
            coverage=judgment["coverage"],
            matched_path_ids=judgment["matched_path_ids"],
        ))

    paths = [
        _assessed_item(
            " — ".join(item["heading_path"]),
            "complete_heading_path_as_delivered",
            None,
            summary="Path-level display is descriptive; canonical grades remain at locator and audited item level.",
            navigation={"path_id": item["path_id"], "locator_ids": item["locator_ids"]},
            **item,
            component_results=[],
        )
        for item in inventory["paths"]
    ]
    base = {
        "schema_version": "subject-index-item-assessments-v3",
        "grading_policy": "subject-index-item-grading-v2",
        "evaluation_id": calculation["evaluation_id"],
        "candidate_id": inventory["candidate_id"],
        "candidate_sha256": inventory["candidate_sha256"],
        "item_inventory_sha256": inventory_record["sha256"],
        "item_inventory_artifact": {"schema_version": inventory["schema_version"], "artifact_path": inventory_record["path"], "sha256": inventory_record["sha256"]},
        "evidence_identity": deepcopy(calculation["evidence_identity"]),
        "assessment_completeness": {
            "locators": _completeness(locators, "locator_id"),
            "paths": _completeness(paths, "path_id"),
            "heading_nodes": _completeness(node_assessments, "node_id"),
            "cross_references": _completeness(reference_assessments, "reference_id"),
            "source_subjects": _completeness(subject_assessments, "subject_id"),
        },
        "audit_mode": calculation["audit_mode"],
        "scope_complete": calculation["audit_mode"] == "full",
        "grade_disclosure": "Diagnostic item projections do not replace the six-dimension calculation.",
        "locator_grading_provenance": {},
        "color_legend": [
            {"band": "excellent", "minimum_score": 90, "color_token": "grade_excellent"},
            {"band": "strong", "minimum_score": 80, "color_token": "grade_strong"},
            {"band": "mixed", "minimum_score": 70, "color_token": "grade_mixed"},
            {"band": "weak", "minimum_score": 60, "color_token": "grade_weak"},
            {"band": "poor", "minimum_score": 0, "color_token": "grade_poor"},
            {"band": "not_measured", "minimum_score": None, "color_token": "grade_neutral"},
        ],
        "locator_assessments": locators,
        "path_assessments": paths,
        "heading_node_assessments": node_assessments,
        "cross_reference_assessments": reference_assessments,
        "source_subject_assessments": subject_assessments,
        "summary": {},
    }
    result = item_grades.build_v8_assessments(base, calculation, structure, locator_documents=list(locator_documents))
    core.validate_schema_document(result, "item-assessments-v6.schema.json", "Generated V8 item assessments")
    return result


def _scorecard(calculation: Mapping[str, Any], *, web: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "dimension_id": item["dimension_id"],
            "weight": item["dimension_weight"],
            "rating": item["final_rating"],
            ("awarded_points" if web else "points"): item["awarded_points"],
            "formula_id": item["formula_id"],
        }
        for item in calculation["dimensions"]
    ]


def _calculation_reference(record: Mapping[str, Any], calculation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": calculation["schema_version"],
        "artifact_path": record["path"],
        "sha256": record["sha256"],
        "calculation_sha256": calculation["calculation_sha256"],
        "rubric_version": calculation["rubric_version"],
        "calculation_profile": calculation["calculation_profile"],
    }


def _structure_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema_version": "structure-audit-v5", "artifact_path": record["path"], "sha256": record["sha256"]}


def _critical_gate_outcomes(
    policy: Mapping[str, Any], structure: Mapping[str, Any], calculation: Mapping[str, Any]
) -> list[dict[str, Any]]:
    defects = structure["defects"]
    predicates = {
        "GATE-SCOPE-LOCATOR": lambda item: item["defect_kind"] in {"fabricated_locator", "nonexistent_locator", "out_of_scope_locator"},
        "GATE-SYSTEMIC-UNSUPPORTED": lambda item: item["severity_basis"] == "systemic_nonuse" and item["dimension_owner"] == "page_reference_reliability",
        "GATE-CENTRAL-OMISSION": lambda item: item["defect_kind"] == "central_omission",
        "GATE-STANCE": lambda item: item["defect_kind"] in {"stance_reversal", "misleading_relationship"},
        "GATE-COMPOUND": lambda item: item["code"] == "CMP",
        "GATE-SEE-SUBSTITUTION": lambda item: item["defect_kind"] == "substitutive_see",
        "GATE-CROSS-REFERENCE": lambda item: item["code"] == "XRF",
        "GATE-DEPTH": lambda item: item["code"] == "HED" and item["severity"] in {"major", "critical"},
        "GATE-CLUTTER": lambda item: item["defect_kind"] == "clutter_pattern",
        "GATE-GROUNDING": lambda item: item["severity"] in {"major", "critical"} and item["dimension_owner"] in {"conceptual_stance_fidelity", "page_reference_reliability"},
        "GATE-SOURCE-SPAN": lambda item: item["defect_kind"] == "scope_failure",
        "GATE-STRUCTURE": lambda item: item["severity"] == "critical" and item["dimension_owner"] in {"findability_navigation", "mechanics_consistency"},
    }
    reliability = reliability_dimension(dict(calculation))["reliability_provenance"]
    denominator = reliability["original_locator_denominator"]
    uninspectable_rate = Decimal(reliability["uninspectable_locator_count"]) / Decimal(denominator) if denominator else ZERO
    tolerance = Decimal(str(policy["audit_design"]["uninspectable_locator_rate_tolerance"]))
    results = []
    for gate in policy["critical_gates"]:
        gate_id = gate["gate_id"]
        matching = [item["defect_id"] for item in defects if predicates.get(gate_id, lambda _: False)(item)]
        triggered = uninspectable_rate > tolerance if gate_id == "GATE-UNINSPECTABLE" else bool(matching)
        if gate_id == "GATE-STRUCTURE":
            triggered = triggered or not structure["full_scope_attestation"]["complete"]
        results.append({**deepcopy(gate), "triggered": triggered, "defect_ids": sorted(matching)})
    return results


def _projection_metadata(
    *,
    policy: Mapping[str, Any],
    calculation: Mapping[str, Any],
    calculation_record: Mapping[str, Any],
    structure: Mapping[str, Any],
    structure_record: Mapping[str, Any],
    candidate_label: str,
) -> dict[str, Any]:
    gates = _critical_gate_outcomes(policy, structure, calculation)
    limitations = [item["summary"] for item in structure["uncertainties"]]
    metadata = {
        "schema_version": "subject-index-v8-projection-metadata-v1",
        "candidate_label": candidate_label,
        "inclusion_policy": "Frozen current-V8 source scope and candidate-blind benchmark.",
        "uncertainty_policy": policy["audit_design"]["uncertainty_policy"],
        "critical_gates": gates,
        "report_id": f"{calculation['evaluation_id']}-v8",
        "headline": "Subject-index evaluation",
        "summary": "Current-V8 source-grounded evaluation from validated registered artifacts.",
        "interpretation": f"The validated V8 calculation produced {calculation['total_score']} of 100 points.",
        "defect_counts": dict(sorted(Counter(item["severity"] for item in structure["defects"]).items())),
        "strengths": deepcopy(structure["strengths"]),
        "defects": deepcopy(structure["defects"]),
        "examples": [],
        "limitations": limitations,
        "canonical_calculation": _calculation_reference(calculation_record, calculation),
        "canonical_structure_audit": _structure_reference(structure_record),
    }
    metadata["projection_metadata_sha256"] = core.canonical_hash(metadata, "projection_metadata_sha256")
    core.validate_schema_document(metadata, "v8-projection-metadata-v1.schema.json", "Generated V8 projection metadata")
    return metadata


def _evaluation_result(
    *,
    calculation: Mapping[str, Any],
    calculation_record: Mapping[str, Any],
    items: Mapping[str, Any],
    items_record: Mapping[str, Any],
    structure_record: Mapping[str, Any],
    metadata: Mapping[str, Any],
    metadata_record: Mapping[str, Any],
) -> dict[str, Any]:
    identity = calculation["evidence_identity"]
    reliability = reliability_dimension(dict(calculation))["reliability_provenance"]
    result = {
        "schema_version": "subject-index-evaluation-result-v10",
        "evaluation_id": calculation["evaluation_id"],
        "candidate": {"label": metadata["candidate_label"], "sha256": identity["candidate_sha256"]},
        "provenance": {
            "source_sha256": identity["source_sha256"],
            "judgment_policy_sha256": identity["policy_sha256"],
            "benchmark_sha256": identity["benchmark_sha256"],
            "rubric_version": calculation["rubric_version"],
            "dimension_calculation_profile": calculation["calculation_profile"],
        },
        "audit_scope": {"mode": calculation["audit_mode"], "complete": calculation["status"] == "scored"},
        "dimension_calculations": _calculation_reference(calculation_record, calculation),
        "scorecard": _scorecard(calculation),
        "total_score": calculation["total_score"],
        "interpretation": metadata["interpretation"],
        "metrics": {"keep_precision": {key: reliability[key] for key in ("keep_precision_numerator", "keep_precision_denominator", "keep_precision", "treatment_recall", "reliability_f1")}},
        "item_assessments": {"schema_version": items["schema_version"], "artifact_path": items_record["path"], "sha256": items_record["sha256"], "grading_policy": items["grading_policy"], "summary": deepcopy(items["summary"])},
        "structure_audit": _structure_reference(structure_record),
        "projection_metadata": {"schema_version": metadata["schema_version"], "artifact_path": metadata_record["path"], "sha256": metadata_record["sha256"], "projection_metadata_sha256": metadata["projection_metadata_sha256"]},
        "critical_gates": deepcopy(metadata["critical_gates"]),
        "defect_counts": deepcopy(metadata["defect_counts"]),
        "comparison_key": {
            "source_sha256": identity["source_sha256"],
            "benchmark_sha256": identity["benchmark_sha256"],
            "judgment_policy_sha256": identity["policy_sha256"],
            "page_map_sha256": identity["page_map_sha256"],
            "chunk_manifest_sha256": identity["chunk_manifest_sha256"],
            "inclusion_policy": metadata["inclusion_policy"],
            "audit_mode": calculation["audit_mode"],
            "uncertainty_policy": metadata["uncertainty_policy"],
            "rubric_version": calculation["rubric_version"],
            "dimension_calculation_profile": calculation["calculation_profile"],
        },
        "limitations": deepcopy(metadata["limitations"]),
    }
    core.validate_schema_document(result, "evaluation-result-v10.schema.json", "Generated V8 evaluation result")
    return result


def _grade_label(score: int | float | None) -> str:
    if score is None:
        return "Not scored"
    if score >= 90:
        return "Excellent"
    if score >= 80:
        return "Strong"
    if score >= 70:
        return "Mixed"
    if score >= 60:
        return "Weak"
    return "Poor"


def _web_report(
    *,
    result: Mapping[str, Any],
    calculation: Mapping[str, Any],
    calculation_record: Mapping[str, Any],
    items: Mapping[str, Any],
    items_record: Mapping[str, Any],
    structure: Mapping[str, Any],
    structure_record: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    calculation_ref = _calculation_reference(calculation_record, calculation)
    structure_ref = _structure_reference(structure_record)
    precision = deepcopy(result["metrics"]["keep_precision"])
    report = {
        "schema_version": "subject-index-web-report-v8",
        "report_id": metadata["report_id"],
        "headline": metadata["headline"],
        "summary": metadata["summary"],
        "grade": {"score": calculation["total_score"], "maximum": 100, "label": _grade_label(calculation["total_score"])},
        "scorecard": _scorecard(calculation, web=True),
        "calculation_explainer": {**calculation_ref, "item_grades_used": False, "gates_used": False},
        "precision_diagnostics": precision,
        "structure_audit": {**structure_ref, **deepcopy(calculation["structure_audit"])},
        "key_metrics": [{"metric_id": key, "value": value} for key, value in precision.items()],
        "density": deepcopy(structure["density"]),
        "gate_status": {"critical_gates": deepcopy(result["critical_gates"]), "outcomes_sha256": core.canonical_hash({"critical_gates": result["critical_gates"]}), "used_in_score_arithmetic": False},
        "strengths": deepcopy(metadata["strengths"]),
        "defects": deepcopy(metadata["defects"]),
        "examples": deepcopy(metadata["examples"]),
        "item_grade_index": {"schema_version": items["schema_version"], "artifact_path": items_record["path"], "sha256": items_record["sha256"], "grading_policy": items["grading_policy"], "summary": deepcopy(items["summary"]), "color_legend": deepcopy(items["color_legend"]), "interaction": {"color_source": "grade.color_token", "popover_source": "popover", "not_measured_behavior": "neutral_not_failure"}},
        "locator_explanations": [deepcopy(item["locator_explanation"]) for item in items["locator_assessments"]],
        "score_views": {"primary_view_id": "canonical_as_delivered", "adjustment_status": "none", "views": [{"view_id": "canonical_as_delivered", "label": "Canonical as delivered", "view_kind": "observed", "score": calculation["total_score"], "maximum": 100, "calculation": calculation_ref, "structure_audit": structure_ref, "causal_attribution": "primary_observed_result", "provenance_artifacts": []}]},
        "methodology": {
            "rubric_version": calculation["rubric_version"],
            "calculation_profile": calculation["calculation_profile"],
            "locator_utility": "Independent page treatment and complete-path fit remain separate diagnostics.",
            "diagnostic_minimum_rule": "The displayed locator grade is 100 times min(treatment, complete-path fit).",
            "binary_keep_rule": "Only supported locators receive Page-reference Reliability keep credit.",
            "keep_precision": "Supported divided by assessable registered locator assignments.",
            "editorial_selectivity_separate": True,
            "long_string_review": "More than six displayed locators triggers review.",
            "long_range_review": "A continuous range longer than ten pages triggers review.",
            "numeric_trigger_is_automatic_defect": False,
        },
        "comparability": deepcopy(result["comparison_key"]),
        "disclosures": ["Item grades are diagnostic and do not reconstruct the six-dimension score.", "Critical gates are reported separately from score arithmetic."],
        "limitations": deepcopy(result["limitations"]),
        "evidence_index": {"calculation": calculation_ref, "structure_audit": structure_ref, "item_assessments": {"artifact_path": items_record["path"], "sha256": items_record["sha256"]}},
    }
    core.validate_schema_document(report, "web-report-v8.schema.json", "Generated V8 web report")
    return report


def _validate_structure_inventory(structure: Mapping[str, Any], inventory: Mapping[str, Any]) -> None:
    denominator = structure["candidate_denominator"]
    nodes = [{key: item[key] for key in ("node_id", "heading_path", "role")} for item in inventory["heading_nodes"]]
    references = [item["reference_id"] for item in inventory["cross_references"]]
    path_ids = [item["path_id"] for item in inventory["paths"] if item["locator_ids"]]
    core.require(denominator["nodes"] == nodes, "structure_candidate_denominator_mismatch", "Structure node denominator differs from the registered item inventory.")
    for values, field, count_field, hash_field in (
        (references, "cross_reference_ids", "cross_reference_count", "cross_reference_id_set_sha256"),
        (path_ids, "locator_bearing_path_ids", "locator_bearing_path_count", "locator_bearing_path_id_set_sha256"),
    ):
        core.require(denominator[field] == values and denominator[count_field] == len(values) and denominator[hash_field] == id_set_hash(values), "structure_candidate_denominator_mismatch", f"Structure {field} differs from the registered item inventory.")
    core.require(denominator["node_count"] == len(nodes) and denominator["node_id_set_sha256"] == id_set_hash([item["node_id"] for item in nodes]), "structure_candidate_denominator_mismatch", "Structure node count or hash differs from the registered item inventory.")
    metrics = structure["metrics"]
    core.require(metrics["total_paths"] == len(inventory["paths"]) and metrics["total_nodes"] == len(nodes) and metrics["expanded_locators"] == len(inventory["locators"]), "structure_candidate_metric_mismatch", "Structure metrics differ from the registered item inventory.")


def command_register_structure(args: argparse.Namespace) -> None:
    command = "register-structure-audit"
    state_path = Path(args.state).resolve()
    try:
        with evaluation_mutation_lock(state_path):
            state, warnings = _transition_state(state_path, "structure_audit")
            _, candidate_record, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="candidate-index-v2", schema_name="candidate-index-v2.schema.json")[0]
            inventory, inventory_record, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="subject-index-item-inventory-v2", schema_name="item-inventory-v2.schema.json")[0]
            structure_path = Path(args.input).resolve()
            core.require(structure_path.is_file(), "input_not_found", f"Structure audit does not exist: {structure_path}")
            relative = portable_relative_path(structure_path, state_path.parent)
            core.require(not any(item.get("path") == relative for item in state["artifacts"]), "registered_output_collision", "Structure audit path is already registered.", relative)
            structure = core.load_json(structure_path, "Structure audit")
            core.validate_schema_document(structure, "structure-audit-v5.schema.json", "Structure audit")
            validate_structure_audit_semantics(structure)
            core.require(structure["evaluation_id"] == state["evaluation_id"], "evaluation_identity_mismatch", "Structure audit evaluation_id differs from canonical state.")
            core.require(structure["candidate_sha256"] == state["candidate"]["candidate_sha256"] == inventory["candidate_sha256"], "candidate_identity_mismatch", "Structure audit candidate identity differs from registered candidate artifacts.")
            core.require(structure["audit_mode"] == state["configuration"]["audit_mode"], "audit_mode_identity_mismatch", "Structure audit mode differs from canonical state.")
            core.require(candidate_record["sha256"] == state["candidate"]["normalized_sha256"] and inventory_record["path"] == state["candidate"]["item_inventory_path"], "candidate_identity_mismatch", "Canonical candidate artifact binding is inconsistent.")
            _validate_structure_inventory(structure, inventory)
            payload = structure_path.read_bytes()
            stamp = now()
            record = _artifact_record(state_path.parent, structure_path, payload, stage="structure_audit", artifact_type="structure_audit", schema_version="structure-audit-v5", stamp=stamp, input_sha256=(candidate_record["sha256"], inventory_record["sha256"]))
            updated = _add_records_and_complete(state, state_path, "structure_audit", [record], "Validated and registered the native V8 structure audit atomically.")
            save_state(state_path, updated)
        core.emit({"command": command, "ok": True, "evaluation_id": state["evaluation_id"], "artifacts_registered": [record["path"]], "artifacts_written": [str(state_path)], "next_actions": [next_stage(updated)], "warnings": warnings})
    except (OSError, core.CalculationError, StructureAuditError, ValueError) as exc:
        if isinstance(exc, (core.CalculationError, StructureAuditError)):
            error = {"code": exc.code, "message": exc.message, "details": exc.details}
        else:
            error = {"code": "structure_registration_error", "message": str(exc)}
        core.emit({"command": command, "ok": False, "error": error}, 1)


def _calculation_loaded_from_state(
    state: Mapping[str, Any], state_path: Path, config_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[Mapping[str, Any]], list[Mapping[str, Any]], dict[str, Any]]:
    policy, policy_record, policy_path = _registered_documents(state, state_path, stage="define_policy", schema_version="subject-index-evaluation-policy-v4", schema_name="evaluation-policy-v4.schema.json")[0]
    validate_v8_policy(policy)
    manifest, manifest_record, manifest_path = _registered_documents(state, state_path, stage="chunk_definition", schema_version="chunk-manifest-v1", schema_name="chunk-manifest.schema.json")[0]
    locator_entries = _registered_documents(state, state_path, stage="locator_audit", schema_version="locator-audit-v2", schema_name="locator-audit-v2.schema.json", many=True)
    missing_entries = _registered_documents(state, state_path, stage="missing_access_audit", schema_version="missing-access-audit-v1", schema_name="missing-access-audit.schema.json", many=True)
    structure, structure_record, structure_path = _registered_documents(state, state_path, stage="structure_audit", schema_version="structure-audit-v5", schema_name="structure-audit-v5.schema.json")[0]
    validate_structure_audit_semantics(structure)
    inventory, inventory_record, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="subject-index-item-inventory-v2", schema_name="item-inventory-v2.schema.json")[0]
    candidate, _, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="candidate-index-v2", schema_name="candidate-index-v2.schema.json")[0]
    core.require(inventory_record["path"] == state["candidate"]["item_inventory_path"] and candidate["candidate_sha256"] == inventory["candidate_sha256"], "candidate_identity_mismatch", "Registered candidate and item inventory differ.")

    def reference(record: Mapping[str, Any]) -> dict[str, str]:
        target = resolve_artifact_path(state_path, record["path"])
        return {"path": Path(os.path.relpath(target, config_path.parent)).as_posix(), "sha256": record["sha256"]}

    config = {
        "schema_version": "subject-index-dimension-calculation-input-v2",
        "evaluation_id": state["evaluation_id"],
        "audit_mode": state["configuration"]["audit_mode"],
        "inputs": {
            "policy": reference(policy_record),
            "chunk_manifest": reference(manifest_record),
            "locator_audits": [reference(item[1]) for item in locator_entries],
            "missing_access_audits": [reference(item[1]) for item in missing_entries],
            "structure_audit": reference(structure_record),
        },
    }
    core.validate_config_shape(config)
    core.validate_schema_document(config, "dimension-calculation-input.schema.json", "Generated calculation input")
    locator_loaded = []
    missing_loaded = []
    artifacts = [{"role": "policy", "path": config["inputs"]["policy"]["path"], "sha256": policy_record["sha256"], "schema_version": policy["schema_version"]}]
    paths = [policy_path]
    for prefix, source, destination in (("locator_audit", locator_entries, locator_loaded), ("missing_access_audit", missing_entries, missing_loaded)):
        for index, (document, record, path) in enumerate(source):
            artifact = {"role": f"{prefix}[{index}]", "path": reference(record)["path"], "sha256": record["sha256"], "schema_version": document["schema_version"]}
            destination.append((document, artifact, path))
            artifacts.append(artifact)
            paths.append(path)
    manifest_artifact = {"role": "chunk_manifest", "path": config["inputs"]["chunk_manifest"]["path"], "sha256": manifest_record["sha256"], "schema_version": manifest["schema_version"]}
    structure_artifact = {"role": "structure_audit", "path": config["inputs"]["structure_audit"]["path"], "sha256": structure_record["sha256"], "schema_version": structure["schema_version"]}
    artifacts.extend([structure_artifact, manifest_artifact])
    paths.extend([structure_path, manifest_path])
    loaded = {
        "config": config,
        "policy": policy,
        "locator_documents": [item[0] for item in locator_loaded],
        "missing_documents": [item[0] for item in missing_loaded],
        "structure": structure,
        "chunk_manifest": manifest,
        "locator_input_entries": locator_loaded,
        "missing_input_entries": missing_loaded,
        "input_artifacts": artifacts,
        "input_paths": paths,
        "config_path": config_path,
    }
    return loaded, inventory, inventory_record, loaded["locator_documents"], loaded["missing_documents"], structure_record


def command_score_state(args: argparse.Namespace) -> None:
    command = "score-index"
    state_path = Path(args.state).resolve()
    try:
        with evaluation_mutation_lock(state_path):
            state, warnings = _transition_state(state_path, "scoring")
            root = state_path.parent
            output_dir = _state_output_path(root, args.output_dir)
            outputs = {
                "input": output_dir / "dimension-calculation-input.v2.json",
                "calculation": output_dir / "dimension-calculations.v5.json",
                "items": output_dir / "item-assessments.v6.json",
                "metadata": output_dir / "projection-metadata.v1.json",
                "result": output_dir / "evaluation-result.v10.json",
            }
            collisions = [str(path) for path in outputs.values() if path.exists()]
            core.require(not collisions, "output_exists", "Refusing to overwrite scoring output.", collisions)
            loaded, inventory, inventory_record, locator_documents, missing_documents, structure_record = _calculation_loaded_from_state(state, state_path, outputs["input"])
            calculation = calculate_loaded(loaded)
            core.require(calculation["status"] == "scored", "v8_score_incomplete", "Current full-state inputs did not produce a complete score.", calculation["status"])
            core.validate_schema_document(calculation, "dimension-calculations-v5.schema.json", "Generated V8 calculation")
            items = _current_item_assessments(inventory, inventory_record, calculation, loaded["structure"], locator_documents, missing_documents)
            stamp = now()
            input_payload = _json_bytes(loaded["config"])
            calculation_payload = _json_bytes(calculation)
            items_payload = _json_bytes(items)
            input_hashes = [item["sha256"] for item in loaded["input_artifacts"]]
            input_record = _artifact_record(root, outputs["input"], input_payload, stage="scoring", artifact_type="dimension_calculation_input", schema_version="subject-index-dimension-calculation-input-v2", stamp=stamp, input_sha256=input_hashes)
            calculation_record = _artifact_record(root, outputs["calculation"], calculation_payload, stage="scoring", artifact_type="dimension_calculations", schema_version="subject-index-dimension-calculations-v5", stamp=stamp, input_sha256=input_hashes)
            items_record = _artifact_record(root, outputs["items"], items_payload, stage="scoring", artifact_type="item_assessments", schema_version="subject-index-item-assessments-v6", stamp=stamp, input_sha256=(calculation_record["sha256"], inventory_record["sha256"], structure_record["sha256"]))
            metadata = _projection_metadata(policy=loaded["policy"], calculation=calculation, calculation_record=calculation_record, structure=loaded["structure"], structure_record=structure_record, candidate_label=inventory["candidate_id"])
            metadata_payload = _json_bytes(metadata)
            metadata_record = _artifact_record(root, outputs["metadata"], metadata_payload, stage="scoring", artifact_type="projection_metadata", schema_version="subject-index-v8-projection-metadata-v1", stamp=stamp, input_sha256=(calculation_record["sha256"], structure_record["sha256"]))
            result = _evaluation_result(calculation=calculation, calculation_record=calculation_record, items=items, items_record=items_record, structure_record=structure_record, metadata=metadata, metadata_record=metadata_record)
            result_payload = _json_bytes(result)
            result_record = _artifact_record(root, outputs["result"], result_payload, stage="scoring", artifact_type="evaluation_result", schema_version="subject-index-evaluation-result-v10", stamp=stamp, visibility="public", input_sha256=(calculation_record["sha256"], items_record["sha256"], structure_record["sha256"], metadata_record["sha256"]))
            records = [input_record, calculation_record, items_record, metadata_record, result_record]
            updated = _add_records_and_complete(state, state_path, "scoring", records, "Assembled registered inputs, calculated V8 dimensions, and registered the validated V10 result atomically.")
            for path, payload in zip(outputs.values(), (input_payload, calculation_payload, items_payload, metadata_payload, result_payload), strict=True):
                _atomic_write(path, payload)
            save_state(state_path, updated)
        core.emit({"command": command, "ok": True, "evaluation_id": state["evaluation_id"], "total_score": calculation["total_score"], "artifacts_registered": [record["path"] for record in records], "artifacts_written": [str(path) for path in outputs.values()] + [str(state_path)], "next_actions": [next_stage(updated)], "warnings": warnings})
    except (OSError, core.CalculationError, StructureAuditError, ValueError) as exc:
        if isinstance(exc, (core.CalculationError, StructureAuditError)):
            error = {"code": exc.code, "message": exc.message, "details": exc.details}
        else:
            error = {"code": "scoring_registration_error", "message": str(exc)}
        core.emit({"command": command, "ok": False, "error": error}, 1)


def command_build_report_state(args: argparse.Namespace) -> None:
    command = "build-web-report"
    state_path = Path(args.state).resolve()
    try:
        with evaluation_mutation_lock(state_path):
            state, warnings = _transition_state(state_path, "web_report")
            result, result_record, _ = _registered_documents(state, state_path, stage="scoring", schema_version="subject-index-evaluation-result-v10", schema_name="evaluation-result-v10.schema.json")[0]
            calculation, calculation_record, _ = _registered_documents(state, state_path, stage="scoring", schema_version="subject-index-dimension-calculations-v5", schema_name="dimension-calculations-v5.schema.json")[0]
            items, items_record, _ = _registered_documents(state, state_path, stage="scoring", schema_version="subject-index-item-assessments-v6", schema_name="item-assessments-v6.schema.json")[0]
            metadata, metadata_record, _ = _registered_documents(state, state_path, stage="scoring", schema_version="subject-index-v8-projection-metadata-v1", schema_name="v8-projection-metadata-v1.schema.json")[0]
            structure, structure_record, _ = _registered_documents(state, state_path, stage="structure_audit", schema_version="structure-audit-v5", schema_name="structure-audit-v5.schema.json")[0]
            core.require(calculation["calculation_sha256"] == core.canonical_hash(calculation, "calculation_sha256"), "calculation_self_hash_mismatch", "Registered calculation self-hash does not reconstruct.")
            core.require(metadata["projection_metadata_sha256"] == core.canonical_hash(metadata, "projection_metadata_sha256"), "projection_metadata_self_hash_mismatch", "Registered projection metadata self-hash does not reconstruct.")
            core.require(result["evaluation_id"] == calculation["evaluation_id"] == items["evaluation_id"] == state["evaluation_id"], "evaluation_identity_mismatch", "Registered scoring artifacts use different evaluation identities.")
            core.require(result["dimension_calculations"]["sha256"] == calculation_record["sha256"] and result["item_assessments"]["sha256"] == items_record["sha256"] and result["structure_audit"]["sha256"] == structure_record["sha256"] and result["projection_metadata"]["sha256"] == metadata_record["sha256"], "result_artifact_binding_mismatch", "Registered result references do not match registered current artifacts.")
            output = _state_output_path(state_path.parent, args.output or str(Path(result_record["path"]).parent / "web-report.v8.json"))
            core.require(not output.exists(), "output_exists", "Refusing to overwrite web report.", str(output))
            report = _web_report(result=result, calculation=calculation, calculation_record=calculation_record, items=items, items_record=items_record, structure=structure, structure_record=structure_record, metadata=metadata)
            payload = _json_bytes(report)
            stamp = now()
            record = _artifact_record(state_path.parent, output, payload, stage="web_report", artifact_type="web_report", schema_version="subject-index-web-report-v8", stamp=stamp, visibility="public", input_sha256=(result_record["sha256"], calculation_record["sha256"], items_record["sha256"], structure_record["sha256"], metadata_record["sha256"]))
            updated = _add_records_and_complete(state, state_path, "web_report", [record], "Built and registered the validated current V8 web-report projection atomically.")
            _atomic_write(output, payload)
            save_state(state_path, updated)
        core.emit({"command": command, "ok": True, "evaluation_id": state["evaluation_id"], "report_id": report["report_id"], "artifacts_registered": [record["path"]], "artifacts_written": [str(output), str(state_path)], "next_actions": [], "warnings": warnings})
    except (OSError, core.CalculationError, StructureAuditError, ValueError) as exc:
        if isinstance(exc, (core.CalculationError, StructureAuditError)):
            error = {"code": exc.code, "message": exc.message, "details": exc.details}
        else:
            error = {"code": "web_report_registration_error", "message": str(exc)}
        core.emit({"command": command, "ok": False, "error": error}, 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight", help="Report exact V8 diagnostic-and-rating calculation sufficiency.")
    preflight.add_argument("--input", required=True)
    preflight.add_argument("--output")
    preflight.set_defaults(func=command_preflight)
    calculate = subparsers.add_parser("calculate", help="Derive all six V8 ratings from frozen ledgers.")
    calculate.add_argument("--input", required=True)
    calculate.add_argument("--output")
    calculate.set_defaults(func=command_calculate)
    register_structure = subparsers.add_parser("register-structure", help="Validate and atomically register the current native structure audit.")
    register_structure.add_argument("--state", required=True)
    register_structure.add_argument("--input", required=True)
    register_structure.set_defaults(func=command_register_structure)
    score = subparsers.add_parser("score", help="Build, validate, and atomically register all current V8 scoring artifacts from canonical state.")
    score.add_argument("--state", required=True)
    score.add_argument("--output-dir", default="scoring", help="Output directory inside the evaluation directory (default: scoring).")
    score.set_defaults(func=command_score_state)
    report = subparsers.add_parser("build-report", help="Build, validate, and atomically register the current V8 web report from canonical state.")
    report.add_argument("--state", required=True)
    report.add_argument("--output", help="Output path inside the evaluation directory (default: beside the registered result).")
    report.set_defaults(func=command_build_report_state)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
