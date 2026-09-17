#!/usr/bin/env python3
"""Deterministic current V8 scoring and projection tooling.

V8 uses the frozen keep judgment as binary rating credit while retaining the
independent page-treatment and complete-path-fit minimum as a diagnostic grade.
V8.1 revises consequence thresholds under a new frozen policy and calculation identity.
V8.2 adds direct destination gates without changing ordinary scores or ceilings.
"""

from __future__ import annotations

from runtime_profile import identity as runtime_identity, percentage_native, is_v10, semantic_uncertainty, versioned_cli, migration_module

import argparse
import hashlib
import json
import os
from collections import Counter
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import item_grade_v8_cli as item_grades
import item_projection_core as item_projection
import scoring_core as core
import web_projection
from policy_cli import destination_gate_policy_errors
from heading_access_provenance import (
    HeadingAccessProvenanceError,
    validate_heading_access_provenance,
)
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
import study_comparison
from structure_audit import (
    StructureAuditError,
    id_set_hash,
    materialize_structure_records,
    validate_structure_audit_semantics,
    validate_uncertainty_gate_scopes,
)


RUBRIC_VERSION = runtime_identity("subject-index-rubric-v8.2")
CALCULATION_PROFILE = runtime_identity("subject-index-dimension-calculation-v7")
CALCULATION_SCHEMA = runtime_identity("subject-index-dimension-calculations-v6")
ITEM_GRADING_POLICY = "subject-index-item-grading-v4"
POLICY_PROFILE = runtime_identity("subject-index-standard-policy-v8.2")

