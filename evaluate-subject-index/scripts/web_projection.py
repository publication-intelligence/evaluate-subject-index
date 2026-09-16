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
                    "assessment": deepcopy(locator_items[locator_id]),
                    "adjusted_assessment": None,
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
            expected_treatments.append({**deepcopy(treatment), "source_page_label": matches[0]["source_page_label"]})
        output.append({
            "source_order": source_order,
            "subject_id": subject["subject_id"], "label": subject["label"], "priority": subject["priority"],
            "meaning": subject["meaning"], "stance": subject["stance"], "acceptable_access": deepcopy(subject["acceptable_access"]),
            "chapter_provenance": deepcopy(subject.get("chapter_provenance", [])),
            "source_chunk_ids": deepcopy(subject.get("source_chunk_ids", subject.get("chapter_provenance", []))),
            "assessment": deepcopy(assessments[subject["subject_id"]]),
            "audit_judgment": deepcopy(subject_judgments[subject["subject_id"]]),
            "reader_tasks": [{"task_id": task["task_id"], "question": task["question"], "subject_ids": deepcopy(task["subject_ids"]), "task_basis": deepcopy(task.get("task_basis", task.get("source_fields", []))), "result": deepcopy(task_results[task["task_id"]])} for task in tasks.get(subject["subject_id"], [])],
            "expected_treatments": expected_treatments,
        })
    return collection("source_subjects", output, "frozen benchmark subject order", counts={
        "source_subjects": len(output), "reader_tasks": len(task_results), "expected_treatments": len(treatment_rows),
    })


def build_density(structure: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Any]:
    chunks = {row["chunk_id"]: row for row in manifest["chunks"]}
    findings = {row["chunk_id"]: row for row in structure["density"]["distribution_findings"]}
    rows = []
    for source_order, measurement in enumerate(structure["density"]["chapter_measurements"]):
        chunk = chunks[measurement["chunk_id"]]
        finding = findings.get(measurement["chunk_id"], {})
        path_finding = finding.get("finding", finding.get("path_finding", "not_measured"))
        occurrence_finding = finding.get("locator_occurrence_finding", "not_measured")
        rows.append({
            "source_order": source_order, "chunk_id": measurement["chunk_id"], "title": chunk["title"],
            "source_units": deepcopy(chunk["source_units"]), "owned_document_page_ranges": deepcopy(chunk["owned_document_page_ranges"]),
            **deepcopy(measurement),
            "canonical_fit_judgment": {"combined": "within_acceptable_bands" if path_finding == "within_path_band" and occurrence_finding == "within_occurrence_band" else "outside_one_or_more_acceptable_bands", "path_rate": path_finding, "locator_occurrence_rate": occurrence_finding, "interpretation": finding.get("interpretation", "Descriptive distribution evidence."), "automatic_defect": False},
        })
    density = structure["density"]
    return collection("density", rows, "chunk manifest packet order", policy_status=density["policy_status"], measurement_level=density["measurement_level"], targets=deepcopy(density["targets"]), maximum_score_contribution=density["maximum_score_contribution"], fit_rating=density.get("fit_rating"))


def _artifact_binding(record: Mapping[str, Any]) -> dict[str, Any]:
    return {"artifact_path": record["path"], "sha256": record["sha256"], "schema_version": record.get("schema_version"), "availability": "canonical_registered_input"}


