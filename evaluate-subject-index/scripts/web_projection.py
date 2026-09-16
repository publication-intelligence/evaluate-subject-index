"""Deterministic public-safe web projection from finalized V8 artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

import scoring_core as core


PROJECTION_SCHEMA_VERSION = "ohfr-v8-canonical-web-projection-v1"
COLLECTION_SCHEMA_VERSION = "ohfr-v8-web-collection-v1"
OVERLAY_SCHEMA_VERSION = "ohfr-v8-representation-correction-overlay-v1"
COLLECTION_PATHS = {
    "index_records": "data/index-records.v1.json",
    "source_subjects": "data/source-subjects.v1.json",
    "density": "data/density.v1.json",
    "correction_overlay": "data/correction-overlay.v1.json",
}
PROHIBITED_KEYS = {
    "evidence_summary", "source_excerpt", "excerpt", "quote", "private_evidence",
    "layout_line_ids", "region_ids", "bboxes", "candidate_pdf_pages",
}
PROHIBITED_TEXT = ("/home/", "storage-provider", "storage_provider", ".pdf", "s3://", "gs://")
SECRET_KEYS = ("secret", "password", "access_token", "api_key", "private_key")
COMPATIBILITY_ALIAS_DISCLOSURE = (
    "Exact percentage and weighted-contribution strings are authoritative; numeric rating and points aliases exist only for the established generic website adapter."
)
DISPLAY_CAUTIONS = (
    "Aggregate scores come from the authoritative V8 calculation, not reconstructed item grades.",
    "Source excerpts and private layout evidence are excluded.",
    COMPATIBILITY_ALIAS_DISCLOSURE,
)


def _self_hash(value: Mapping[str, Any], field: str) -> str:
    return core.canonical_hash(value, field)


def _file_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(core.json_output_value(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def public_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: public_safe(item) for key, item in value.items() if key not in PROHIBITED_KEYS}
    if isinstance(value, list):
        return [public_safe(item) for item in value]
    return value


def _projection_limitations(result: Mapping[str, Any]) -> list[str]:
    return list(dict.fromkeys([*public_safe(deepcopy(result["limitations"])), *DISPLAY_CAUTIONS]))


def dimension_denominator_disclosures(calculation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "dimension_id": dimension["dimension_id"],
            "components": deepcopy(dimension["denominators"]["components"]),
        }
        for dimension in calculation["dimensions"]
    ]


def scorecard_with_compatibility_aliases(scorecard: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **deepcopy(row),
            "rating": float(row["dimension_percentage"]) / 20,
            "awarded_points": float(row["weighted_contribution"]),
            "maximum_points": row["weight"],
        }
        for row in scorecard
    ]


def _public_label(value: Any) -> str:
    return "not measured" if value is None else str(value).replace("_", " ")


def public_locator_explanation(assessment: Mapping[str, Any]) -> dict[str, Any]:
    """Replace private locator prose with structured public-safe narration."""
    explanation = deepcopy(assessment["locator_explanation"])
    treatment = explanation["page_treatment"]
    fit = explanation["complete_path_fit"]
    grade = explanation["diagnostic_locator_grade"]["score"]
    credit = explanation["keep_rating_credit"]["credit"]
    judgment = _public_label(assessment["judgment"])
    label = assessment["source_page_label"]
    explanation["evidence_summary"] = (
        f"Page {label}: {judgment}; page treatment {_public_label(treatment['category'])}; "
        f"complete-path fit {_public_label(fit['category'])}; diagnostic grade {_public_label(grade)}; "
        f"keep credit {_public_label(credit)}."
    )
    for axis, title in ((treatment, "Page treatment"), (fit, "Complete-path fit")):
        axis["rationale"] = (
            f"{title} is {_public_label(axis['category'])} with score {_public_label(axis['score'])} "
            f"under rule {axis['rule_id']}."
        )
        axis["rationale_source"] = "mechanical_structured_category_rule"
    return explanation


def public_locator_assessment(assessment: Mapping[str, Any]) -> dict[str, Any]:
    """Project one private locator assessment without authored evidence prose."""
    public = deepcopy(assessment)
    explanation = public_locator_explanation(assessment)
    public["locator_explanation"] = explanation
    public["summary"] = explanation["evidence_summary"]
    public["popover"]["summary"] = explanation["evidence_summary"]
    factor_explanations = {
        "page_treatment": explanation["page_treatment"]["rationale"],
        "complete_path_fit": explanation["complete_path_fit"]["rationale"],
        "diagnostic_locator_grade": explanation["diagnostic_locator_grade"]["calculation"],
    }
    for factor in public["popover"]["factors"]:
        factor["explanation"] = factor_explanations.get(factor["factor_id"], "Structured locator assessment factor.")
    return public


def _selected(value: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {field: deepcopy(value[field]) for field in fields if field in value}


ACCESS_IDENTITY_FIELDS = (
    "locator_ids", "matched_path_ids", "matched_locator_ids", "usable_locator_ids", "source_evidence_ids",
    "locator_evidence_ids", "benchmark_evidence_ids", "source_uncertainty_ids", "usable_locator_evidence_ids",
    "tested_locator_ids", "tested_locator_evidence_ids", "tested_path_ids", "tested_direct_path_ids",
    "usable_cross_reference_ids", "usable_cross_reference_path_ids", "usable_path_ids",
    "tested_cross_reference_ids", "tested_cross_reference_source_path_ids", "source_path_ids",
    "tested_source_path_ids", "matched_reference_ids", "matched_cross_reference_ids",
)
ACCESS_CATEGORY_FIELDS = (
    "reason_code", "miss_reason_code", "confidence", "expected_count", "found_count",
    "missed_count", "matched_count", "usable_count",
)


def _public_access_fields(value: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    public = _selected(value, (*fields, *ACCESS_IDENTITY_FIELDS, *ACCESS_CATEGORY_FIELDS))
    uncertainty = value.get("uncertainty")
    if isinstance(uncertainty, Mapping):
        projected = _selected(uncertainty, ("status", "confidence", "evidence_ids", *ACCESS_IDENTITY_FIELDS))
        if uncertainty.get("status") in {"uncertain", "uninspectable"}:
            projected["reason"] = f"Access uncertainty status is {uncertainty['status']}."
        public["uncertainty"] = projected
    elif uncertainty is not None:
        public["uncertainty"] = uncertainty if uncertainty in {"none", "uncertain", "uninspectable", "not_measured"} else "reported"
    return public


def public_subject_access(judgment: Mapping[str, Any]) -> dict[str, Any]:
    public = _public_access_fields(judgment, (
        "subject_id", "priority", "coverage", "direct_access", "cross_reference_access",
        "stance_preserved", "matched_path_ids", "expected_document_pages", "found_document_pages",
        "missed_document_pages", "severity", "confidence", "realistic_first_lookup_success",
        "treatment_recall", "locator_recall", "error_codes", "evidence_ids",
    ))
    public["missing_routes"] = [_public_access_fields(row, ("route_type", "reason_code", "evidence_ids")) for row in judgment.get("missing_routes", [])]
    public["missed_treatments"] = [_public_access_fields(row, ("treatment_id", "document_page", "locator_class", "reason_code", "evidence_ids")) for row in judgment.get("missed_treatments", [])]
    public["dependency_defects"] = []
    for row in judgment.get("dependency_defects", []):
        defect = _public_access_fields(row, ("defect_id", "dependency_type", "disposition", "locator_id", "coverage_subject_ids", "confidence", "evidence_ids"))
        defect["observed_conflict"] = f"Structured locator dependency defect {row['defect_id']} was reported."
        defect["required_adjudication"] = "Review the registered dependency defect and evidence identifiers."
        defect["summary"] = defect["observed_conflict"]
        public["dependency_defects"].append(defect)
    details = [f"Coverage is {judgment['coverage']}"]
    if "direct_access" in judgment:
        details.append(f"direct access is {judgment['direct_access']}")
    if "cross_reference_access" in judgment:
        details.append(f"cross-reference access is {judgment['cross_reference_access']}")
    public["access_rationale"] = "; ".join(details) + "."
    return public


def public_reader_task_result(result: Mapping[str, Any]) -> dict[str, Any]:
    public = _public_access_fields(result, ("task_id", "subject_ids", "result", "access_mode", "matched_path_ids", "severity", "confidence", "evidence_ids"))
    access_mode = f" through {result['access_mode']} access" if "access_mode" in result else ""
    public["access_rationale"] = f"Reader task result is {result['result']}{access_mode}."
    return public


def public_treatment_judgment(treatment: Mapping[str, Any], source_page_label: str) -> dict[str, Any]:
    public = _public_access_fields(treatment, ("treatment_id", "subject_id", "document_page", "locator_class", "status", "evidence_ids"))
    public["source_page_label"] = source_page_label
    public["access_rationale"] = (
        f"{treatment['locator_class'].replace('_', ' ').capitalize()} treatment on page "
        f"{source_page_label} is {treatment['status']}."
    )
    return public


def collection(kind: str, items: list[dict[str, Any]], source_order: str, **extra: Any) -> dict[str, Any]:
    value = {
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "collection_kind": kind,
        "source_order": source_order,
        "count": len(items),
        "items": items,
        **extra,
    }
    value["collection_sha256"] = _self_hash(value, "collection_sha256")
    return value


def _canonical_target(value: str) -> str:
    normalized = value.casefold().replace("–", "—")
    normalized = re.sub(r"\s*(?:—|--)\s*", "—", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _target_lookup_keys(value: str, *, under_context: bool = False) -> tuple[str, ...]:
    exact = _canonical_target(value)
    hierarchy = re.match(r"(?is)^under\s+([^:]+?)\s*:\s*(.+)$", value.strip())
    if hierarchy is None and under_context:
        hierarchy = re.match(r"(?is)^([^:]+?)\s*:\s*(.+)$", value.strip())
    if hierarchy is None:
        return (exact,)
    hierarchical = _canonical_target(f"{hierarchy.group(1)}—{hierarchy.group(2)}")
    return (exact,) if hierarchical == exact else (exact, hierarchical)


def _resolved_targets(target: str, index: Mapping[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    parts = re.split(r"\s*;\s*", target)
    under_context = bool(parts and re.match(r"(?is)^under\s+[^:]+?\s*:\s*.+$", parts[0].strip()))
    for part in parts:
        matches: list[dict[str, str]] = []
        for key in _target_lookup_keys(part, under_context=under_context):
            matches = index.get(key, [])
            if matches:
                break
        if not matches or len({match["node_id"] for match in matches}) != 1:
            return []
        results.extend(matches)
    return results


def build_index_records(candidate: Mapping[str, Any], inventory: Mapping[str, Any], items: Mapping[str, Any]) -> dict[str, Any]:
    paths = {row["path_id"]: row for row in inventory["paths"]}
    nodes = {row["node_id"]: row for row in inventory["heading_nodes"]}
    locator_items = {row["locator_id"]: row for row in items["locator_assessments"]}
    path_items = {row["path_id"]: row for row in items["path_assessments"]}
    node_items = {row["node_id"]: row for row in items["heading_node_assessments"]}
    reference_items = {row["reference_id"]: row for row in items["cross_reference_assessments"]}
    target_index: dict[str, list[dict[str, str]]] = {}
    for record in candidate["records"]:
        path = paths[record["path_id"]]
        target_index.setdefault(_canonical_target("—".join(record["heading_path"])), []).append(
            {"record_id": record["record_id"], "path_id": record["path_id"], "node_id": path["node_ids"][-1]}
        )

    output = []
    for delivered_order, record in enumerate(candidate["records"]):
        path = paths[record["path_id"]]
        terminal_node_id = path["node_ids"][-1]
        assignments = {row["locator_id"]: row for row in record["locator_assignments"]}
        displays = []
        for display_order, display in enumerate(record["locator_displays"]):
            atomic = []
            for atomic_order, locator_id in enumerate(display["locator_ids"]):
                assignment = assignments[locator_id]
                atomic.append({
                    "atomic_order": atomic_order,
                    "locator_id": locator_id,
                    "source_page_label": assignment["source_page_label"],
                    "document_page": assignment["document_page"],
                    "mapping_status": assignment["mapping_status"],
                    "adjusted_assessment": None,


                    "assessment": public_locator_assessment(locator_items[locator_id]),
                })
            displays.append({
                "display_order": display_order,
                "display_id": display["display_id"],
                "displayed_locator": display["displayed_locator"],
                "kind": display["kind"],
                "range_id": display.get("range_id"),
                "range_start_display": display.get("start_display"),
                "range_end_display": display.get("end_display"),
                "mapping_status": display["mapping_status"],
                "atomic_locator_ids": deepcopy(display["locator_ids"]),
                "atomic_locators": atomic,
            })
        references = []
        for reference_order, raw in enumerate(record["cross_references"]):
            resolved = _resolved_targets(raw["target"], target_index)
            resolution = {"status": "resolved" if resolved else "unresolved", "targets": resolved}
            assessment = deepcopy(reference_items[raw["reference_id"]])
            references.append({
                "reference_order": reference_order,
                "reference_id": raw["reference_id"],
                "reference_type": raw["type"],
                "source": {"record_id": record["record_id"], "path_id": record["path_id"], "node_id": terminal_node_id, "heading_path": deepcopy(record["heading_path"])},
                "target_display": raw["target"],
                "resolution": resolution,
                "adjusted_resolution": deepcopy(resolution),
                "assessment": assessment,
                "adjusted_assessment": None,
                "adjusted_judgment": assessment["judgment"],
            })
        output.append({
            "delivered_order": delivered_order,
            "record_id": record["record_id"],
            "record_type": record["record_type"],
            "path_id": record["path_id"],
            "node_ids": deepcopy(path["node_ids"]),
            "terminal_node_id": terminal_node_id,
            "parent_node_id": nodes[terminal_node_id]["parent_node_id"],
            "heading_hierarchy": [{"level": level, "node_id": node_id, "parent_node_id": nodes[node_id]["parent_node_id"], "heading": heading, "assessment": deepcopy(node_items[node_id])} for level, (node_id, heading) in enumerate(zip(path["node_ids"], record["heading_path"], strict=True))],
            "delivered_indentation_level": record.get("delivered_indentation_level", len(record["heading_path"]) - 1),
            "heading_path": deepcopy(record["heading_path"]),
            "delivered_heading_path": deepcopy(record["heading_path"]),
            "corrected_heading_path": [],
            "display_heading_path": deepcopy(record["heading_path"]),
            "original_displayed_form": record["original_displayed_form"],
            "displayed_locators": displays,
            "cross_references": references,
            "heading_assessment": deepcopy(node_items[terminal_node_id]),
            "adjusted_heading_assessment": None,
            "path_assessment": deepcopy(path_items[record["path_id"]]),
        })
    return collection("index_records", output, "candidate.records delivered order", counts={
        "records": len(output), "heading_nodes": len(nodes), "paths": len(paths),
        "displayed_locators": sum(len(row["displayed_locators"]) for row in output),
        "atomic_locators": sum(len(display["atomic_locators"]) for row in output for display in row["displayed_locators"]),
        "cross_references": sum(len(row["cross_references"]) for row in output),
    })


def build_source_subjects(benchmark: Mapping[str, Any], items: Mapping[str, Any], missing_documents: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    assessments = {row["subject_id"]: row for row in items["source_subject_assessments"]}
    subject_judgments = {row["subject_id"]: row for document in missing_documents for row in document["subject_judgments"]}
    task_results = {row["task_id"]: row for document in missing_documents for row in document["reader_task_results"]}
    treatment_rows = [row for document in missing_documents for row in document["treatment_judgments"]]
    treatments: dict[str, list[Mapping[str, Any]]] = {}
    for row in treatment_rows:
        treatments.setdefault(row["subject_id"], []).append(row)
    tasks: dict[str, list[Mapping[str, Any]]] = {}
    for task in benchmark["reader_tasks"]:
        for subject_id in task["subject_ids"]:
            tasks.setdefault(subject_id, []).append(task)
    subject_ids = [row["subject_id"] for row in benchmark["subjects"]]
    core.require(set(subject_ids) == set(assessments) == set(subject_judgments), "projection_subject_join_mismatch", "Benchmark, item assessments, and missing-access judgments do not cover the same subjects.")
    core.require(set(task_results) == {row["task_id"] for row in benchmark["reader_tasks"]}, "projection_task_join_mismatch", "Reader-task results do not cover the frozen benchmark tasks exactly.")
    output = []
    for source_order, subject in enumerate(benchmark["subjects"]):
        evidence_by_key: dict[tuple[int, str], list[Mapping[str, Any]]] = {}
        for evidence in subject["evidence"]:
            evidence_by_key.setdefault((evidence["document_page"], evidence["locator_class"]), []).append(evidence)
        expected_treatments = []
        for treatment in sorted(treatments.get(subject["subject_id"], []), key=lambda row: row["treatment_id"]):
            matches = evidence_by_key.get((treatment["document_page"], treatment["locator_class"]), [])
            core.require(bool(matches), "projection_treatment_join_mismatch", f"No frozen evidence matches {treatment['treatment_id']}.")
            expected_treatments.append(public_treatment_judgment(treatment, matches[0]["source_page_label"]))
        output.append({
            "source_order": source_order,
            "subject_id": subject["subject_id"], "label": subject["label"], "priority": subject["priority"],
            "meaning": subject["meaning"],
            "stance": (
                "Benchmark stance narrative withheld from the public projection; "
                f"stance preservation outcome: {subject_judgments[subject['subject_id']].get('stance_preserved', 'not reported')}."
            ),
            "acceptable_access": deepcopy(subject["acceptable_access"]),
            "chapter_provenance": deepcopy(subject.get("chapter_provenance", [])),
            "source_chunk_ids": deepcopy(subject.get("source_chunk_ids", subject.get("chapter_provenance", []))),
            "assessment": deepcopy(assessments[subject["subject_id"]]),
            "audit_judgment": public_subject_access(subject_judgments[subject["subject_id"]]),
            "reader_tasks": [{"task_id": task["task_id"], "question": task["question"], "subject_ids": deepcopy(task["subject_ids"]), "task_basis": deepcopy(task.get("task_basis", task.get("source_fields", []))), "result": public_reader_task_result(task_results[task["task_id"]])} for task in tasks.get(subject["subject_id"], [])],
            "expected_treatments": expected_treatments,
        })
    return collection(
        "source_subjects", output, "frozen benchmark subject order",
        counts={"source_subjects": len(output), "reader_tasks": len(task_results), "expected_treatments": len(treatment_rows)},
        limitations=["Authored benchmark stance narratives are withheld; public items report only the registered stance-preservation outcome."],
    )


def build_density(structure: Mapping[str, Any], manifest: Mapping[str, Any], calculation: Mapping[str, Any]) -> dict[str, Any]:
    chunks = {row["chunk_id"]: row for row in manifest["chunks"]}
    selectivity = next(row for row in calculation["dimensions"] if row["dimension_id"] == "editorial_selectivity")
    component = next(row for row in selectivity["components"] if row["component_id"] == "density_fit")
    calculated_rows = component["details"]["chapter_measurements"]
    calculated = {row["chunk_id"]: row for row in calculated_rows}
    expected = [row["chunk_id"] for row in structure["density"]["chapter_measurements"]]
    core.require(
        len(calculated) == len(calculated_rows) == len(expected) and set(calculated) == set(expected),
        "density_projection_chunk_mismatch",
        "Projected density calculations must cover every and only canonical structure density chunk.",
    )
    rows = []
    for source_order, measurement in enumerate(structure["density"]["chapter_measurements"]):
        chunk = chunks[measurement["chunk_id"]]
        fit = calculated[measurement["chunk_id"]]
        rows.append({
            "source_order": source_order, "chunk_id": measurement["chunk_id"], "title": chunk["title"],
            "source_units": deepcopy(chunk["source_units"]), "owned_document_page_ranges": deepcopy(chunk["owned_document_page_ranges"]),
            **deepcopy(measurement),
            "path_rate_per_1000_words": None if fit.get("path_rate") is None else float(fit["path_rate"]),
            "occurrence_rate_per_1000_words": None if fit.get("occurrence_rate") is None else float(fit["occurrence_rate"]),
            "canonical_fit_judgment": {
                "combined": fit.get("unit_fit_percentage"),
                "path_fit_percentage": fit.get("path_fit_percentage"),
                "occurrence_fit_percentage": fit.get("occurrence_fit_percentage"),
                "unit_fit_percentage": fit.get("unit_fit_percentage"),
                "status": fit.get("status", "not_measured" if fit.get("unit_fit_percentage") is None else "measured"),
                "basis": "canonical_finalized_density_calculation",
                "automatic_defect": False,
            },
        })
    density = structure["density"]
    fit_percentage = component.get("percentage")
    return collection("density", rows, "chunk manifest packet order", policy_status=density["policy_status"], measurement_level=density["measurement_level"], targets=deepcopy(density["targets"]), maximum_score_contribution=density["maximum_score_contribution"], fit_percentage=fit_percentage, fit_rating=None if fit_percentage is None else float(fit_percentage) / 20)


def _artifact_binding(record: Mapping[str, Any]) -> dict[str, Any]:
    return {"artifact_path": record["path"], "sha256": record["sha256"], "schema_version": record.get("schema_version"), "availability": "canonical_registered_input"}


def build_bundle(*, result: Mapping[str, Any], result_record: Mapping[str, Any], report: Mapping[str, Any], report_record: Mapping[str, Any], calculation: Mapping[str, Any], calculation_record: Mapping[str, Any], items: Mapping[str, Any], items_record: Mapping[str, Any], candidate: Mapping[str, Any], candidate_record: Mapping[str, Any], inventory: Mapping[str, Any], inventory_record: Mapping[str, Any], benchmark: Mapping[str, Any], benchmark_record: Mapping[str, Any], structure: Mapping[str, Any], structure_record: Mapping[str, Any], manifest: Mapping[str, Any], manifest_record: Mapping[str, Any], missing_documents: Sequence[Mapping[str, Any]], missing_records: Sequence[Mapping[str, Any]], overlay: Mapping[str, Any] | None, overlay_record: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    collections = {
        "index_records": public_safe(build_index_records(candidate, inventory, items)),
        "source_subjects": public_safe(build_source_subjects(benchmark, items, missing_documents)),
        "density": public_safe(build_density(structure, manifest, calculation)),
    }
    if overlay is not None:
        collections["correction_overlay"] = public_safe(deepcopy(overlay))
    for value in collections.values():
        hash_field = "overlay_sha256" if value.get("schema_version") == OVERLAY_SCHEMA_VERSION else "collection_sha256"
        value[hash_field] = _self_hash(value, hash_field)
    payloads = {key: json_bytes(value) for key, value in collections.items()}
    binding_order = (["correction_overlay"] if "correction_overlay" in collections else []) + ["index_records", "source_subjects", "density"]
    bindings = [{"collection_id": key, "artifact_path": COLLECTION_PATHS[key], "count": collections[key].get("affected_heading_count", collections[key].get("count", 0)), "content_sha256": collections[key].get("overlay_sha256", collections[key].get("collection_sha256")), "file_sha256": _file_hash(payloads[key])} for key in binding_order]
    gates = deepcopy(result["critical_gates"])
    readiness = {"status": result.get("evaluation_validity", {}).get("status") if result.get("evaluation_validity", {}).get("status", "valid") != "valid" else "not_publication_ready" if any(row["triggered"] for row in gates) else "publication_ready", "triggered_gate_ids": [row["gate_id"] for row in gates if row["triggered"]]}
    scorecard = scorecard_with_compatibility_aliases(report["scorecard"])
    dimension_denominators = deepcopy(report["calculation_explainer"]["dimension_denominators"])
    source_records = [benchmark_record, calculation_record, items_record, candidate_record, inventory_record, structure_record, manifest_record, result_record, report_record, *missing_records]
    if overlay_record is not None:
        source_records.append(overlay_record)
    overlay_applicable = overlay is not None
    correction_outcomes = {"applicable": False, "overlay_included": False, "reason": "No confirmed registered correction overlay applies.", "affected_headings": 0, "character_replacements": 0}
    if overlay_applicable:
        resolution = overlay.get("cross_reference_resolution", {})
        remaining = resolution.get("remaining_unresolved_reference", {})
        removed_minor = sum("removed_by_confirmed_representation_correction" in row.get("adjusted_status", "") for row in overlay.get("defect_outcomes", []))
        observed_minor = result.get("defect_counts", {}).get("minor", 0)
        correction_outcomes = deepcopy(overlay.get("correction_outcomes", {
            "affected_headings": overlay["affected_heading_count"],
            "character_replacements": overlay["character_replacement_count"],
            "corrected_cross_reference_id": resolution.get("item_id"),
            "remaining_unresolved_cross_reference_id": remaining.get("reference_id"),
            "observed_minor_defect_count": observed_minor,
            "adjusted_minor_defect_count": observed_minor - removed_minor,
            "cross_reference_gate_unchanged": True,
            "readiness_unchanged": True,
        }))
    projection = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "projection_id": "OHFR-V8-WEB-" + hashlib.sha256(json.dumps({"evaluation_id": result["evaluation_id"], "result_sha256": result_record["sha256"]}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12].upper(),
        "review_signals": deepcopy(result.get("review_signals", [])),
        "projection_role": "deterministic_public_safe_display_projection", "evaluation_id": result["evaluation_id"],
        "view_selection": {"authoritative_view_id": "canonical_as_delivered", "primary_view_id": "canonical_as_delivered", "default_display_view_id": "canonical_as_delivered", "display_view_rationale": "The canonical as-delivered result is authoritative."},
        "score_views": {"canonical_source_adjustment_status": report["score_views"]["adjustment_status"], "projection_adjustment_status": "confirmed_representation_adjustment_applied" if overlay_applicable else "not_applicable", "total_delta": 0, "views": [{"view_id": "canonical_as_delivered", "label": "Canonical as delivered", "view_kind": "observed", "role": "authoritative_primary_observation", "score": result["overall_percentage"], "maximum": 100, "scorecard": scorecard, "dimension_denominators": dimension_denominators, "critical_gates": gates, "readiness": readiness, "provenance_artifacts": [_artifact_binding(result_record), _artifact_binding(report_record), _artifact_binding(calculation_record)]}]},
        "correction_outcomes": correction_outcomes,
        "item_summaries": {"observed": deepcopy(items["summary"])}, "collections": bindings,
        "provenance": {"source_artifacts": [_artifact_binding(row) for row in sorted(source_records, key=lambda row: row["path"])], "source_sha256": result["provenance"]["source_sha256"], "benchmark_sha256": result["provenance"]["benchmark_sha256"], "judgment_policy_sha256": result["provenance"]["judgment_policy_sha256"], "rubric_version": result["provenance"]["rubric_version"], "dimension_calculation_profile": result["provenance"]["dimension_calculation_profile"], "projection_metadata_sha256": result["projection_metadata"]["projection_metadata_sha256"], "calculation_sha256": result["dimension_calculations"]["calculation_sha256"], "missing_access_audit_set_sha256": items["evidence_identity"]["missing_access_audit_set_sha256"], "correction_overlay_sha256": overlay.get("overlay_sha256") if overlay_applicable else None},
        "density_denominator": {"indexable_source_words": sum(row["indexable_source_words"] for row in structure["density"]["chapter_measurements"]), "unit": "words"},
        "public_safety": {"source_excerpts_included": False, "restricted_files_included": False, "private_layout_evidence_included": False, "absolute_paths_included": False, "source_subject_summaries_are_synthesized_not_quoted": True},
        "limitations": _projection_limitations(result),
    }
    projection["projection_sha256"] = _self_hash(projection, "projection_sha256")
    return projection, collections


def _validate_predecessor_display_contract(
    projection: Mapping[str, Any],
    *,
    canonical_scorecard: Sequence[Mapping[str, Any]],
    dimension_denominators: Sequence[Mapping[str, Any]],
) -> None:
    views = projection.get("score_views", {}).get("views", [])
    core.require(len(views) == 1, "invalid_legacy_projection", "Legacy projection must contain exactly one canonical score view.")
    view = views[0]
    expected_view_fields = {"view_id", "label", "view_kind", "role", "score", "maximum", "scorecard", "dimension_denominators", "critical_gates", "readiness", "provenance_artifacts"}
    core.require(frozenset(view) in {frozenset(expected_view_fields), frozenset(expected_view_fields - {"dimension_denominators"})}, "invalid_legacy_projection", "Predecessor projection score view has an unexpected shape.")
    canonical_fields = {"dimension_id", "dimension_percentage", "weight", "weighted_contribution", "formula_id"}
    alias_fields = {"dimension_id", "rating", "awarded_points", "maximum_points", "formula_id"}
    row_fields = {frozenset(row) for row in view["scorecard"]}
    core.require(len(row_fields) == 1 and next(iter(row_fields)) in {frozenset(canonical_fields), frozenset(alias_fields)}, "invalid_legacy_projection", "Predecessor projection scorecard is neither the exact-percentage nor compatibility-alias shape.")
    if next(iter(row_fields)) == frozenset(canonical_fields):
        core.require(view["scorecard"] == list(canonical_scorecard), "invalid_legacy_projection", "Predecessor exact scorecard differs from the canonical report scorecard.")
    else:
        expected_aliases = [
            {key: value for key, value in row.items() if key in alias_fields}
            for row in scorecard_with_compatibility_aliases(canonical_scorecard)
        ]
        actual_aliases = [{**row, "rating": float(row["rating"]), "awarded_points": float(row["awarded_points"]), "maximum_points": float(row["maximum_points"])} for row in view["scorecard"]]
        core.require(actual_aliases == expected_aliases, "invalid_legacy_projection", "Predecessor projection score aliases do not reconstruct from the canonical report scorecard.", {"expected": expected_aliases, "actual": view["scorecard"]})
    normalized = deepcopy(projection)
    normalized_view = normalized["score_views"]["views"][0]
    normalized_view["scorecard"] = scorecard_with_compatibility_aliases(canonical_scorecard)
    normalized_view["dimension_denominators"] = deepcopy(list(dimension_denominators))
    normalized["projection_sha256"] = _self_hash(normalized, "projection_sha256")
    core.validate_schema_document(normalized, "web-projection-v1.schema.json", "Legacy canonical web projection shape")


def validate_bundle(
    projection: Mapping[str, Any],
    collections: Mapping[str, Mapping[str, Any]],
    *,
    allow_legacy_display: bool = False,
    canonical_scorecard: Sequence[Mapping[str, Any]] = (),
    dimension_denominators: Sequence[Mapping[str, Any]] = (),
) -> None:
    strict_display = True
    try:
        core.validate_schema_document(dict(projection), "web-projection-v1.schema.json", "Generated canonical web projection")
    except core.CalculationError:
        if not allow_legacy_display:
            raise
        strict_display = False
        _validate_predecessor_display_contract(
            projection,
            canonical_scorecard=canonical_scorecard,
            dimension_denominators=dimension_denominators,
        )
    for view in projection["score_views"]["views"] if strict_display else []:
        for row in view["scorecard"]:
            core.require(
                float(row["rating"]) == float(row["dimension_percentage"]) / 20
                and float(row["awarded_points"]) == float(row["weighted_contribution"])
                and float(row["maximum_points"]) == float(row["weight"]),
                "projection_compatibility_alias_mismatch",
                "Projection compatibility aliases do not reconstruct from the authoritative exact scorecard fields.",
            )
    core.require(projection["projection_sha256"] == _self_hash(projection, "projection_sha256"), "projection_self_hash_mismatch", "Projection self-hash does not reconstruct.")
    by_id = {row["collection_id"]: row for row in projection["collections"]}
    expected = {"index_records", "source_subjects", "density"} | ({"correction_overlay"} if "correction_overlay" in collections else set())
    core.require(set(by_id) == expected, "projection_collection_set_mismatch", "Projection collection bindings are incomplete or unexpected.")
    for key, value in collections.items():
        schema = "correction-overlay-v1.schema.json" if key == "correction_overlay" else "web-collection-v1.schema.json"
        try:
            core.validate_schema_document(dict(value), schema, f"Generated {key} collection")
        except core.CalculationError:
            if not allow_legacy_display or key != "density" or "fit_rating" in value:
                raise
            expected_rating = None if value.get("fit_percentage") is None else float(value["fit_percentage"]) / 20
            normalized_density = deepcopy(value)
            normalized_density["fit_rating"] = expected_rating
            normalized_density["collection_sha256"] = _self_hash(normalized_density, "collection_sha256")
            core.validate_schema_document(normalized_density, schema, "Predecessor density collection shape")
        if key == "density" and "fit_rating" in value:
            expected_rating = None if value.get("fit_percentage") is None else float(value["fit_percentage"]) / 20
            actual_rating = None if value.get("fit_rating") is None else float(value["fit_rating"])
            core.require(actual_rating == expected_rating, "projection_compatibility_alias_mismatch", "Density fit_rating does not reconstruct from authoritative fit_percentage.")
        hash_field = "overlay_sha256" if key == "correction_overlay" else "collection_sha256"
        core.require(value[hash_field] == _self_hash(value, hash_field) == by_id[key]["content_sha256"], "projection_collection_hash_mismatch", f"{key} content hash does not reconstruct.")
        core.require(_file_hash(json_bytes(value)) == by_id[key]["file_sha256"], "projection_collection_file_hash_mismatch", f"{key} file hash does not reconstruct.")
        if key != "correction_overlay":
            core.require(value["count"] == len(value["items"]) == by_id[key]["count"], "projection_collection_count_mismatch", f"{key} count is inconsistent.")
    records = collections["index_records"]
    core.require([row["delivered_order"] for row in records["items"]] == list(range(records["count"])), "projection_record_order_mismatch", "Index records are not in delivered order.")
    locator_ids = [atomic["locator_id"] for row in records["items"] for display in row["displayed_locators"] for atomic in display["atomic_locators"]]
    core.require(len(locator_ids) == len(set(locator_ids)) == records["counts"]["atomic_locators"], "projection_locator_join_mismatch", "Projected locator identities are incomplete or duplicated.")
    tasks: dict[str, tuple[str, ...]] = {}
    for subject in collections["source_subjects"]["items"]:
        for task in subject["reader_tasks"]:
            identity = tuple(task["subject_ids"])
            core.require(task["task_id"] not in tasks or tasks[task["task_id"]] == identity, "projection_task_membership_mismatch", "A reader task has inconsistent many-to-many membership.")
            tasks[task["task_id"]] = identity
    encoded = json.dumps(core.json_output_value({"projection": projection, "collections": collections}), ensure_ascii=False).lower()
    core.require(not any(token in encoded for token in PROHIBITED_TEXT), "unsafe_public_projection", "Projected output contains a prohibited public-safety token.")
    def keys(value: Any) -> list[str]:
        if isinstance(value, Mapping):
            return [str(key).lower() for key in value] + [item for child in value.values() for item in keys(child)]
        if isinstance(value, list):
            return [item for child in value for item in keys(child)]
        return []
    core.require(not any(token in key for key in keys({"projection": projection, "collections": collections}) for token in SECRET_KEYS), "unsafe_public_projection", "Projected output contains a secret-bearing field.")