ZERO = Decimal(0)
ONE = Decimal(1)
TWO = Decimal(2)

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
        **({"semantic_unknown_axes":[a for a in ("treatment","complete_path_fit","keep","judgment_subtype") if locator["axis_resolution"].get(a)=="unresolved"],"label":"Semantically unresolved after inspection"} if "axis_resolution" in locator else {}),
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
        "schema_version": runtime_identity("subject-index-v8-locator-fit-preflight-v1"),
        "validated_complete_path_fit": [r for r in deterministic if "semantic_unknown_axes" not in r],
        **({"semantic_unresolved_after_inspection":[r for r in deterministic if "semantic_unknown_axes" in r]} if semantic_uncertainty() else {}),
        "invalid_or_contradictory_state": invalid,
        "group_counts": {
            "validated_complete_path_fit": sum("semantic_unknown_axes" not in r for r in deterministic),
            **({"semantic_unresolved_after_inspection":sum("semantic_unknown_axes" in r for r in deterministic)} if semantic_uncertainty() else {}),
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


def validate_v8_policy(policy_document: dict[str, Any], *, profile: str | None = None) -> None:
    """Validate the frozen policy itself, independent of Markdown wording."""
    core.validate_schema_document(
        policy_document, "evaluation-policy-v4.schema.json", "policy", profile=profile
    )
    gate_errors = destination_gate_policy_errors(policy_document)
    core.require(not gate_errors, "destination_gate_policy_incomplete", "The V8.2 policy must retain its direct destination gates.", gate_errors)
    core.require(
        policy_document.get("policy_sha256")
        == core.canonical_hash(policy_document, "policy_sha256"),
        "policy_self_hash_mismatch",
        "The V8 evaluation policy self-hash does not reconstruct.",
    )
    core.require(
        policy_document.get("policy_profile", {}).get("id") == runtime_identity("subject-index-standard-policy-v8.2", profile=profile),
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
        structure_document.get("schema_version") == "structure-audit-v6",
        "unsupported_structure_audit_schema",
        "Current V8 scoring requires structure-audit-v6.",
    )
    core.validate_schema_document(
        structure_document, "structure-audit-v6.schema.json", "structure_audit"
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
    validate_heading_access_provenance(
        structure_document,
        (item[0] for item in locator_entries),
        (item[0] for item in missing_entries),
    )
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
    scoring_inputs = dict(loaded)
    if "structure" in loaded:
        scoring_inputs["structure"] = deepcopy(loaded["structure"])
        scoring_inputs["structure"].pop("causal_projection", None)
        scoring_inputs["structure"].pop("uncertainty_gate_scopes", None)
        scoring_inputs["structure"]["schema_version"] = "structure-audit-v5"
        for reference in scoring_inputs["structure"].get("cross_reference_judgments", []):
            reference.pop("target_resolution", None)
        for node in scoring_inputs["structure"].get("node_judgments", []):
            component = node["component_judgments"]["heading_access_architecture"]
            for field in ("causal_findings", "primary_finding_id", "primary_basis"):
                component.pop(field, None)
    ledgers, missing = core.preflight_loaded(scoring_inputs)
    if ledgers is None:
        for issue in missing:
            issue["evaluation_outcome"] = "indeterminate"
            issue["publication_quality_failure"] = False
        return None, missing
    validity = _evaluation_validity(loaded["policy"], loaded["structure"], {"dimensions": [{"dimension_id": "page_reference_reliability", "reliability_provenance": {"original_locator_denominator": ledgers["locator_original"], "uninspectable_locator_count": sum(row.get("judgment") == "uninspectable" for row in ledgers["locators"])}}]})
    missing.extend({"code": row["blocker_id"], "message": row["reason"], "evaluation_outcome": validity["status"], "publication_quality_failure": False, "details": row} for row in validity["blockers"])
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
    semantic_rows = [r for r in ledgers["locators"] if "axis_resolution" in r] if semantic_uncertainty() else []
    semantic_keep = [r for r in semantic_rows if r["axis_resolution"]["keep"] == "unresolved"]
    by_id = {item["locator_id"]: item for item in assignments}
    measured_locators = [
        item for item in ledgers["locators"] if item.get("judgment") in {"supported", "partially_supported", "unsupported", *({"not_kept_subtype_unresolved"} if semantic_uncertainty() else set())}
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
        semantic_unresolved=len(semantic_keep),
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

    assessed_assignments = assignments if semantic_rows else [by_id[item["locator_id"]] for item in measured_locators]
    diagnostic_numerator = sum(
        (core.decimal_value(item["diagnostic_credit"]) for item in assessed_assignments if item["diagnostic_credit"] is not None), ZERO
    )
    treatment_numerator = sum(
        (core.decimal_value(item["treatment_score"]) for item in assessed_assignments if item["treatment_score"] is not None), ZERO
    )
    fit_numerator = sum(
        (core.decimal_value(item["fit_score"]) for item in assessed_assignments if item["fit_score"] is not None), ZERO
    )
    supported = sum(item["judgment"] == "supported" for item in measured_locators)
    found = sum(item["status"] == "found" for item in measured_treatments)
    assessable = len(measured_locators)
    mean_diagnostic = diagnostic_numerator / Decimal(assessable) if assessable else ZERO
    mean_treatment = treatment_numerator / Decimal(assessable) if assessable else ZERO
    mean_fit = fit_numerator / Decimal(assessable) if assessable else ZERO
    keep_precision = core.rate(supported, assessable)
    recall = core.rate(found, len(measured_treatments))

    unknown_loc = len(uninspectable_locators) + len(locator_not_measured) + len(semantic_keep)
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
        central_base = Decimal(100) * core.f1(keep_precision, recall)
        lower_base = Decimal(100) * core.f1(keep_lower, recall_lower)
        upper_base = Decimal(100) * core.f1(keep_upper, recall_upper)
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
    # Only severe/no-fit delivered evidence participates in consequence ceilings.
    pattern = [
        item
        for item in measured_locators
        if item.get("judgment") == "unsupported"
        and item.get("complete_path_fit") in {"severe_mismatch", "no_fit"}
        and set(item.get("error_codes", [])) & core.RELIABILITY_CODES
    ]
    delivered_major = [row for row in ledgers["defects"] if core.material_consequence(row) and core.delivered_bad_locators(row, measured_locators)]
    critical = [row for row in critical if core.material_consequence(row) and core.delivered_bad_locators(row, measured_locators)]
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
        high_max, _, high_band = core.high_value_cap(high_found_value, high_total)
        pattern_max, pattern_triggered, pattern_band = core.reliability_pattern_cap(
            pattern_count, locator_total, units, unit_denominator
        )
        return [
            core.cap_record("reliability.major_delivered_no_fit", Decimal(80), bool(delivered_major), {"severity": ["major", "critical"], "fit": ["severe_mismatch", "no_fit"], "consequence": ["blocks", "misleads"]}, {"defect_count": len(delivered_major)}, [row["defect_id"] for row in delivered_major]),
            core.cap_record(
                "reliability.critical_locator",
                Decimal(40),
                bool(critical),
                {"severity": "critical", "defect_kinds": ["fabricated_locator", "nonexistent_locator", "out_of_scope_locator"]},
                {"defect_count": len(critical)},
                [item["defect_id"] for item in critical],
            ),
            core.cap_record(
                "reliability.high_value_treatment_recall",
                high_max,
                False,
                {"rule": "V8.1 recall omissions receive ordinary score deductions only", "band": high_band},
                {"found": high_found_value, "expected": high_total, "rate": core.decimal_text(core.rate(high_found_value, high_total))},
                high_miss_evidence,
            ),
            core.cap_record(
                "reliability.distributed_unsupported_pattern",
                pattern_max,
                pattern_triggered,
                {"minimum_count": 3, "fit": ["severe_mismatch", "no_fit"], "minimum_source_unit_rate": "0.25", "rate_table": "reliability_owned_unsupported_v1", "band": pattern_band},
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

    semantic_low=[];semantic_high=[]
    if semantic_rows:
        from v10_semantic import resolved_possibilities
        for row in semantic_rows:
            worlds=resolved_possibilities(row)
            def adverse(value):return value['complete_path_fit'] in {'severe_mismatch','no_fit'}
            semantic_low.append(max(worlds,key=lambda value:(value['judgment']=='unsupported',adverse(value))))
            semantic_high.append(min(worlds,key=lambda value:(value['judgment']=='unsupported',adverse(value))))
    semantic_ids={row['locator_id'] for row in semantic_rows}
    factual=[row for row in measured_locators if row['locator_id'] not in semantic_ids]
    def patterns(rows):
        return [r for r in rows if r['judgment']=='unsupported' and r['complete_path_fit'] in {'severe_mismatch','no_fit'} and set(r.get('error_codes',[])) & core.RELIABILITY_CODES]
    low_pattern=patterns(factual+semantic_low) if semantic_rows else pattern
    high_pattern=patterns(factual+semantic_high) if semantic_rows else pattern
    physical_unknown=len(uninspectable_locators)+len(locator_not_measured)
    known_high_misses = [item["treatment_id"] for item in high_measured if item["status"] == "missed"]
    known_pattern_ids = [item["locator_id"] for item in pattern]
    central_caps = caps(high_found, len(high_measured), len(pattern), assessable, len(pattern_units), known_high_misses, known_pattern_ids)
    lower_caps = caps(
        high_found,
        len(high_measured) + len(high_unknown) + len(high_not_measured_ids),
        len(low_pattern) + physical_unknown,
        assessable + unknown_loc,
        len({r.get("_source_unit_id") for r in low_pattern if r.get("_source_unit_id")} | unknown_locator_units),
        known_high_misses + [item["treatment_id"] for item in high_unknown] + high_not_measured_ids,
        [r["locator_id"] for r in low_pattern] + [item["locator_id"] for item in uninspectable_locators] + locator_not_measured,
    )
    upper_caps = caps(
        high_found + len(high_unknown) + len(high_not_measured_ids),
        len(high_measured) + len(high_unknown) + len(high_not_measured_ids),
        len(high_pattern),
        assessable + unknown_loc,
        len({r.get("_source_unit_id") for r in high_pattern if r.get("_source_unit_id")}),
        known_high_misses,
        [r["locator_id"] for r in high_pattern],
    )

    if semantic_rows:
        critical_candidates=core.defect_subset(ledgers,'page_reference_reliability',severities={'critical'},kinds={'fabricated_locator','nonexistent_locator','out_of_scope_locator'})
        for cap_rows,witness in ((lower_caps,factual+semantic_low),(upper_caps,factual+semantic_high)):
            for cap in cap_rows:
                if cap['cap_id'] not in {'reliability.major_delivered_no_fit','reliability.critical_locator'}:continue
                candidates=critical_candidates if cap['cap_id']=='reliability.critical_locator' else ledgers['defects']
                qualified=[r for r in candidates if core.material_consequence(r) and core.delivered_bad_locators(r,witness)]
                cap['triggered']=bool(qualified);cap['observed']={'defect_count':len(qualified)}
                cap['affected_evidence_ids']=[r['defect_id'] for r in qualified]
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
    if semantic_rows:
        def cap_outcome(rows):return [(r['cap_id'],r['triggered'],r['maximum_percentage']) for r in rows]
        stable_caps=cap_outcome(lower_caps)==cap_outcome(upper_caps)
        result['missing_data_bounds']['stable_cap_outcome']=stable_caps
        if not stable_caps:
            result.update(status='not_scored_insufficient_evidence',dimension_percentage=None,weighted_contribution=None)
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
        if item[field] is None and item["disposition"] == "semantic_unresolved":return "semantic_unresolved"
        return str(item[field])

    if semantic_rows:
        treatment_tiers += ('semantic_unresolved',)
        fit_tiers += ('semantic_unresolved',)
        diagnostic_values += ('semantic_unresolved',)
        rating_values += ('semantic_unresolved',)
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
        "locator_treatment_class": dict(Counter(item.get("treatment_class") or "semantic_unresolved" for item in ledgers["locators"])),
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
            "weight": "base_percentage_times_100",
            "effective_weight": "base_percentage_times_100",
            "weight_renormalized": False,
        },
        {
            "component_id": "high_value_treatment_recall_safeguard",
            "raw_numerator": core.decimal_text(Decimal(high_found)),
            "raw_denominator": core.decimal_text(Decimal(len(high_measured))),
            "normalized_value": core.decimal_text(core.rate(high_found, len(high_measured))),
            "weight": "reported_diagnostic_only",
            "effective_weight": "reported_diagnostic_only",
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
            ("supported", "partially_supported", "unsupported", "uninspectable") + (("semantic_unresolved","not_kept_subtype_unresolved") if semantic_rows else ()),
        ) | {"not_measured": len(locator_not_measured)},
        "counts_by_treatment_class": dict(sorted(Counter(item.get("treatment_class") or "semantic_unresolved" for item in ledgers["locators"]).items())) | ({"not_measured": len(locator_not_measured)} if locator_not_measured else {}),
        "counts_by_treatment_tier": treatment_counts,
        "counts_by_fit_tier": fit_counts,
        "counts_by_diagnostic_credit_value": diagnostic_counts,
        "counts_by_rating_credit_value": rating_counts,
        "locator_utility_assignments": assignments,
        "locator_path_bindings": {row["locator_id"]: row.get("path_id") for row in ledgers["locators"]},
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
        "pre_cap_percentage": result["pre_cap_percentage"],
        "cap_evaluations": result["cap_evaluations"],
        "applied_cap": result["applied_cap"],
        "uncertainty_lower": result["missing_data_bounds"]["lower"],
        "uncertainty_upper": result["missing_data_bounds"]["upper"],
        "dimension_percentage": result["dimension_percentage"],
        "dimension_weight": result["dimension_weight"],
        "weighted_contribution": result["weighted_contribution"],
    }
    if semantic_rows:
        from v10_semantic import apply_axis_diagnostics
        apply_axis_diagnostics(result,assignments,semantic_rows,semantic_keep)
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
    execution = (loaded.get("study_identity") or {}).get("execution_contract")
    if semantic_uncertainty():
        core.require(execution is not None, "execution_compatibility_required", "Corrected calculations require an explicitly adopted state and reviewed execution binding.")
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
        for cap_set in (dimension["cap_evaluations"], dimension["missing_data_bounds"]["lower"]["cap_evaluations"], dimension["missing_data_bounds"]["upper"]["cap_evaluations"]):
            for cap in cap_set:
                evidence = set(cap["affected_evidence_ids"])
                rows = [row for row in ledgers["defects"] if row["defect_id"] in evidence]
                cap["observed"]["consequence_evidence"] = deepcopy(rows)
                cap["observed"]["qualifying_locator_evidence"] = [{key: locator.get(key) for key in ("locator_id", "path_id", "complete_path_fit", "severity", "judgment")} for row in rows for locator in core.delivered_bad_locators(row, ledgers["locators"])]
                cap["affected_evidence_ids"] = sorted(evidence | {item for row in rows for item in row["affected_item_ids"]})
                consequences = {
                    "meaningful_coverage": "Essential subject access is absent.",
                    "editorial_selectivity": "Systemic contentless entries dilute useful retrieval.",
                    "conceptual_stance_fidelity": "Material heading meaning or source stance is misrepresented.",
                    "page_reference_reliability": "Delivered severe/no-fit locators materially mislead retrieval.",
                    "findability_navigation": "Delivered routes mislead or block retrieval, high-priority access is destroyed, or the frozen aggregate access threshold is met.",
                    "mechanics_consistency": "Material structural failure or frozen aggregate mechanical friction impairs navigation.",
                }
                cap["observed"]["severity_basis"] = sorted({row["severity_basis"] for row in rows}) if rows else ["frozen_quantitative_threshold"]
                cap["observed"]["retrieval_consequence"] = sorted({row["retrieval_consequence"] for row in rows}) if rows else [consequences[dimension["dimension_id"]]]
                cap["observed"]["threshold_reason"] = (consequences[dimension["dimension_id"]] + " Observed evidence satisfies " + core.canonical_json_text(cap["threshold"])) if cap["triggered"] else "Threshold not met."
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
    unrounded_total = sum((core.decimal_value(item["weighted_contribution"]) for item in dimensions), ZERO) if all_scored else None
    total = core.round_overall_percentage(unrounded_total) if unrounded_total is not None else None
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
        "overall_percentage": core.displayed_number(total, Decimal("0.01")) if total is not None else None,
        "maximum_percentage": 100,
        "final_rounding": {
            "mode": "ROUND_HALF_UP",
            "quantum": "0.01",
            "input": core.decimal_text(unrounded_total) if unrounded_total is not None else None,
            "output": core.decimal_text(total) if total is not None else None,
        },
        "arithmetic_check": all_scored and total == unrounded_total.quantize(Decimal("0.01"), rounding=core.ROUND_HALF_UP),
    }
    architecture = loaded["structure"]["locator_architecture"]
    result["structure_audit"] = {
        "schema_version": "structure-audit-v5",
        "candidate_denominator": deepcopy(loaded["structure"]["candidate_denominator"]),
        "full_scope_attestation": deepcopy(loaded["structure"]["full_scope_attestation"]),
        "locator_architecture": deepcopy(architecture),
        "uncertainties": deepcopy(loaded["structure"]["uncertainties"]),
    }
    if semantic_uncertainty():
        result["execution_contract"] = deepcopy(execution)
        result["calculation_id"] = "CALC-" + core.canonical_hash({"baseline_id":result["calculation_id"],"execution_contract":execution})[:12].upper()
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
        ledgers, base_missing = preflight_loaded(loaded)
        fit_report = (
            locator_fit_preflight(ledgers, loaded["config"]["audit_mode"])
            if ledgers is not None
            else {
                "schema_version": runtime_identity("subject-index-v8-locator-fit-preflight-v1"),
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
            "evaluation_outcome": "invalid" if any(row.get("evaluation_outcome") == "invalid" for row in missing) else "indeterminate" if missing else "valid",
            "publication_quality_failure": loaded["structure"].get("scoring_context", {}).get("candidate_attempt", {}).get("status") in {"empty", "structurally_incomplete", "unparseable"},
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
    except (OSError, core.CalculationError, HeadingAccessProvenanceError) as exc:
        error = {"code": exc.code, "message": exc.message, "details": exc.details} if isinstance(exc, (core.CalculationError, HeadingAccessProvenanceError)) else {"code": "file_error", "message": str(exc)}
        core.emit({"command": "v8-calculation-sufficiency-preflight", "ok": False, "error": error}, 1)


def command_calculate(args: argparse.Namespace) -> None:
    try:
        loaded = load_v8_inputs(Path(args.input).resolve())
        result = calculate_loaded(loaded)
        core.validate_schema_document(result, "dimension-calculations-v6.schema.json", "Generated V8 dimension calculations")
        if args.output:
            output_path = Path(args.output).resolve()
            core.require(not core.aliases_existing_file(output_path, {loaded["config_path"], *loaded["input_paths"]}), "output_aliases_frozen_input", "Calculation output must not overwrite frozen evidence.")
            write_json(output_path, result)
            response = {"command": "calculate-v8-dimensions", "ok": True, "evaluation_id": result["evaluation_id"], "status": result["status"], "overall_percentage": result["overall_percentage"], "calculation_sha256": result["calculation_sha256"], "artifact_written": str(output_path)}
        else:
            response = {"command": "calculate-v8-dimensions", "ok": True, **result}
        core.emit(response)
    except (OSError, core.CalculationError, HeadingAccessProvenanceError) as exc:
        error = {"code": exc.code, "message": exc.message, "details": exc.details} if isinstance(exc, (core.CalculationError, HeadingAccessProvenanceError)) else {"code": "file_error", "message": str(exc)}
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
    sha256: str | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any], Path]]:
    records = [
        item for item in state.get("artifacts", [])
        if item.get("stage") == stage and (item.get("schema_version") == schema_version or (semantic_uncertainty() and schema_version == "locator-audit-v2" and item.get("schema_version") == "locator-audit-v3"))
        and (sha256 is None or item.get("sha256") == sha256)
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


def _replace_records_and_complete(
    state: dict[str, Any],
    state_path: Path,
    stage: str,
    records: Sequence[dict[str, Any]],
    note: str,
) -> dict[str, Any]:
    """Replace one complete stage without changing any other stage records."""
    updated = deepcopy(state)
    updated["artifacts"] = [item for item in updated["artifacts"] if item.get("stage") != stage]
    updated["artifacts"].extend(records)
    updated["artifacts"].sort(key=lambda item: item["path"])
    stamp = records[0]["recorded_at"]
    updated["stages"][stage] = {"status": "completed", "updated_at": stamp, "notes": [note]}
    updated["updated_at"] = stamp
    errors, _ = validate_state(updated, state_path=state_path, check_files=False)
    core.require(not errors, "canonical_state_invalid", f"Replacing {stage} would leave invalid canonical state.", errors)
    return updated


def _validate_complete_web_bundle(
    state: Mapping[str, Any],
    state_path: Path,
    expected_records: Sequence[Mapping[str, Any]],
    output: Path,
    bundle_output: Path,
    current_inputs: Sequence[Mapping[str, Any]],
    calculation: Mapping[str, Any],
) -> None:
    """Validate the registered web bundle and require an exact managed target set."""
    registered = [deepcopy(item) for item in state["artifacts"] if item.get("stage") == "web_report"]
    expected_by_path = {item["path"]: item for item in expected_records}
    registered_by_path = {item["path"]: item for item in registered}
    core.require(
        len(registered_by_path) == len(registered) and set(registered_by_path) == set(expected_by_path),
        "replacement_bundle_incomplete",
        "The completed registered web-report bundle is partial or uses unexpected paths.",
        {"expected": sorted(expected_by_path), "registered": sorted(registered_by_path)},
    )

    schema_names = {
        "web_report": "web-report-v10.schema.json",
        "web_projection": "web-projection-v1.schema.json",
        "web_index_records": "web-collection-v1.schema.json",
        "web_source_subjects": "web-collection-v1.schema.json",
        "web_density": "web-collection-v1.schema.json",
        "correction_overlay": "correction-overlay-v1.schema.json",
    }
    documents: dict[str, dict[str, Any]] = {}
    for relative, expected in expected_by_path.items():
        record = registered_by_path[relative]
        core.require(
            (record.get("artifact_type"), record.get("schema_version"))
            == (expected.get("artifact_type"), expected.get("schema_version")),
            "replacement_bundle_identity_mismatch",
            f"Registered web artifact identity is unexpected: {relative}",
        )
        path = resolve_artifact_path(state_path, relative).resolve()
        core.require(path.is_file(), "registered_artifact_missing", f"Registered artifact is unavailable: {relative}")
        actual = core.sha256_file(path)
        core.require(actual == record["sha256"], "registered_artifact_hash_mismatch", f"Registered artifact bytes changed: {relative}", {"expected_sha256": record["sha256"], "actual_sha256": actual})
        artifact_type = record["artifact_type"]
        document = core.load_json(path, record["schema_version"])
        if artifact_type != "web_report":
            if artifact_type not in {"web_projection", "web_density"}:
                core.validate_schema_document(document, schema_names[artifact_type], record["schema_version"])
        documents[artifact_type] = document

    report = documents["web_report"]
    projection = documents["web_projection"]
    expected_scorecard = _scorecard(calculation)
    dimension_denominators = web_projection.dimension_denominator_disclosures(calculation)
    core.require(report.get("scorecard") == expected_scorecard, "replacement_bundle_identity_mismatch", "Registered web report scorecard differs from the current canonical calculation.")
    try:
        core.validate_schema_document(report, "web-report-v10.schema.json", report["schema_version"])
    except core.CalculationError:
        core.require(
            "dimension_denominators" not in report.get("calculation_explainer", {}),
            "invalid_legacy_web_report",
            "Legacy web report compatibility permits only the missing denominator disclosure.",
        )
        normalized_report = deepcopy(report)
        normalized_report["calculation_explainer"]["dimension_denominators"] = deepcopy(dimension_denominators)
        core.validate_schema_document(normalized_report, "web-report-v10.schema.json", "Legacy web report shape")
    registered_by_type = {item["artifact_type"]: item for item in registered}
    input_by_type = {item["artifact_type"]: item for item in current_inputs}
    core.require(
        report["report_id"] == f"{state['evaluation_id']}-v8"
        and report["calculation_explainer"]["sha256"] == input_by_type["dimension_calculations"]["sha256"]
        and report["item_grade_index"]["sha256"] == input_by_type["item_assessments"]["sha256"]
        and report["structure_audit"]["sha256"] == input_by_type["structure_audit"]["sha256"],
        "replacement_bundle_identity_mismatch",
        "Registered web report is not bound to the current scoring artifacts.",
    )
    collection_types = {
        "index_records": "web_index_records",
        "source_subjects": "web_source_subjects",
        "density": "web_density",
        "correction_overlay": "correction_overlay",
    }
    collection_ids = [row["collection_id"] for row in projection["collections"]]
    core.require(
        len(collection_ids) == len(set(collection_ids)) and all(key in collection_types for key in collection_ids),
        "replacement_bundle_identity_mismatch",
        "Registered web projection has duplicate or unexpected collection identities.",
    )
    projection_parent = Path(registered_by_type["web_projection"]["path"]).parent
    core.require(
        all(
            (projection_parent / row["artifact_path"]).as_posix()
            == registered_by_type[collection_types[row["collection_id"]]]["path"]
            for row in projection["collections"]
        ),
        "replacement_bundle_identity_mismatch",
        "Registered web projection collection paths do not identify the registered collection files.",
    )
    collections = {
        row["collection_id"]: documents[collection_types[row["collection_id"]]]
        for row in projection["collections"]
    }
    core.require(projection["evaluation_id"] == state["evaluation_id"], "replacement_bundle_identity_mismatch", "Registered web projection evaluation identity differs from canonical state.")
    web_projection.validate_bundle(
        projection,
        collections,
        allow_legacy_display=True,
        canonical_scorecard=expected_scorecard,
        dimension_denominators=dimension_denominators,
    )
    provenance = {item["artifact_path"]: item["sha256"] for item in projection["provenance"]["source_artifacts"]}
    required_bindings = [*current_inputs, registered_by_path[portable_relative_path(output, state_path.parent)]]
    core.require(
        all(provenance.get(item["path"]) == item["sha256"] for item in required_bindings),
        "replacement_bundle_identity_mismatch",
        "Registered web projection is not bound to the current scoring and report artifacts.",
    )

    expected_files = {resolve_artifact_path(state_path, path).resolve() for path in expected_by_path}
    allowed_directories = {bundle_output.resolve(), *(path.parent for path in expected_files if path != output.resolve())}
    actual_entries = {Path(os.path.abspath(path)) for path in bundle_output.rglob("*")} if bundle_output.is_dir() else set()
    unmanaged = sorted(str(path) for path in actual_entries - expected_files - allowed_directories)
    core.require(not unmanaged, "unmanaged_output_collision", "The registered bundle directory contains unmanaged paths.", unmanaged)


def _write_web_bundle_transaction(
    state_path: Path,
    writes: Sequence[tuple[Path, bytes]],
    updated: dict[str, Any],
    *,
    bundle_output: Path,
) -> None:
    """Write all web outputs and restore exact prior bytes if any write fails."""
    state_before = state_path.read_bytes()
    snapshots = {path: path.read_bytes() if path.is_file() else None for path, _ in writes}
    written: list[Path] = []
    try:
        for path, payload in writes:
            _atomic_write(path, payload)
            written.append(path)
        save_state(state_path, updated)
    except Exception as original:
        rollback_errors = []
        for path in reversed(written):
            try:
                prior = snapshots[path]
                if prior is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write(path, prior)
            except Exception as exc:
                rollback_errors.append(f"{path}: {exc}")
        try:
            if not state_path.is_file() or state_path.read_bytes() != state_before:
                _atomic_write(state_path, state_before)
        except Exception as exc:
            rollback_errors.append(f"{state_path}: {exc}")
        for directory in sorted({path.parent for path, prior in snapshots.items() if prior is None}, key=lambda path: len(path.parts), reverse=True):
            if directory == bundle_output or bundle_output in directory.parents:
                try:
                    directory.rmdir()
                except OSError:
                    pass
        if rollback_errors:
            raise core.CalculationError("web_report_rollback_failed", "Web-report replacement failed and prior bytes could not be fully restored.", rollback_errors) from original
        raise


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
    result = item_grades.build_v8_assessments(
        base,
        calculation,
        structure,
        locator_documents=list(locator_documents),
        missing_documents=list(missing_documents),
    )
    core.validate_schema_document(result, "item-assessments-v7.schema.json", "Generated V8 item assessments")
    return result


def _scorecard(calculation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "dimension_id": item["dimension_id"],
            "weight": item["dimension_weight"],
            "dimension_percentage": item["dimension_percentage"],
            "weighted_contribution": item["weighted_contribution"],
            "formula_id": item["formula_id"],
            **({"semantic_uncertainty":deepcopy(item["semantic_uncertainty"])} if item.get("semantic_uncertainty") else {}),
            **({key: item[key] for key in ("substantive_selectivity_percentage", "density_fit_percentage", "substantive_points_out_of_10", "density_points_out_of_5")} if percentage_native() and item["dimension_id"] == "editorial_selectivity" else {}),
        }
        for item in calculation["dimensions"]
    ]


def _calculation_reference(record: Mapping[str, Any], calculation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": calculation["schema_version"],
        **({"execution_contract":deepcopy(calculation["execution_contract"])} if semantic_uncertainty() else {}),
        "artifact_path": record["path"],
        "sha256": record["sha256"],
        "calculation_sha256": calculation["calculation_sha256"],
        "rubric_version": calculation["rubric_version"],
        "calculation_profile": calculation["calculation_profile"],
    }


def _structure_reference(record: Mapping[str, Any]) -> dict[str, Any]:
    return {"schema_version": "structure-audit-v6", "artifact_path": record["path"], "sha256": record["sha256"]}


def _public_density(structure: Mapping[str, Any], calculation: Mapping[str, Any]) -> dict[str, Any]:
    selectivity = next(item for item in calculation["dimensions"] if item["dimension_id"] == "editorial_selectivity")
    component = next(item for item in selectivity["components"] if item["component_id"] == "density_fit")
    calculated_chapters = component["details"]["chapter_measurements"]
    chapter_fits = {
        item["chunk_id"]: {
            key: item[key]
            for key in ("path_fit_percentage", "occurrence_fit_percentage", "unit_fit_percentage")
        }
        for item in calculated_chapters
    }
    expected_chunks = {item["chunk_id"] for item in structure["density"]["chapter_measurements"]}
    core.require(
        len(chapter_fits) == len(calculated_chapters) and set(chapter_fits) == expected_chunks,
        "density_projection_chunk_mismatch",
        "Public density fit values must cover every and only canonical structure density chunk.",
    )
    density = deepcopy(structure["density"])
    if percentage_native():
        density.pop("fit_rating", None)
        detail = component["details"]
        density.update({key: detail[key] for key in ("total_weighted_percentage_numerator", "total_indexable_source_words")})
        density["chapter_measurements"] = deepcopy(calculated_chapters)
        if "scoring_override" in detail:
            density["scoring_override"] = deepcopy(detail["scoring_override"])
        for item in calculated_chapters:
            chapter_fits[item["chunk_id"]]["weighted_percentage_numerator"] = item["weighted_percentage_numerator"]
    historical_rounding = density.get("rounding")
    density["rounding"] = "none"
    density["current_calculation_profile"] = {
        "profile_id": calculation["calculation_profile"],
        "density_fit_precision": "full_precision",
        "dimension_percentage_precision": "full_precision",
        "weighted_contribution_precision": "full_precision",
        "overall_percentage_rounding": {
            key: calculation["final_rounding"][key]
            for key in ("mode", "quantum")
        },
    }
    if historical_rounding is not None:
        density["historical_rounding"] = {
            "value": historical_rounding,
            "source": "frozen_density_policy_and_structure",
            "applied_to_current_calculation": False,
        }
    return {
        **density,
        "density_fit_percentage": component["details"]["density_fit_percentage"] if percentage_native() else component["percentage"],
        **({"scoring_density_fit_percentage": component["percentage"]} if percentage_native() else {}),
        "chapter_fit_by_chunk": chapter_fits,
    }


PRESENTATION_DIMENSIONS = {
    "meaningful_coverage": (
        "Meaningful coverage",
        "Measures priority-weighted access to frozen source subjects; complete access receives full credit, partial access receives half credit, and missing access receives none.",
    ),
    "editorial_selectivity": (
        "Editorial selectivity",
        "Combines substantive locator selectivity and source-word-weighted density fit using the canonical component weights.",
    ),
    "conceptual_stance_fidelity": (
        "Conceptual and stance fidelity",
        "Measures source-grounded conceptual and stance fidelity across the audited heading-node denominator.",
    ),
    "page_reference_reliability": (
        "Page-reference reliability",
        "Combines binary locator keep precision and expected-treatment recall with the canonical harmonic mean and caps.",
    ),
    "findability_navigation": (
        "Findability and navigation",
        "Combines coverage-conditioned reader tasks, heading-access architecture, and cross-reference validity with the canonical weights and caps.",
    ),
    "mechanics_consistency": (
        "Mechanics and consistency",
        "Measures mechanical consistency across the audited heading-node denominator using the canonical status credits.",
    ),
}

PRESENTATION_COMPONENT_LABELS = {
    "priority_weighted_subject_access": "Priority-weighted subject access",
    "substantive_selectivity": "Substantive selectivity",
    "density_fit": "Density fit",
    "conceptual_stance_nodes": "Conceptual and stance node credit",
    "keep_precision": "Locator keep precision",
    "page_treatment_axis_diagnostic": "Page-treatment diagnostic",
    "complete_path_fit_axis_diagnostic": "Complete-path-fit diagnostic",
    "diagnostic_locator_credit_mean": "Diagnostic locator credit",
    "expected_treatment_recall": "Expected-treatment recall",
    "reliability_f1": "Reliability harmonic mean",
    "high_value_treatment_recall_safeguard": "High-value treatment recall",
    "coverage_conditioned_reader_tasks": "Coverage-conditioned reader-task credit",
    "heading_access_architecture": "Heading-access architecture",
    "cross_reference_validity": "Cross-reference validity",
    "mechanics_nodes": "Mechanics node credit",
}


def _presentation_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _presentation_display(value: Any, *, complement: bool = False, unavailable: str = "Not measured") -> str:
    decimal = _presentation_decimal(value)
    if decimal is None:
        return unavailable
    displayed = (ONE - decimal if complement else decimal) * Decimal(100)
    return f"{displayed.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}%"


def _presentation_score(value: Any) -> float | None:
    decimal = _presentation_decimal(value)
    return None if decimal is None else float(decimal * Decimal(100))


def _presentation_component(dimension: Mapping[str, Any], component_id: str) -> Mapping[str, Any]:
    matches = [item for item in dimension["components"] if item["component_id"] == component_id]
    core.require(len(matches) == 1, "presentation_component_mismatch", f"Expected one canonical {component_id} component.")
    return matches[0]


def _presentation_component_state(dimension: Mapping[str, Any], component_id: str) -> str:
    denominator = next((item for item in dimension["denominators"]["components"] if item["component_id"] == component_id), None)
    if dimension.get("semantic_uncertainty"):
        return "semantic_unresolved"
    if denominator is None:
        return "not_measured"
    if denominator["genuinely_inapplicable"]:
        return "not_applicable"
    if denominator["uninspectable"] and not denominator["measured"]:
        return "uninspectable"
    if denominator["not_measured"] and not denominator["measured"]:
        return "not_measured"
    return "not_measured"


def _presentation_unavailable_label(state: str) -> str:
    return {"not_applicable": "Not applicable", "uninspectable": "Uninspectable", "not_measured": "Not measured", "semantic_unresolved": "Semantically unresolved after inspection"}[state]


def _presentation_ratio_metric(metric_id: str, label: str, dimension: Mapping[str, Any], component_id: str) -> dict[str, Any]:
    component = _presentation_component(dimension, component_id)
    value = component["normalized_value"]
    return {
        "metric_id": metric_id,
        "label": label,
        "display_value": _presentation_display(value, unavailable=_presentation_unavailable_label(_presentation_component_state(dimension, component_id))),
        "value": value,
        "numerator": component["raw_numerator"],
        "denominator": component["raw_denominator"],
    }


def _presentation_calculation_basis(dimension: Mapping[str, Any]) -> list[dict[str, Any]]:
    lines = []
    for component in dimension["components"]:
        label = PRESENTATION_COMPONENT_LABELS.get(component["component_id"], component["component_id"].replace("_", " ").capitalize())
        value = component["normalized_value"]
        if value is None:
            state = _presentation_component_state(dimension, component["component_id"])
            lines.append({"equation": (f"{label}: {_presentation_unavailable_label(state)}" if state=="semantic_unresolved" else f"{label} is {state.replace(chr(95), chr(32))}"), "kind": "input", "number_scores": []})
            continue
        percentage = core.decimal_text(Decimal(str(value)) * Decimal(100))
        line = {
            "equation": f"{label} = {component['raw_numerator']} / {component['raw_denominator']} = {percentage}%",
            "kind": "input",
            "number_scores": [None, None, _presentation_score(value)],
            "score": _presentation_score(value),
        }
        if component["effective_weight"] in {"reported_diagnostic_only", "not_used_independently_in_dimension_arithmetic", "not_used_in_dimension_arithmetic", "cap_only"}:
            line["tooltip"] = "Reported diagnostic or safeguard only; excluded as an independent weighted score component."
        lines.append(line)

    if dimension["dimension_id"] == "page_reference_reliability":
        keep = _presentation_component(dimension, "keep_precision")["normalized_value"]
        recall = _presentation_component(dimension, "expected_treatment_recall")["normalized_value"]
        if keep is not None and recall is not None:
            keep_percentage = core.decimal_text(Decimal(keep) * Decimal(100))
            recall_percentage = core.decimal_text(Decimal(recall) * Decimal(100))
            base = dimension["pre_cap_percentage"]
            lines.append({
                "equation": f"Canonical harmonic mean = 2 * {keep_percentage}% * {recall_percentage}% / ({keep_percentage}% + {recall_percentage}%) = {base}%",
                "kind": "step",
                "number_scores": [None, float(Decimal(keep_percentage)), float(Decimal(recall_percentage)), float(Decimal(keep_percentage)), float(Decimal(recall_percentage)), float(Decimal(base))],
                "score": float(Decimal(base)),
            })
    elif dimension["dimension_id"] in {"editorial_selectivity", "findability_navigation"}:
        weighted = []
        for component in dimension["components"]:
            value = _presentation_decimal(component["normalized_value"])
            weight_text = component["effective_weight"]
            numerator, denominator = weight_text.split("/", 1) if "/" in weight_text else (weight_text, "1")
            weight = Decimal(numerator) / Decimal(denominator)
            if value is not None and weight:
                weighted.append((value * Decimal(100), weight))
        if weighted and dimension["pre_cap_percentage"] is not None:
            base = Decimal(str(dimension["pre_cap_percentage"]))
            equation = "Canonical weighted combination = " + " + ".join(
                f"{core.decimal_text(value)}% * {core.decimal_text(weight)}" for value, weight in weighted
            ) + f" = {core.decimal_text(base)}%"
            number_scores = [item for value, _ in weighted for item in (float(value), None)] + [float(base)]
            lines.append({"equation": equation, "kind": "step", "number_scores": number_scores, "score": float(base)})
    elif dimension["pre_cap_percentage"] is not None:
        value = Decimal(str(dimension["pre_cap_percentage"]))
        lines.append({"equation": f"Canonical pre-cap percentage = {core.decimal_text(value)}%", "kind": "step", "number_scores": [float(value)], "score": float(value)})

    applied_cap = dimension["applied_cap"]
    if applied_cap is not None and dimension["pre_cap_percentage"] is not None and dimension["dimension_percentage"] is not None:
        pre_cap = Decimal(str(dimension["pre_cap_percentage"]))
        ceiling = Decimal(str(applied_cap["maximum_percentage"]))
        final = Decimal(str(dimension["dimension_percentage"]))
        lines.append({
            "equation": (f"Applied cap ({core.decimal_text(ceiling)}% ceiling): {core.decimal_text(pre_cap)}% → {core.decimal_text(final)}%" if final < pre_cap else f"Non-binding triggered ceiling = {core.decimal_text(ceiling)}%; score remains {core.decimal_text(final)}%"),
            "kind": "step",
            "number_scores": [None, float(pre_cap), float(final)] if final < pre_cap else [None, float(final)],
            "score": float(final),
            "tooltip": core.canonical_json_text(next(row for row in dimension["cap_evaluations"] if row["cap_id"] == applied_cap["cap_id"])),
        })
    elif dimension["dimension_percentage"] is not None:
        final = Decimal(str(dimension["dimension_percentage"]))
        lines.append({
            "equation": f"No canonical cap reduced the {core.decimal_text(final)}% result",
            "kind": "step",
            "number_scores": [float(final)],
            "score": float(final),
        })
    return lines


def _presentation_summary(
    *,
    calculation: Mapping[str, Any],
    calculation_record: Mapping[str, Any],
    candidate: Mapping[str, Any],
    structure: Mapping[str, Any],
    missing_documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    dimensions = {item["dimension_id"]: item for item in calculation["dimensions"]}
    subject_rows = [row for document in missing_documents for row in document["subject_judgments"]]
    task_rows = [row for document in missing_documents for row in document["reader_task_results"]]
    treatment_rows = [row for document in missing_documents for row in document["treatment_judgments"]]
    coverage = {
        priority: {status: sum(row["priority"] == priority and row["coverage"] == status for row in subject_rows) for status in ("complete", "partial", "missing")}
        for priority in ("essential", "major", "optional")
    }

    optional_scored = {row["subject_id"]: row["scored"] for row in structure["scoring_context"].get("optional_subject_scoring", [])}
    measured_subjects = [
        row for row in subject_rows
        if row["coverage"] in core.COVERAGE_CREDIT and (row["priority"] != "optional" or optional_scored.get(row["subject_id"], True))
    ]
    complete_weight = sum((core.PRIORITY_CREDIT[row["priority"]] for row in measured_subjects if row["coverage"] == "complete"), ZERO)
    partial_weight = sum((core.PRIORITY_CREDIT[row["priority"]] for row in measured_subjects if row["coverage"] == "partial"), ZERO)
    missing_weight = sum((core.PRIORITY_CREDIT[row["priority"]] for row in measured_subjects if row["coverage"] == "missing"), ZERO)
    denominator_weight = complete_weight + partial_weight + missing_weight
    coverage_component = _presentation_component(dimensions["meaningful_coverage"], "priority_weighted_subject_access")
    core.require(
        Decimal(coverage_component["raw_numerator"]) == complete_weight + partial_weight * Decimal("0.5")
        and Decimal(coverage_component["raw_denominator"]) == denominator_weight,
        "presentation_metric_binding_mismatch",
        "Presentation coverage weights differ from the canonical calculation.",
    )
    essential_cap = next(item for item in dimensions["meaningful_coverage"]["cap_evaluations"] if item["cap_id"] == "coverage.essential_miss_rate")

    coverage_by_subject = {row["subject_id"]: row["coverage"] for row in subject_rows}
    eligible_tasks = [
        row for row in task_rows
        if all(coverage_by_subject.get(subject_id) in core.COVERAGE_CREDIT and coverage_by_subject[subject_id] != "missing" for subject_id in row["subject_ids"])
        and row["result"] in core.TASK_CREDIT
    ]
    task_component = _presentation_component(dimensions["findability_navigation"], "coverage_conditioned_reader_tasks")
    task_credit = sum((core.TASK_CREDIT[row["result"]] for row in eligible_tasks), ZERO)
    core.require(
        Decimal(task_component["raw_numerator"]) == task_credit
        and Decimal(task_component["raw_denominator"]) == len(eligible_tasks),
        "presentation_metric_binding_mismatch",
        "Presentation reader-task operands differ from the canonical calculation.",
    )
    strict_task_successes = sum(row["result"] == "succeeds" for row in eligible_tasks)
    strict_task_value = None if task_component["normalized_value"] is None else core.decimal_text(core.rate(strict_task_successes, len(eligible_tasks)))

    reliability = dimensions["page_reference_reliability"]["reliability_provenance"]
    metrics = [
        {
            "metric_id": "weighted_concept_access_partial_credit",
            "label": "Meaningful coverage",
            "display_value": _presentation_display(coverage_component["normalized_value"]),
            "value": coverage_component["normalized_value"],
            "complete_weight": core.decimal_text(complete_weight),
            "partial_weight": core.decimal_text(partial_weight),
            "denominator_weight": core.decimal_text(denominator_weight),
        },
        {
            "metric_id": "essential_concept_miss_rate",
            "label": "Essential subjects covered",
            "display_value": _presentation_display(essential_cap["observed"]["rate"], complement=True),
            "value": essential_cap["observed"]["rate"],
            "numerator": str(essential_cap["observed"]["missing"]),
            "denominator": str(essential_cap["observed"]["essential_denominator"]),
        },
        _presentation_ratio_metric("locator_recall", "Expected-treatment recall", dimensions["page_reference_reliability"], "expected_treatment_recall"),
        {
            "metric_id": "reader_task_strict_success",
            "label": "Coverage-conditioned research-question access",
            "display_value": _presentation_display(
                strict_task_value,
                unavailable=_presentation_unavailable_label(_presentation_component_state(dimensions["findability_navigation"], "coverage_conditioned_reader_tasks")),
            ),
            "value": strict_task_value,
            "partial_credit_value": task_component["normalized_value"],
            "numerator": str(strict_task_successes),
            "denominator": str(len(eligible_tasks)),
        },
        _presentation_ratio_metric("substantive_selectivity", "Substantive selectivity", dimensions["editorial_selectivity"], "substantive_selectivity"),
        {
            "metric_id": "strict_supported_locator_rate",
            "label": "Locator keep precision",
            "display_value": _presentation_display(reliability["keep_precision"]),
            "value": reliability["keep_precision"],
            "numerator": str(reliability["keep_precision_numerator"]),
            "denominator": str(reliability["keep_precision_denominator"]),
        },
        _presentation_ratio_metric("conceptual_stance_fidelity", "Conceptual and stance fidelity", dimensions["conceptual_stance_fidelity"], "conceptual_stance_nodes"),
        _presentation_ratio_metric("valid_entry_precision_at_least_partial", "Reliability F1", dimensions["page_reference_reliability"], "reliability_f1"),
        _presentation_ratio_metric("density_fit", "Density fit", dimensions["editorial_selectivity"], "density_fit"),
        _presentation_ratio_metric("heading_access_architecture", "Heading-access architecture", dimensions["findability_navigation"], "heading_access_architecture"),
        _presentation_ratio_metric("cross_reference_validity", "Cross-reference validity", dimensions["findability_navigation"], "cross_reference_validity"),
        _presentation_ratio_metric("mechanics_consistency", "Mechanics and consistency", dimensions["mechanics_consistency"], "mechanics_nodes"),
    ]
    return {
        "schema_version": "subject-index-presentation-summary-v1",
        "provenance": {
            "evaluation_id": calculation["evaluation_id"],
            "web_report_sha256": calculation_record["sha256"],
        },
        "coverage_by_priority": coverage,
        "scope": {
            "displayed_locators": sum(len(row["locator_displays"]) for row in candidate["records"]),
            "expected_treatments": len(treatment_rows),
        },
        "metrics": metrics,
        "dimensions": [
            {
                "dimension_id": dimension_id,
                "label": PRESENTATION_DIMENSIONS[dimension_id][0],
                "rationale": PRESENTATION_DIMENSIONS[dimension_id][1],
                "calculation_basis": _presentation_calculation_basis(dimensions[dimension_id]),
            }
            for dimension_id in PRESENTATION_DIMENSIONS
        ],
    }


def _destination_gate_evidence(structure, calculation, locator_documents, inventory, *, source_binding_valid=True):
    """Read finalized audit axes; never infer total wrongness from severity or prose."""
    reliability = reliability_dimension(dict(calculation))["reliability_provenance"]
    expected = {row["locator_id"] for row in reliability.get("locator_utility_assignments", [])}
    audited = {row["locator_id"]: row for document in locator_documents for row in document["judgments"]}
    scopes = validate_uncertainty_gate_scopes(structure)
    uncertain_locators, uncertain_references, unknown_ids = set(), set(), set()
    blockers = []
    wrong_locators, broken_references = [], []

    def block(code, ids, reason):
        blockers.append({"blocker_id": code, "affected_item_ids": sorted(set(ids)), "reason": reason})

    references = {row["reference_id"]: row for row in inventory.get("cross_references", [])}
    paths = {row["path_id"] for row in inventory.get("paths", [])}
    delivered = set(structure["candidate_denominator"]["cross_reference_ids"])
    locator_paths = {row["path_id"] for identity, row in audited.items() if identity in expected}
    for record in structure.get("uncertainties", []):
        identity = record["uncertainty_id"]
        scope = scopes.get(identity)
        if scope is None or scope["scope"] == "unknown":
            unknown_ids.update(record["affected_item_ids"])
            block("GATE-ASSESSMENT-UNCERTAINTY-SCOPE", record["affected_item_ids"], f"Uncertainty {identity} lacks confirmed gate applicability; its contextual paths must not be treated as established path-wide locator uncertainty.")
            continue
        targets = set(scope["target_ids"])
        kind = scope["scope"]
        population = {"locator_support": expected, "path_locator_support": locator_paths,
                      "cross_reference_destination": delivered & set(references)}.get(kind)
        if population is not None and targets - population:
            block("GATE-ASSESSMENT-UNCERTAINTY-TARGET", targets - population, f"Uncertainty {identity} cites scope targets absent from the selected candidate evidence.")
        if kind == "locator_support":
            uncertain_locators.update(targets)
        elif kind == "path_locator_support":
            uncertain_locators.update(row["locator_id"] for row in audited.values() if row["path_id"] in targets)
        elif kind == "cross_reference_destination":
            uncertain_references.update(targets & delivered & set(references))
        # benchmark_access and measurement_provenance do not assert uncertain
        # destination support; independent source/audit safeguards still apply.
    for reference_id in sorted(uncertain_references):
        block("GATE-ASSESSMENT-REFERENCE-UNCERTAIN", [reference_id], "Explicitly scoped uncertainty affects this delivered reference destination.")

    if not is_v10() and any(row["defect_kind"] == "scope_failure" for row in structure["defects"]):
        block("GATE-ASSESSMENT-SOURCE", [], "Wrong-source evidence cannot establish candidate destination failures.")
        return [], [], {"status": "indeterminate", "blockers": blockers}
    if is_v10() and not source_binding_valid:
        block("GATE-ASSESSMENT-SOURCE", expected | locator_paths, "VALIDITY-SOURCE-SPAN: source-dependent judgments cannot be established from mismatched source evidence.")
    if expected - set(audited):
        block("GATE-ASSESSMENT-LOCATOR-EVIDENCE", expected - set(audited), "Finalized locator audit evidence is missing.")
    for locator_id in sorted(expected & set(audited)):
        if is_v10() and not source_binding_valid:
            continue
        row = audited[locator_id]
        if unknown_ids & {locator_id, row["path_id"]}:
            continue  # Already disclosed as an applicability gap, not a locator judgment.
        semantic = row.get('axis_resolution') if semantic_uncertainty() else None
        if semantic:
            unknown_axes=[axis for axis in ('treatment','complete_path_fit','keep','judgment_subtype') if semantic.get(axis)=='unresolved']
            dependent=set(semantic.get('dependent_reference_ids',[]))
            if dependent-set(references):
                block('GATE-ASSESSMENT-UNCERTAINTY-TARGET',dependent-set(references),'Semantic dependency cites an undelivered reference.')
            blockers.append({'blocker_id':'GATE-ASSESSMENT-LOCATOR-UNCERTAIN','affected_item_ids':sorted({locator_id,row['path_id']} | (dependent & set(references))),
                             'semantic_unknown_axes':unknown_axes,'dependent_reference_ids':sorted(dependent & set(references)),
                             'reason':'Semantically unresolved after inspection; only predicates needing an unresolved axis are withheld.'})
            if set(unknown_axes) & {'keep','complete_path_fit'}:continue
        if row["judgment"] == "uninspectable" or (not semantic and row.get("confidence") not in {"high", "medium"}) or locator_id in uncertain_locators:
            block("GATE-ASSESSMENT-LOCATOR-UNCERTAIN", [locator_id], "Locator support is uncertain or uninspectable; no candidate-quality gate is inferred.")
            continue
        if row["judgment"] != "unsupported" or row["complete_path_fit"] != "no_fit":
            continue
        if row["source_scope_status"] not in {"indexable", "excluded"} or row["treatment_class"] == "unavailable" or not row.get("evidence_ids") or not row.get("fit_rationale", "").strip():
            block("GATE-ASSESSMENT-LOCATOR-EVIDENCE", [locator_id], "Zero-fit finding lacks inspectable, source-linked audit evidence.")
            continue
        wrong_locators.append({key: deepcopy(row[key]) for key in (
            "locator_id", "path_id", "complete_heading_path", "document_page", "source_page_label",
            "judgment", "complete_path_fit", "treatment_class", "source_scope_status", "confidence", "evidence_ids")})

    for row in sorted(structure.get("cross_reference_judgments", []), key=lambda row: row["reference_id"]):
        reference_id = row["reference_id"]
        if reference_id in uncertain_references or reference_id in unknown_ids:
            continue  # The scope/uncertainty blocker already names this reference.
        resolution = row.get("target_resolution")
        target = references.get(reference_id)
        if reference_id not in delivered or target is None:
            block("GATE-ASSESSMENT-REFERENCE-IDENTITY", [reference_id], "Reference exception is not bound to the delivered candidate inventory.")
        elif (row["judgment"] in {"uninspectable", "not_measured"} or row["confidence"] not in {"high", "medium"}
              or resolution is None or resolution["status"] == "uncertain"):
            block("GATE-ASSESSMENT-REFERENCE-RESOLUTION", [reference_id], "Delivered reference exception lacks confirmed destination resolution; publication readiness is indeterminate.")
        elif (resolution["reference_type"] != target["reference_type"] or resolution["target_display"] != target["target_display"]
              or not set(resolution["resolved_path_ids"]) <= paths or not resolution["evidence_ids"] or not resolution["rationale"].strip()):
            block("GATE-ASSESSMENT-REFERENCE-EVIDENCE", [reference_id], "Destination resolution does not match the delivered reference or preserved evidence.")
        elif resolution["status"] == "no_valid_destination":
            if row["judgment"] != "unsupported" or resolution["resolved_path_ids"]:
                block("GATE-ASSESSMENT-REFERENCE-CONTRADICTION", [reference_id], "Absent-destination claim contradicts partial support or a resolved destination.")
            else:
                broken_references.append({"reference_id": reference_id, "judgment": row["judgment"],
                    "reference_type": resolution["reference_type"], "target_display": resolution["target_display"],
                    "target_resolution": resolution["status"], "resolved_path_ids": [],
                    "confidence": row["confidence"], "evidence_ids": sorted(set(row["evidence_ids"]) | set(resolution["evidence_ids"]))})
        elif not resolution["resolved_path_ids"]:
            block("GATE-ASSESSMENT-REFERENCE-EVIDENCE", [reference_id], "An identifiable destination requires its delivered path ID.")
    return wrong_locators, broken_references, {"status": "indeterminate" if blockers else "sufficient", "blockers": blockers}


def _critical_gate_outcomes(policy, structure, calculation, *, destination_evidence=None):
    if is_v10():
        from v10_consequences import gate_outcomes
        return gate_outcomes(policy, structure, calculation, destination_evidence, _legacy_critical_gate_outcomes)
    return _legacy_critical_gate_outcomes(policy, structure, calculation, destination_evidence=destination_evidence)


def _legacy_critical_gate_outcomes(
    policy: Mapping[str, Any], structure: Mapping[str, Any], calculation: Mapping[str, Any],
    *, destination_evidence: tuple | None = None, bad_locator_evidence=None,
) -> list[dict[str, Any]]:
    direct_locators, direct_references, _ = destination_evidence or ([], [], {})
    owned_locators = {row["locator_id"] for row in direct_locators}
    owned_references = {row["reference_id"] for row in direct_references}
    defects = structure["defects"]
    references = set(structure["candidate_denominator"]["cross_reference_ids"])
    reliability = reliability_dimension(dict(calculation))["reliability_provenance"]
    locators = [dict(row, path_id=reliability.get("locator_path_bindings", {}).get(row["locator_id"], row.get("path_id"))) for row in reliability.get("locator_utility_assignments", [])]
    blocked_ids = {item for blocker in (destination_evidence[2]["blockers"] if destination_evidence else []) for item in blocker["affected_item_ids"]}
    references -= blocked_ids
    locators = [row for row in locators if not {row["locator_id"], row.get("path_id")} & blocked_ids]
    def bad(item):
        return (bad_locator_evidence or core.delivered_bad_locators)(item, locators)
    def major(item):
        return not set(item["affected_item_ids"]) & blocked_ids and core.material_consequence(item) and not core.partial_fit_only(item, locators)
    def delivered_reference(item):
        return bool(references & set(item["affected_item_ids"]))
    predicates = {
        "GATE-SCOPE-LOCATOR": lambda item: major(item) and bool(bad(item)) and item["defect_kind"] in {"fabricated_locator", "nonexistent_locator", "out_of_scope_locator"},
        "GATE-CENTRAL-OMISSION": lambda item: major(item) and item["defect_kind"] == "central_omission" and (item["severity"] == "critical" or item.get("high_priority_access_destroyed")),
        "GATE-STANCE": lambda item: major(item) and item["retrieval_consequence"] == "misleads" and item["defect_kind"] in {"stance_reversal", "misleading_relationship"},
        "GATE-COMPOUND": lambda item: major(item) and item["code"] == "CMP" and bool(bad(item)),
        "GATE-SEE-SUBSTITUTION": lambda item: major(item) and item["retrieval_consequence"] == "blocks" and item["defect_kind"] == "substitutive_see" and (delivered_reference(item) or any(x.startswith("NODE-") for x in item["affected_item_ids"]) or item.get("high_priority_access_destroyed")),
        "GATE-CROSS-REFERENCE": lambda item: major(item) and item["code"] == "XRF" and item["defect_kind"] in {"circular_or_chained_reference", "unsupported_reference"} and delivered_reference(item),
        # Stance and compound failures have specific gates; no generic duplicate.
        "GATE-GROUNDING": lambda item: major(item) and bool(bad(item)) and item["code"] not in {"STA", "CON", "CMP"} and item["defect_kind"] not in {"stance_reversal", "misleading_relationship", "fabricated_locator", "nonexistent_locator", "out_of_scope_locator"},
        "GATE-STRUCTURE": lambda item: major(item) and item["severity"] == "critical" and item["defect_kind"] in {"representation_corruption", "mechanical_invariant"} and item["dimension_owner"] == "mechanics_consistency",
    }
    aggregate_candidates = {
        "GATE-CLUTTER": [row for row in defects if row["defect_kind"] == "clutter_pattern"],
        "GATE-CROSS-REFERENCE": [row for row in defects if row["code"] == "XRF" and row["defect_kind"] in {"circular_or_chained_reference", "unsupported_reference"} and delivered_reference(row)],
        "GATE-SYSTEMIC-UNSUPPORTED": [row for row in defects if row["dimension_owner"] == "page_reference_reliability" and bad(row)],
    }
    results = []
    for gate in policy["critical_gates"]:
        gate_id = gate["gate_id"]
        direct = direct_locators if gate_id == "GATE-WRONG-LOCATOR" else direct_references if gate_id == "GATE-BROKEN-REFERENCE" else []
        def separately_owned(row):
            # One atomic wrong destination is owned by its direct gate. Retain
            # distinct material findings and patterns with other affected items.
            if set(row["affected_item_ids"]) <= owned_locators | owned_references:
                return True
            locator_ids = {item["locator_id"] for item in bad(row)}
            if gate_id in {"GATE-SCOPE-LOCATOR", "GATE-COMPOUND", "GATE-GROUNDING", "GATE-SYSTEMIC-UNSUPPORTED"}:
                return bool(locator_ids) and locator_ids <= owned_locators
            if gate_id in {"GATE-CROSS-REFERENCE", "GATE-SEE-SUBSTITUTION"}:
                return bool(row["affected_item_ids"]) and set(row["affected_item_ids"]) <= owned_references
            return False
        matching = [row for row in defects if predicates.get(gate_id, lambda _: False)(row) and not separately_owned(row)]
        groups = core.systemic_defect_groups([row for row in aggregate_candidates.get(gate_id, [])
            if not core.has_partial_fit(row, locators) and not separately_owned(row)
            and not blocked_ids & set(row["affected_item_ids"])
            and not (owned_locators & {item["locator_id"] for item in bad(row)} or owned_references & set(row["affected_item_ids"]))])
        group_ids = {item for group in groups for item in group["defect_ids"]}
        matching = [row for row in defects if row in matching or row["defect_id"] in group_ids]
        triggered = bool(matching or direct)
        attempt = structure.get("scoring_context", {}).get("candidate_attempt", {})
        candidate_failure = gate_id == "GATE-STRUCTURE" and attempt.get("status") in {"empty", "structurally_incomplete", "unparseable"}
        triggered = triggered or candidate_failure
        threshold = ("10 distinct items, >=5% of one denominator, >=2 sections and >=25% source/structural spread" if groups or gate_id in {"GATE-CLUTTER", "GATE-SYSTEMIC-UNSUPPORTED"} else gate["description"])
        affected = {item for row in matching for item in row["affected_item_ids"]}
        # Preserve original defect provenance, but do not count direct failures
        # again in another gate's affected IDs or qualifying locator rows.
        affected -= owned_locators | owned_references
        qualifying = {locator["locator_id"]: deepcopy(locator) for row in matching for locator in bad(row) if locator["locator_id"] not in owned_locators}
        results.append({**deepcopy(gate), "triggered": triggered,
                        "defect_ids": sorted(row["defect_id"] for row in matching),
                        "affected_evidence_ids": sorted(affected | set(attempt.get("evidence_ids", []) if candidate_failure else []) | {row.get("locator_id", row.get("reference_id")) for row in direct}),
                        "threshold": threshold, "systemic_groups": groups,
                        "consequence_evidence": [deepcopy(row) for row in matching],
                        "direct_destination_evidence": deepcopy(direct),
                        "qualifying_locator_evidence": [qualifying[key] for key in sorted(qualifying)],
                        "threshold_reason": ("Confirmed delivered destination failure from finalized audit evidence; one item is sufficient, independent of severity, defect records, rates, or spread." if direct else "Frozen systemic threshold met: " + core.canonical_json_text(groups) if groups else "Qualifying material consequence: " + core.canonical_json_text(matching) if matching else "Candidate output cannot function as an index: " + core.canonical_json_text(attempt) if candidate_failure else "No qualifying evidence crosses this threshold.")})
    return results


def _evaluation_validity(policy, structure, calculation):
    reliability = reliability_dimension(dict(calculation))["reliability_provenance"]
    denominator = reliability["original_locator_denominator"]
    count = reliability["uninspectable_locator_count"]
    value = core.rate(count, denominator)
    tolerance = Decimal(str(policy["audit_design"]["uninspectable_locator_rate_tolerance"]))
    blockers = []
    if value > tolerance:
        blockers.append({"blocker_id": "VALIDITY-UNINSPECTABLE", "outcome": "indeterminate", "count": count, "denominator": denominator, "rate": core.decimal_text(value), "threshold": core.decimal_text(tolerance), "reason": "Uninspectability exceeds frozen audit tolerance; index quality is undetermined."})
    # V10 source identity/span mismatches are rejected by registered-input and
    # study preflight. Candidate scope defects cannot establish invalid evidence.
    wrong_span = [] if is_v10() else [row for row in structure["defects"] if row["defect_kind"] == "scope_failure"]
    if wrong_span:
        blockers.append({"blocker_id": "VALIDITY-SOURCE-SPAN", "outcome": "invalid", "evidence": deepcopy(wrong_span), "reason": "Evaluated source span is wrong; this audit cannot establish index quality."})
    if not structure["full_scope_attestation"]["complete"]:
        blockers.append({"blocker_id": "VALIDITY-ATTESTATION", "outcome": "indeterminate", "reason": "Incomplete audit attestation does not establish an index defect."})
    return {"status": "invalid" if wrong_span else "indeterminate" if blockers else "valid", "blockers": blockers, "used_as_publication_gate": False}


def _review_signals(structure, calculation):
    reliability = reliability_dimension(dict(calculation))["reliability_provenance"]
    partial = [row["locator_id"] for row in reliability.get("locator_utility_assignments", []) if row["fit_category"] == "material_partial_fit"]
    missing = structure.get("scoring_context", {}).get("cross_reference_applicability", {}).get("warranted_reference_obligation_ids", [])
    supplemental = sorted(set(missing) | {item for row in structure["defects"] if row["dimension_owner"] == "findability_navigation" and row["code"] in {"HED", "SUB", "XRF"} and not row.get("high_priority_access_destroyed") for item in row["affected_item_ids"] if item.startswith(("TASK-", "SUBJ-", "TREAT-"))})
    deep = [row["node_id"] for row in structure["candidate_denominator"]["nodes"] if len(row["heading_path"]) >= 3]
    return [{"signal_id": name, "color": "yellow", "affected_evidence_ids": sorted(ids), "count": len(ids), "reason": reason, "individually_caps_or_gates": False}
            for name, ids, reason in [
                ("REVIEW-PARTIAL-FIT", partial, "Partial fits retain ordinary diagnostic and rating consequences; no cap or gate."),
                ("REVIEW-MISSING-SUPPLEMENTAL-ROUTE", supplemental, "Supplemental route omissions remain scored; no individual cap or gate."),
                ("REVIEW-HEADING-DEPTH", deep, "Third-level headings prompt review only.")]
            if ids]


def _projection_metadata(
    *,
    policy: Mapping[str, Any],
    calculation: Mapping[str, Any],
    calculation_record: Mapping[str, Any],
    structure: Mapping[str, Any],
    structure_record: Mapping[str, Any],
    candidate_label: str,
    locator_documents: Sequence[Mapping[str, Any]],
    inventory: Mapping[str, Any],
    candidate_access_review=None,
) -> dict[str, Any]:
    destination_evidence = _destination_gate_evidence(structure, calculation, locator_documents, inventory)
    if candidate_access_review and candidate_access_review['blockers']:
        destination_evidence[2]['blockers'].extend(deepcopy(candidate_access_review['blockers']))
        destination_evidence[2]['status'] = 'indeterminate'
    gates = _critical_gate_outcomes(policy, structure, calculation, destination_evidence=destination_evidence)
    limitations = [item["summary"] for item in structure["uncertainties"]]
    metadata = {
        "schema_version": runtime_identity("subject-index-v8-projection-metadata-v2"),
        "candidate_label": candidate_label,
        "inclusion_policy": ("Preserved V8.2 source scope with independently reviewed V10 benchmark access amendment." if is_v10() else "Frozen V8.2 source scope and candidate-blind benchmark, preserved under V9." if percentage_native() else "Frozen current-V8 source scope and candidate-blind benchmark."),
        "uncertainty_policy": policy["audit_design"]["uncertainty_policy"],
        "critical_gates": gates,
        "gate_assessment": destination_evidence[2],
        "evaluation_validity": _evaluation_validity(policy, structure, calculation),
        "review_signals": _review_signals(structure, calculation),
        "report_id": f"{calculation['evaluation_id']}-{'v10' if is_v10() else 'v9' if percentage_native() else 'v8'}",
        "headline": "Subject-index evaluation",
        "summary": ("V10 percentage evaluation from validated registered artifacts and independently reviewed benchmark access proof." if is_v10() else "V9 percentage evaluation from validated registered artifacts and preserved source proof." if percentage_native() else "Current-V8 source-grounded evaluation from validated registered artifacts."),
        "interpretation": ("Semantically unresolved after inspection; no overall percentage is established." if semantic_uncertainty() and calculation["overall_percentage"] is None else f"The validated {'V10' if is_v10() else 'V9' if percentage_native() else 'V8'} calculation produced an overall percentage of {calculation['overall_percentage']}%."),
        "defect_counts": dict(sorted(Counter(item["severity"] for item in structure["defects"]).items())),
        "strengths": deepcopy(structure["strengths"]),
        "defects": deepcopy(structure["defects"]),
        "examples": [],
        "limitations": limitations,
        "canonical_calculation": _calculation_reference(calculation_record, calculation),
        "canonical_structure_audit": _structure_reference(structure_record),
        "canonical_heading_access_source": {
            "role": "heading_access_causal_source",
            **_structure_reference(structure_record),
        },
    }
    metadata["projection_metadata_sha256"] = core.canonical_hash(metadata, "projection_metadata_sha256")
    core.validate_schema_document(metadata, "v8-projection-metadata-v2.schema.json", "Generated V8 projection metadata")
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
        "schema_version": runtime_identity("subject-index-evaluation-result-v12"),
        "evaluation_id": calculation["evaluation_id"],
        "candidate": {"label": metadata["candidate_label"], "sha256": identity["candidate_sha256"]},
        "provenance": {
            "source_sha256": identity["source_sha256"],
            "judgment_policy_sha256": identity["policy_sha256"],
            "benchmark_sha256": identity["benchmark_sha256"],
            "rubric_version": calculation["rubric_version"],
            "dimension_calculation_profile": calculation["calculation_profile"],
        },
        "audit_scope": {"mode": calculation["audit_mode"], "complete": (calculation["audit_mode"] == "full" and not any(c["not_measured"] for d in calculation["dimensions"] for c in d["denominators"]["components"])) if semantic_uncertainty() else calculation["status"] == "scored"},
        "dimension_calculations": _calculation_reference(calculation_record, calculation),
        "scorecard": _scorecard(calculation),
        "overall_percentage": calculation["overall_percentage"],
        "interpretation": metadata["interpretation"],
        "metrics": {"keep_precision": {key: reliability[key] for key in ("keep_precision_numerator", "keep_precision_denominator", "keep_precision", "treatment_recall", "reliability_f1")}},
        "item_assessments": {"schema_version": items["schema_version"], "artifact_path": items_record["path"], "sha256": items_record["sha256"], "grading_policy": items["grading_policy"], "summary": deepcopy(items["summary"])},
        "heading_access_causal_provenance": deepcopy(items["heading_access_causal_provenance"]),
        "structure_audit": _structure_reference(structure_record),
        "projection_metadata": {"schema_version": metadata["schema_version"], "artifact_path": metadata_record["path"], "sha256": metadata_record["sha256"], "projection_metadata_sha256": metadata["projection_metadata_sha256"]},
        "critical_gates": deepcopy(metadata["critical_gates"]),
        "gate_assessment": deepcopy(metadata["gate_assessment"]),
        "evaluation_validity": deepcopy(metadata["evaluation_validity"]),
        "review_signals": deepcopy(metadata["review_signals"]),
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
    if is_v10():
        from v10_consequences import outcome_fields
        result.update(outcome_fields(result))
    core.validate_schema_document(result, "evaluation-result-v12.schema.json", "Generated V8 evaluation result")
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
    candidate: Mapping[str, Any],
    missing_documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    calculation_ref = _calculation_reference(calculation_record, calculation)
    structure_ref = _structure_reference(structure_record)
    precision = deepcopy(result["metrics"]["keep_precision"])
    report = {
        "schema_version": runtime_identity("subject-index-web-report-v10"),
        "report_id": metadata["report_id"],
        "headline": metadata["headline"],
        "summary": metadata["summary"],
        "grade": {"score": calculation["overall_percentage"], "maximum": 100, "label": _grade_label(calculation["overall_percentage"])},
        "scorecard": _scorecard(calculation),
        "calculation_explainer": {
            **calculation_ref,
            "item_grades_used": False,
            "gates_used": False,
            "dimension_denominators": web_projection.dimension_denominator_disclosures(calculation),
        },
        "presentation_summary": _presentation_summary(
            calculation=calculation,
            calculation_record=calculation_record,
            candidate=candidate,
            structure=structure,
            missing_documents=missing_documents,
        ),
        "precision_diagnostics": precision,
        "structure_audit": {**deepcopy(calculation["structure_audit"]), **structure_ref},
        "key_metrics": [{"metric_id": key, "value": value} for key, value in precision.items()],
        "density": _public_density(structure, calculation),
        "gate_status": {"critical_gates": deepcopy(result["critical_gates"]), "outcomes_sha256": core.canonical_hash({"critical_gates": result["critical_gates"]}), "used_in_score_arithmetic": False},
        "strengths": deepcopy(metadata["strengths"]),
        "defects": deepcopy(metadata["defects"]),
        "examples": deepcopy(metadata["examples"]),
        "item_grade_index": {"schema_version": items["schema_version"], "artifact_path": items_record["path"], "sha256": items_record["sha256"], "grading_policy": items["grading_policy"], "summary": deepcopy(items["summary"]), "color_legend": deepcopy(items["color_legend"]), "interaction": {"color_source": "grade.color_token", "popover_source": "popover", "not_measured_behavior": "neutral_not_failure"}},
        "locator_explanations": [web_projection.public_locator_explanation(item) for item in items["locator_assessments"]],
        "heading_access_causal_provenance": deepcopy(items["heading_access_causal_provenance"]),
        "score_views": {"primary_view_id": "canonical_as_delivered", "adjustment_status": "none", "views": [{"view_id": "canonical_as_delivered", "label": "Canonical as delivered", "view_kind": "observed", "score": calculation["overall_percentage"], "maximum": 100, "calculation": calculation_ref, "structure_audit": structure_ref, "causal_attribution": "primary_observed_result", "provenance_artifacts": []}]},
        "evaluation_validity": deepcopy(result["evaluation_validity"]),
        "gate_assessment": deepcopy(result["gate_assessment"]),
        "review_signals": deepcopy(result["review_signals"]),
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
        "disclosures": ["Item grades are diagnostic and do not reconstruct the six-dimension score.", "Critical gates are reported separately from score arithmetic.", web_projection.COMPATIBILITY_ALIAS_DISCLOSURE],
        "limitations": deepcopy(result["limitations"]),
        "evidence_index": {"calculation": calculation_ref, "structure_audit": structure_ref, "item_assessments": {"artifact_path": items_record["path"], "sha256": items_record["sha256"]}},
    }
    if is_v10():
        report.update({key: deepcopy(result[key]) for key in ("method_readiness", "authoritative_evaluation", "human_release_decision")})
    core.validate_schema_document(report, "web-report-v10.schema.json", "Generated V8 web report")
    return report


def _validate_structure_inventory(structure: Mapping[str, Any], inventory: Mapping[str, Any]) -> None:
    denominator = structure["candidate_denominator"]
    nodes = [{key: item[key] for key in ("node_id", "heading_path", "role")} for item in inventory["heading_nodes"]]
    references = [item["reference_id"] for item in inventory["cross_references"]]
    path_ids = [item["path_id"] for item in inventory["paths"] if item["locator_ids"]]
    distinct_heading_paths = {tuple(item["heading_path"]) for item in inventory["paths"]}
    core.require(denominator["nodes"] == nodes, "structure_candidate_denominator_mismatch", "Structure node denominator differs from the registered item inventory.")
    for values, field, count_field, hash_field in (
        (references, "cross_reference_ids", "cross_reference_count", "cross_reference_id_set_sha256"),
        (path_ids, "locator_bearing_path_ids", "locator_bearing_path_count", "locator_bearing_path_id_set_sha256"),
    ):
        core.require(denominator[field] == values and denominator[count_field] == len(values) and denominator[hash_field] == id_set_hash(values), "structure_candidate_denominator_mismatch", f"Structure {field} differs from the registered item inventory.")
    core.require(denominator["node_count"] == len(nodes) and denominator["node_id_set_sha256"] == id_set_hash([item["node_id"] for item in nodes]), "structure_candidate_denominator_mismatch", "Structure node count or hash differs from the registered item inventory.")
    metrics = structure["metrics"]
    core.require(metrics["total_paths"] == len(distinct_heading_paths) and metrics["total_nodes"] == len(nodes) and metrics["expanded_locators"] == len(inventory["locators"]), "structure_candidate_metric_mismatch", "Structure metrics differ from the registered item inventory.")


def command_register_structure(args: argparse.Namespace) -> None:
    command = "register-structure-audit"
    state_path = Path(args.state).resolve()
    try:
        with evaluation_mutation_lock(state_path):
            state, warnings = _transition_state(state_path, "structure_audit")
            _, candidate_record, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="candidate-index-v2", schema_name="candidate-index-v2.schema.json")[0]
            inventory, inventory_record, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="subject-index-item-inventory-v2", schema_name="item-inventory-v2.schema.json")[0]
            locator_entries = _registered_documents(state, state_path, stage="locator_audit", schema_version="locator-audit-v2", schema_name="locator-audit-v2.schema.json", many=True)
            missing_entries = _registered_documents(state, state_path, stage="missing_access_audit", schema_version="missing-access-audit-v1", schema_name="missing-access-audit.schema.json", many=True)
            structure_path = Path(args.input).resolve()
            core.require(structure_path.is_file(), "input_not_found", f"Structure audit does not exist: {structure_path}")
            relative = portable_relative_path(structure_path, state_path.parent)
            core.require(not any(item.get("path") == relative for item in state["artifacts"]), "registered_output_collision", "Structure audit path is already registered.", relative)
            structure = core.load_json(structure_path, "Structure audit")
            core.validate_schema_document(structure, "structure-audit-v6.schema.json", "Structure audit")
            validate_structure_audit_semantics(structure)
            validate_heading_access_provenance(
                structure,
                (item[0] for item in locator_entries),
                (item[0] for item in missing_entries),
            )
            core.require(structure["evaluation_id"] == state["evaluation_id"], "evaluation_identity_mismatch", "Structure audit evaluation_id differs from canonical state.")
            core.require(structure["candidate_sha256"] == state["candidate"]["candidate_sha256"] == inventory["candidate_sha256"], "candidate_identity_mismatch", "Structure audit candidate identity differs from registered candidate artifacts.")
            core.require(structure["audit_mode"] == state["configuration"]["audit_mode"], "audit_mode_identity_mismatch", "Structure audit mode differs from canonical state.")
            core.require(candidate_record["sha256"] == state["candidate"]["normalized_sha256"] and inventory_record["path"] == state["candidate"]["item_inventory_path"], "candidate_identity_mismatch", "Canonical candidate artifact binding is inconsistent.")
            _validate_structure_inventory(structure, inventory)
            if is_v10():
                from v10_candidate_access import bound_review
                benchmark, _ = study_comparison.registered_document(state, state_path, 'benchmark_freeze', 'source-subject-benchmark-v2')
                lock = study_comparison.load_study_binding(state, state_path)
                bound_review(state, state_path, benchmark, lock, structure_path=structure_path)
            payload = structure_path.read_bytes()
            stamp = now()
            record = _artifact_record(state_path.parent, structure_path, payload, stage="structure_audit", artifact_type="structure_audit", schema_version="structure-audit-v6", stamp=stamp, input_sha256=(candidate_record["sha256"], inventory_record["sha256"]))
            updated = _add_records_and_complete(state, state_path, "structure_audit", [record], "Validated and registered the native V8 structure audit atomically.")
            study_comparison.preflight_state(updated, state_path, require_density=True)
            save_state(state_path, updated)
        core.emit({"command": command, "ok": True, "evaluation_id": state["evaluation_id"], "artifacts_registered": [record["path"]], "artifacts_written": [str(state_path)], "next_actions": [next_stage(updated)], "warnings": warnings})
    except (OSError, core.CalculationError, StructureAuditError, HeadingAccessProvenanceError, ValueError) as exc:
        if isinstance(exc, (core.CalculationError, StructureAuditError, HeadingAccessProvenanceError)):
            error = {"code": exc.code, "message": exc.message, "details": exc.details}
        else:
            error = {"code": "structure_registration_error", "message": str(exc)}
        core.emit({"command": command, "ok": False, "error": error}, 1)