def build_bundle(*, result: Mapping[str, Any], result_record: Mapping[str, Any], report: Mapping[str, Any], report_record: Mapping[str, Any], calculation: Mapping[str, Any], calculation_record: Mapping[str, Any], items: Mapping[str, Any], items_record: Mapping[str, Any], candidate: Mapping[str, Any], candidate_record: Mapping[str, Any], inventory: Mapping[str, Any], inventory_record: Mapping[str, Any], benchmark: Mapping[str, Any], benchmark_record: Mapping[str, Any], structure: Mapping[str, Any], structure_record: Mapping[str, Any], manifest: Mapping[str, Any], manifest_record: Mapping[str, Any], missing_documents: Sequence[Mapping[str, Any]], missing_records: Sequence[Mapping[str, Any]], overlay: Mapping[str, Any] | None, overlay_record: Mapping[str, Any] | None) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    collections = {
        "index_records": public_safe(build_index_records(candidate, inventory, items)),
        "source_subjects": public_safe(build_source_subjects(benchmark, items, missing_documents)),
        "density": public_safe(build_density(structure, manifest)),
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
    readiness = {"status": "not_publication_ready" if any(row["triggered"] for row in gates) else "publication_ready", "triggered_gate_ids": [row["gate_id"] for row in gates if row["triggered"]]}
    scorecard = [{"dimension_id": row["dimension_id"], "rating": float(row["dimension_percentage"]) / 20, "awarded_points": float(row["weighted_contribution"]), "maximum_points": row["weight"], "formula_id": row["formula_id"]} for row in report["scorecard"]]
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
        "projection_role": "deterministic_public_safe_display_projection", "evaluation_id": result["evaluation_id"],
        "view_selection": {"authoritative_view_id": "canonical_as_delivered", "primary_view_id": "canonical_as_delivered", "default_display_view_id": "canonical_as_delivered", "display_view_rationale": "The canonical as-delivered result is authoritative."},
        "score_views": {"canonical_source_adjustment_status": report["score_views"]["adjustment_status"], "projection_adjustment_status": "confirmed_representation_adjustment_applied" if overlay_applicable else "not_applicable", "total_delta": 0, "views": [{"view_id": "canonical_as_delivered", "label": "Canonical as delivered", "view_kind": "observed", "role": "authoritative_primary_observation", "score": result["overall_percentage"], "maximum": 100, "scorecard": scorecard, "critical_gates": gates, "readiness": readiness, "provenance_artifacts": [_artifact_binding(result_record), _artifact_binding(report_record), _artifact_binding(calculation_record)]}]},
        "correction_outcomes": correction_outcomes,
        "item_summaries": {"observed": deepcopy(items["summary"])}, "collections": bindings,
        "provenance": {"source_artifacts": [_artifact_binding(row) for row in sorted(source_records, key=lambda row: row["path"])], "source_sha256": result["provenance"]["source_sha256"], "benchmark_sha256": result["provenance"]["benchmark_sha256"], "judgment_policy_sha256": result["provenance"]["judgment_policy_sha256"], "rubric_version": result["provenance"]["rubric_version"], "dimension_calculation_profile": result["provenance"]["dimension_calculation_profile"], "projection_metadata_sha256": result["projection_metadata"]["projection_metadata_sha256"], "calculation_sha256": result["dimension_calculations"]["calculation_sha256"], "missing_access_audit_set_sha256": items["evidence_identity"]["missing_access_audit_set_sha256"], "correction_overlay_sha256": overlay.get("overlay_sha256") if overlay_applicable else None},
        "density_denominator": {"indexable_source_words": sum(row["indexable_source_words"] for row in structure["density"]["chapter_measurements"]), "unit": "words"},
        "public_safety": {"source_excerpts_included": False, "restricted_files_included": False, "private_layout_evidence_included": False, "absolute_paths_included": False, "source_subject_summaries_are_synthesized_not_quoted": True},
        "limitations": ["Aggregate scores come from the authoritative V8 calculation, not reconstructed item grades.", "Source excerpts and private layout evidence are excluded."],
    }
    projection["projection_sha256"] = _self_hash(projection, "projection_sha256")
    return projection, collections


def validate_bundle(projection: Mapping[str, Any], collections: Mapping[str, Mapping[str, Any]]) -> None:
    core.validate_schema_document(dict(projection), "web-projection-v1.schema.json", "Generated canonical web projection")
    core.require(projection["projection_sha256"] == _self_hash(projection, "projection_sha256"), "projection_self_hash_mismatch", "Projection self-hash does not reconstruct.")
    by_id = {row["collection_id"]: row for row in projection["collections"]}
    expected = {"index_records", "source_subjects", "density"} | ({"correction_overlay"} if "correction_overlay" in collections else set())
    core.require(set(by_id) == expected, "projection_collection_set_mismatch", "Projection collection bindings are incomplete or unexpected.")
    for key, value in collections.items():
        schema = "correction-overlay-v1.schema.json" if key == "correction_overlay" else "web-collection-v1.schema.json"
        core.validate_schema_document(dict(value), schema, f"Generated {key} collection")
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