def _calculation_loaded_from_state(
    state: Mapping[str, Any], state_path: Path, config_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[Mapping[str, Any]], list[Mapping[str, Any]], dict[str, Any]]:
    study_identity = study_comparison.preflight_state(state, state_path, require_density=True)
    policy, policy_record, policy_path = _registered_documents(state, state_path, stage="define_policy", schema_version=runtime_identity("subject-index-evaluation-policy-v4"), schema_name="evaluation-policy-v4.schema.json")[0]
    validate_v8_policy(policy)
    manifest, manifest_record, manifest_path = _registered_documents(state, state_path, stage="chunk_definition", schema_version="chunk-manifest-v1", schema_name="chunk-manifest.schema.json")[0]
    locator_entries = _registered_documents(state, state_path, stage="locator_audit", schema_version="locator-audit-v2", schema_name="locator-audit-v2.schema.json", many=True)
    missing_entries = _registered_documents(state, state_path, stage="missing_access_audit", schema_version="missing-access-audit-v1", schema_name="missing-access-audit.schema.json", many=True)
    structure, structure_record, structure_path = _registered_documents(state, state_path, stage="structure_audit", schema_version="structure-audit-v6", schema_name="structure-audit-v6.schema.json")[0]
    validate_structure_audit_semantics(structure)
    validate_heading_access_provenance(
        structure,
        (item[0] for item in locator_entries),
        (item[0] for item in missing_entries),
    )
    inventory, inventory_record, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="subject-index-item-inventory-v2", schema_name="item-inventory-v2.schema.json")[0]
    candidate, _, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="candidate-index-v2", schema_name="candidate-index-v2.schema.json")[0]
    core.require(inventory_record["path"] == state["candidate"]["item_inventory_path"] and candidate["candidate_sha256"] == inventory["candidate_sha256"], "candidate_identity_mismatch", "Registered candidate and item inventory differ.")

    def reference(record: Mapping[str, Any]) -> dict[str, str]:
        target = resolve_artifact_path(state_path, record["path"])
        return {"path": Path(os.path.relpath(target, config_path.parent)).as_posix(), "sha256": record["sha256"]}

    config = {
        "schema_version": runtime_identity("subject-index-dimension-calculation-input-v2"),
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
    loaded["study_identity"] = study_identity
    if is_v10():
        from v10_candidate_access import bound_review
        benchmark, _ = study_comparison.registered_document(state, state_path, 'benchmark_freeze', 'source-subject-benchmark-v2')
        lock = study_comparison.load_study_binding(state, state_path)
        loaded["candidate_access_review"] = bound_review(state, state_path, benchmark, lock)
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
                "input": output_dir / ("dimension-calculation-input.v5.json" if semantic_uncertainty() else "dimension-calculation-input.v4.json" if is_v10() else "dimension-calculation-input.v3.json" if percentage_native() else "dimension-calculation-input.v2.json"),
                "calculation": output_dir / ("dimension-calculations.v9.json" if semantic_uncertainty() else "dimension-calculations.v8.json" if is_v10() else "dimension-calculations.v7.json" if percentage_native() else "dimension-calculations.v6.json"),
                "items": output_dir / ("item-assessments.v10.json" if semantic_uncertainty() else "item-assessments.v9.json" if is_v10() else "item-assessments.v8.json" if percentage_native() else "item-assessments.v7.json"),
                "metadata": output_dir / ("projection-metadata.v10-semantic-v2.json" if semantic_uncertainty() else "projection-metadata.v10.json" if is_v10() else "projection-metadata.v9.json" if percentage_native() else "projection-metadata.v2.json"),
                "result": output_dir / ("evaluation-result.v15.json" if semantic_uncertainty() else "evaluation-result.v14.json" if is_v10() else "evaluation-result.v13.json" if percentage_native() else "evaluation-result.v12.json"),
            }
            collisions = [str(path) for path in outputs.values() if path.exists()]
            core.require(not collisions, "output_exists", "Refusing to overwrite scoring output.", collisions)
            loaded, inventory, inventory_record, locator_documents, missing_documents, structure_record = _calculation_loaded_from_state(state, state_path, outputs["input"])
            calculation = calculate_loaded(loaded)
            core.require(calculation["status"] == "scored" or (semantic_uncertainty() and any(d.get("semantic_uncertainty") for d in calculation["dimensions"])), "v8_score_incomplete", "Current full-state inputs did not produce a complete score.", calculation["status"])
            core.validate_schema_document(calculation, "dimension-calculations-v6.schema.json", "Generated V8 calculation")
            items = _current_item_assessments(inventory, inventory_record, calculation, loaded["structure"], locator_documents, missing_documents)
            stamp = now()
            input_payload = _json_bytes(loaded["config"])
            calculation_payload = _json_bytes(calculation)
            items_payload = _json_bytes(items)
            input_hashes = [item["sha256"] for item in loaded["input_artifacts"]]
            if loaded.get("candidate_access_review", {}).get("receipt_file_sha256"):
                input_hashes.append(loaded["candidate_access_review"]["receipt_file_sha256"])
            input_record = _artifact_record(root, outputs["input"], input_payload, stage="scoring", artifact_type="dimension_calculation_input", schema_version=runtime_identity("subject-index-dimension-calculation-input-v2"), stamp=stamp, input_sha256=input_hashes)
            calculation_record = _artifact_record(root, outputs["calculation"], calculation_payload, stage="scoring", artifact_type="dimension_calculations", schema_version=runtime_identity("subject-index-dimension-calculations-v6"), stamp=stamp, input_sha256=input_hashes)
            items_record = _artifact_record(root, outputs["items"], items_payload, stage="scoring", artifact_type="item_assessments", schema_version=runtime_identity("subject-index-item-assessments-v7"), stamp=stamp, input_sha256=(calculation_record["sha256"], inventory_record["sha256"], structure_record["sha256"]))
            metadata = _projection_metadata(policy=loaded["policy"], calculation=calculation, calculation_record=calculation_record, structure=loaded["structure"], structure_record=structure_record, candidate_label=inventory["candidate_id"], locator_documents=locator_documents, inventory=inventory, candidate_access_review=loaded.get("candidate_access_review"))
            metadata_payload = _json_bytes(metadata)
            metadata_record = _artifact_record(root, outputs["metadata"], metadata_payload, stage="scoring", artifact_type="projection_metadata", schema_version=runtime_identity("subject-index-v8-projection-metadata-v2"), stamp=stamp, input_sha256=(calculation_record["sha256"], structure_record["sha256"]))
            result = _evaluation_result(calculation=calculation, calculation_record=calculation_record, items=items, items_record=items_record, structure_record=structure_record, metadata=metadata, metadata_record=metadata_record)
            if loaded.get("study_identity") is not None:
                result["comparison_key"]["study_identity"] = loaded["study_identity"]
            core.validate_schema_document(result,"evaluation-result-v12.schema.json","Final bound evaluation result")
            result_payload = _json_bytes(result)
            result_record = _artifact_record(root, outputs["result"], result_payload, stage="scoring", artifact_type="evaluation_result", schema_version=runtime_identity("subject-index-evaluation-result-v12"), stamp=stamp, visibility="public", input_sha256=(calculation_record["sha256"], items_record["sha256"], structure_record["sha256"], metadata_record["sha256"]))
            records = [input_record, calculation_record, items_record, metadata_record, result_record]
            updated = _add_records_and_complete(state, state_path, "scoring", records, ("Calculated V10 percentages and registered the validated V14 result atomically." if is_v10() else "Assembled registered inputs, calculated V9 percentages, and registered the validated V13 result atomically." if percentage_native() else "Assembled registered inputs, calculated V8 dimensions, and registered the validated V12 result atomically."))
            for path, payload in zip(outputs.values(), (input_payload, calculation_payload, items_payload, metadata_payload, result_payload), strict=True):
                _atomic_write(path, payload)
            save_state(state_path, updated)
        core.emit({"command": command, "ok": True, "evaluation_id": state["evaluation_id"], "overall_percentage": calculation["overall_percentage"], "artifacts_registered": [record["path"] for record in records], "artifacts_written": [str(path) for path in outputs.values()] + [str(state_path)], "next_actions": [next_stage(updated)], "warnings": warnings})
    except (OSError, core.CalculationError, StructureAuditError, HeadingAccessProvenanceError, ValueError) as exc:
        if isinstance(exc, (core.CalculationError, StructureAuditError, HeadingAccessProvenanceError)):
            error = {"code": exc.code, "message": exc.message, "details": exc.details}
        else:
            error = {"code": "scoring_registration_error", "message": str(exc)}
        core.emit({"command": command, "ok": False, "error": error}, 1)


def command_build_report_state(args: argparse.Namespace) -> None:
    command = "build-web-report"
    state_path = Path(args.state).resolve()
    try:
        with evaluation_mutation_lock(state_path):
            state = load_state(state_path)
            errors, warnings = validate_state(state, state_path=state_path)
            core.require(not errors, "canonical_state_invalid", "Canonical evaluation state is invalid.", errors)
            replacing = bool(getattr(args, "replace_complete_bundle", False) and state["stages"]["web_report"]["status"] == "completed")
            if not replacing:
                state, warnings = _transition_state(state_path, "web_report")
            result, result_record, _ = _registered_documents(state, state_path, stage="scoring", schema_version=runtime_identity("subject-index-evaluation-result-v12"), schema_name="evaluation-result-v12.schema.json")[0]
            calculation, calculation_record, _ = _registered_documents(state, state_path, stage="scoring", schema_version=runtime_identity("subject-index-dimension-calculations-v6"), schema_name="dimension-calculations-v6.schema.json", sha256=result["dimension_calculations"]["sha256"])[0]
            items, items_record, _ = _registered_documents(state, state_path, stage="scoring", schema_version=runtime_identity("subject-index-item-assessments-v7"), schema_name="item-assessments-v7.schema.json")[0]
            metadata, metadata_record, _ = _registered_documents(state, state_path, stage="scoring", schema_version=runtime_identity("subject-index-v8-projection-metadata-v2"), schema_name="v8-projection-metadata-v2.schema.json")[0]
            structure, structure_record, _ = _registered_documents(state, state_path, stage="structure_audit", schema_version="structure-audit-v6", schema_name="structure-audit-v6.schema.json")[0]
            candidate, candidate_record, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="candidate-index-v2", schema_name="candidate-index-v2.schema.json")[0]
            inventory, inventory_record, _ = _registered_documents(state, state_path, stage="candidate_normalization", schema_version="subject-index-item-inventory-v2", schema_name="item-inventory-v2.schema.json")[0]
            benchmark, benchmark_record, _ = _registered_documents(state, state_path, stage="benchmark_freeze", schema_version="source-subject-benchmark-v2", schema_name="source-benchmark.schema.json")[0]
            manifest, manifest_record, _ = _registered_documents(state, state_path, stage="chunk_definition", schema_version="chunk-manifest-v1", schema_name="chunk-manifest.schema.json")[0]
            missing_entries = _registered_documents(state, state_path, stage="missing_access_audit", schema_version="missing-access-audit-v1", schema_name="missing-access-audit.schema.json", many=True)
            core.require(calculation["calculation_sha256"] == core.canonical_hash(calculation, "calculation_sha256"), "calculation_self_hash_mismatch", "Registered calculation self-hash does not reconstruct.")
            core.require(metadata["projection_metadata_sha256"] == core.canonical_hash(metadata, "projection_metadata_sha256"), "projection_metadata_self_hash_mismatch", "Registered projection metadata self-hash does not reconstruct.")
            core.require(result["evaluation_id"] == calculation["evaluation_id"] == items["evaluation_id"] == state["evaluation_id"], "evaluation_identity_mismatch", "Registered scoring artifacts use different evaluation identities.")
            core.require(result["dimension_calculations"]["sha256"] == calculation_record["sha256"] and result["item_assessments"]["sha256"] == items_record["sha256"] and result["structure_audit"]["sha256"] == structure_record["sha256"] and result["projection_metadata"]["sha256"] == metadata_record["sha256"], "result_artifact_binding_mismatch", "Registered result references do not match registered current artifacts.")
            study_identity = study_comparison.preflight_state(state, state_path, require_density=True)
            core.require(result["comparison_key"].get("study_identity") == study_identity, "study_comparison_stale", "Rescore after changing the study binding; report identity must match current evidence.")
            output = _state_output_path(state_path.parent, args.output or str(Path(result_record["path"]).parent / ("web-report.v13.json" if semantic_uncertainty() else "web-report.v12.json" if is_v10() else "web-report.v11.json" if percentage_native() else "web-report.v10.json")))
            bundle_output = _state_output_path(state_path.parent, args.bundle_output or str(Path(result_record["path"]).parent / ("v10-canonical-projection" if is_v10() else "v9-canonical-projection" if percentage_native() else "v8-canonical-projection")))
            if not replacing:
                core.require(not output.exists() and not bundle_output.exists(), "output_exists", "Refusing to overwrite web report or canonical web projection bundle.", [str(output), str(bundle_output)])
            report = _web_report(
                result=result,
                calculation=calculation,
                calculation_record=calculation_record,
                items=items,
                items_record=items_record,
                structure=structure,
                structure_record=structure_record,
                metadata=metadata,
                candidate=candidate,
                missing_documents=[item[0] for item in missing_entries],
            )
            report["methodology"]["benchmark"] = study_comparison.benchmark_identity(benchmark)
            if study_identity is not None:
                report["methodology"]["benchmark"]["release"] = deepcopy(study_identity["release"])
            core.validate_schema_document(report, "web-report-v10.schema.json", "Benchmark-labeled report")
            payload = _json_bytes(report)
            stamp = now()
            record = _artifact_record(state_path.parent, output, payload, stage="web_report", artifact_type="web_report", schema_version=runtime_identity("subject-index-web-report-v10"), stamp=stamp, visibility="public", input_sha256=(result_record["sha256"], calculation_record["sha256"], items_record["sha256"], structure_record["sha256"], metadata_record["sha256"]))
            if percentage_native():
                core.require(all(item.get("schema_version") == web_projection.OVERLAY_SCHEMA_VERSION for item in state["artifacts"] if item.get("artifact_type") == "correction_overlay"), "legacy_overlay_requires_rebinding", "The percentage runtime requires a native percentage-only overlay explicitly bound to this evaluation")
            overlay_entries = [item for item in state["artifacts"] if item.get("artifact_type") == "correction_overlay" and item.get("schema_version") == web_projection.OVERLAY_SCHEMA_VERSION]
            core.require(len(overlay_entries) <= 1, "duplicate_registered_artifact", "At most one confirmed correction overlay may apply.")
            overlay = overlay_record = None
            if overlay_entries:
                overlay_record = deepcopy(overlay_entries[0])
                overlay_path = resolve_artifact_path(state_path, overlay_record["path"])
                core.require(core.sha256_file(overlay_path) == overlay_record["sha256"], "registered_artifact_hash_mismatch", "Registered correction overlay bytes changed.")
                overlay = core.load_json(overlay_path, web_projection.OVERLAY_SCHEMA_VERSION)
                core.validate_schema_document(overlay, "correction-overlay-v1.schema.json", "Registered correction overlay")
                core.require(overlay["evaluation_id"] == state["evaluation_id"] and overlay["overlay_sha256"] == core.canonical_hash(overlay, "overlay_sha256"), "correction_overlay_binding_mismatch", "Correction overlay identity or self-hash is invalid.")
            projection, collections = web_projection.build_bundle(
                result=result, result_record=result_record, report=report, report_record=record,
                calculation=calculation, calculation_record=calculation_record, items=items, items_record=items_record,
                candidate=candidate, candidate_record=candidate_record, inventory=inventory, inventory_record=inventory_record,
                benchmark=benchmark, benchmark_record=benchmark_record, structure=structure, structure_record=structure_record,
                manifest=manifest, manifest_record=manifest_record, missing_documents=[item[0] for item in missing_entries],
                missing_records=[item[1] for item in missing_entries], overlay=overlay, overlay_record=overlay_record,
            )
            web_projection.validate_bundle(projection, collections)
            generated = [(bundle_output / "projection.v1.json", web_projection.json_bytes(projection), "web_projection", web_projection.PROJECTION_SCHEMA_VERSION)]
            generated.extend((bundle_output / web_projection.COLLECTION_PATHS[key], web_projection.json_bytes(value), "correction_overlay" if key == "correction_overlay" else f"web_{key}", value["schema_version"]) for key, value in collections.items())
            bundle_records = [_artifact_record(state_path.parent, path, data, stage="web_report", artifact_type=artifact_type, schema_version=schema_version, stamp=stamp, visibility="public", input_sha256=(record["sha256"], result_record["sha256"])) for path, data, artifact_type, schema_version in generated]
            records = [record, *bundle_records]
            if replacing:
                current_inputs = [result_record, calculation_record, items_record, structure_record, candidate_record, inventory_record, benchmark_record, manifest_record, *[item[1] for item in missing_entries]]
                if overlay_record is not None:
                    current_inputs.append(overlay_record)
                _validate_complete_web_bundle(state, state_path, records, output, bundle_output, current_inputs, calculation)
                updated = _replace_records_and_complete(state, state_path, "web_report", records, "Rebuilt and replaced the complete canonical public web projection bundle atomically.")
            else:
                updated = _add_records_and_complete(state, state_path, "web_report", records, ("Built and registered web-report.v12 and the V10 public projection bundle atomically." if is_v10() else "Built and registered web-report.v11 and the complete V9 public web projection bundle atomically." if percentage_native() else "Built and registered web-report.v10 and the complete canonical public web projection bundle atomically."))
            writes = [(output, payload), *[(row[0], row[1]) for row in generated]]
            _write_web_bundle_transaction(state_path, writes, updated, bundle_output=bundle_output)
        core.emit({"command": command, "ok": True, "evaluation_id": state["evaluation_id"], "report_id": report["report_id"], "projection_id": projection["projection_id"], "replacement": replacing, "artifacts_registered": [item["path"] for item in records], "artifacts_written": [str(output), *[str(row[0]) for row in generated], str(state_path)], "next_actions": [], "warnings": warnings})
    except (OSError, core.CalculationError, StructureAuditError, HeadingAccessProvenanceError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, (core.CalculationError, StructureAuditError, HeadingAccessProvenanceError)):
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
    report = subparsers.add_parser("build-report", help="Build, validate, and atomically register web-report.v10 and its canonical public web projection bundle.")
    report.add_argument("--state", required=True)
    report.add_argument("--output", help="Output path inside the evaluation directory (default: beside the registered result).")
    report.add_argument("--bundle-output", help="Bundle directory inside the evaluation directory (default: v8-canonical-projection beside the result).")
    report.add_argument("--replace-complete-bundle", action="store_true", help="Validate and atomically replace the complete registered web-report bundle without changing scoring artifacts.")
    report.set_defaults(func=command_build_report_state)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
