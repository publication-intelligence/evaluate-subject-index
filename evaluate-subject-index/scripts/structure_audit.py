"""Native V8 structure-ledger validation and pass materialization."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping


DISPLAYED_LOCATOR_THRESHOLD = 6
CONTINUOUS_RANGE_SPAN_THRESHOLD = 10
NODE_COMPONENTS = (
    "conceptual_stance_fidelity",
    "heading_access_architecture",
    "mechanics_consistency",
)


class StructureAuditError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def _require(condition: Any, code: str, message: str, details: Any = None) -> None:
    if not condition:
        raise StructureAuditError(code, message, details)


def id_set_hash(ids: list[str]) -> str:
    payload = json.dumps({"ids": sorted(ids)}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _unique_records(records: Any, field: str, label: str) -> dict[str, dict[str, Any]]:
    _require(isinstance(records, list), "invalid_structure_ledger", f"{label} must be an array.")
    result: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        _require(isinstance(record, dict), "invalid_structure_ledger", f"{label}[{index}] must be an object.")
        identity = record.get(field)
        _require(isinstance(identity, str) and identity not in result, "duplicate_or_invalid_id", f"{label} identities must be unique strings.", identity)
        result[identity] = record
    return result


def _validate_architecture_review(
    review: Mapping[str, Any],
    *,
    node_ids: set[str],
    path_ids: set[str],
    defect_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    path_id = review["path_id"]
    _require(path_id in path_ids, "unexpected_ledger_items", "Architecture review cites a path outside the candidate denominator.", path_id)
    terminal_node_id = review["terminal_node_id"]
    _require(terminal_node_id in node_ids, "unexpected_ledger_items", "Architecture review cites a node outside the candidate denominator.", terminal_node_id)
    displays = review["displayed_locators"]
    _require(review["displayed_locator_count"] == len(displays), "displayed_locator_count_mismatch", "Displayed locator count must equal the number of DISPLAY-* rows.", path_id)
    flattened: list[str] = []
    range_spans: list[int] = []
    display_ids: set[str] = set()
    for display in displays:
        display_id = display["display_id"]
        atomic_ids = display["expanded_atomic_locator_ids"]
        _require(display_id not in display_ids, "duplicate_or_invalid_id", "Displayed locator IDs must be unique within a path.", display_id)
        display_ids.add(display_id)
        _require(display["atomic_assignment_count"] == len(atomic_ids), "atomic_assignment_count_mismatch", "Each displayed locator must own exactly its declared atomic assignments.", display_id)
        flattened.extend(atomic_ids)
        if display["kind"] == "singleton":
            _require(len(atomic_ids) == 1 and display["range_id"] is None and display["range_endpoints"] is None and display["inclusive_range_span"] is None, "singleton_grouping_invalid", "A singleton must own one atomic assignment and no range fields.", display_id)
        else:
            endpoints = display["range_endpoints"]
            span = display["inclusive_range_span"]
            _require(isinstance(endpoints, dict) and isinstance(span, int) and display["range_id"] is not None, "range_grouping_incomplete", "A range requires its identity, endpoints, and inclusive span.", display_id)
            start = endpoints.get("start", {}).get("document_page")
            end = endpoints.get("end", {}).get("document_page")
            _require(isinstance(start, int) and isinstance(end, int) and end >= start and span == end - start + 1 and span == len(atomic_ids), "range_span_mismatch", "A range span must reconstruct from endpoints and owned assignments.", display_id)
            range_spans.append(span)
    _require(flattened == review["expanded_atomic_locator_ids"] and len(flattened) == len(set(flattened)), "display_assignment_binding_mismatch", "Displayed-to-atomic ownership must flatten exactly once in delivered order.", path_id)
    _require(review["atomic_assignment_count"] == len(flattened), "atomic_assignment_count_mismatch", "Path atomic count must equal its complete flattened ownership list.", path_id)
    maximum_span = max(range_spans, default=0)
    long_string = len(displays) > DISPLAYED_LOCATOR_THRESHOLD
    long_range = maximum_span > CONTINUOUS_RANGE_SPAN_THRESHOLD
    _require(review["maximum_range_span"] == maximum_span and review["long_displayed_locator_string_review_trigger"] is long_string and review["long_continuous_range_review_trigger"] is long_range, "architecture_trigger_mismatch", "Architecture triggers must reconstruct from displayed count and inclusive range span.", path_id)
    _require(long_string or long_range, "untriggered_architecture_review", "Only numerically triggered paths belong in triggered_reviews.", path_id)

    status = review["review_status"]
    facts = [
        review["conceptually_distinguishable_treatments"],
        review["meaningful_subheadings_or_access_routes"],
        review["material_scanning_or_retrieval_impairment"],
        review["subdivision_is_conceptual_not_trivial"],
    ]
    defect_ids = review["defect_ids"]
    if status == "defect_confirmed":
        _require(all(value is True for value in facts) and bool(defect_ids) and bool(review["evidence_ids"]), "numeric_trigger_cannot_create_architecture_defect", "A trigger becomes a defect only with all semantic findings and bound evidence.", path_id)
        for defect_id in defect_ids:
            defect = defect_by_id.get(defect_id)
            _require(defect is not None and defect.get("dimension_owner") == "findability_navigation" and defect.get("code") in {"HED", "SUB"} and bool({path_id, terminal_node_id} & set(defect.get("affected_item_ids", []))), "architecture_defect_binding_mismatch", "A confirmed architecture defect must bind this path or terminal node.", defect_id)
    elif status == "reviewed_no_defect":
        _require(not defect_ids and bool(review["evidence_ids"]) and not all(value is True for value in facts), "reviewed_no_defect_mismatch", "A passing review requires evidence, no defect, and at least one failed defect prerequisite.", path_id)
    else:
        _require(not defect_ids and not review["evidence_ids"] and all(value is None for value in facts), "unreviewed_architecture_mismatch", "An unreviewed trigger must remain explicitly uncertain.", path_id)


def validate_structure_audit_semantics(structure: Mapping[str, Any]) -> None:
    """Validate exact denominator, exception-ledger, and architecture invariants."""

    _require(structure.get("schema_version") in {"structure-audit-v5", "structure-audit-v6"}, "unsupported_structure_audit_schema", "Current V8 structure processing requires structure-audit-v5 or structure-audit-v6.")
    denominator = structure["candidate_denominator"]
    node_records = _unique_records(denominator["nodes"], "node_id", "candidate_denominator.nodes")
    node_ids = list(node_records)
    reference_ids = denominator["cross_reference_ids"]
    path_ids = denominator["locator_bearing_path_ids"]
    _require(all(isinstance(item, str) for item in reference_ids) and len(reference_ids) == len(set(reference_ids)), "duplicate_or_invalid_id", "Cross-reference denominator IDs must be unique strings.")
    _require(all(isinstance(item, str) for item in path_ids) and len(path_ids) == len(set(path_ids)), "duplicate_or_invalid_id", "Locator-bearing path denominator IDs must be unique strings.")
    _require(denominator["node_count"] == len(node_ids) and denominator["cross_reference_count"] == len(reference_ids) and denominator["locator_bearing_path_count"] == len(path_ids), "candidate_denominator_count_mismatch", "Candidate denominator counts must reconstruct from stable identity arrays.")
    for ids, field in (
        (node_ids, "node_id_set_sha256"),
        (reference_ids, "cross_reference_id_set_sha256"),
        (path_ids, "locator_bearing_path_id_set_sha256"),
    ):
        _require(denominator[field] == id_set_hash(ids), "candidate_denominator_hash_mismatch", f"{field} must reconstruct from its stable IDs.")

    node_exceptions = _unique_records(structure["node_judgments"], "node_id", "node_judgments")
    reference_exceptions = _unique_records(structure["cross_reference_judgments"], "reference_id", "cross_reference_judgments")
    _require(set(node_exceptions) <= set(node_ids), "unexpected_ledger_items", "Node judgments contain identities outside the candidate denominator.", sorted(set(node_exceptions) - set(node_ids)))
    _require(set(reference_exceptions) <= set(reference_ids), "unexpected_ledger_items", "Cross-reference judgments contain identities outside the candidate denominator.", sorted(set(reference_exceptions) - set(reference_ids)))
    for node_id, record in node_exceptions.items():
        statuses = [record["component_judgments"][component]["status"] for component in NODE_COMPONENTS]
        _require(any(status != "passes" for status in statuses), "default_pass_record_forbidden", "node_judgments stores exceptions only; omit all-pass nodes.", node_id)
    for reference_id, record in reference_exceptions.items():
        _require(record["judgment"] != "supported", "default_pass_record_forbidden", "cross_reference_judgments stores exceptions only; omit supported references.", reference_id)

    attestation = structure["full_scope_attestation"]
    pilot_pass_nodes = set(attestation["pilot_pass_node_ids"])
    pilot_supported_references = set(attestation["pilot_supported_cross_reference_ids"])
    _require(pilot_pass_nodes <= set(node_ids) and not pilot_pass_nodes & set(node_exceptions), "pilot_pass_ledger_mismatch", "Pilot pass-node IDs must be unique denominator members absent from the exception ledger.")
    _require(pilot_supported_references <= set(reference_ids) and not pilot_supported_references & set(reference_exceptions), "pilot_pass_ledger_mismatch", "Pilot supported-reference IDs must be unique denominator members absent from the exception ledger.")
    if structure["audit_mode"] == "full":
        _require(attestation == {**attestation, "complete": True, "all_nodes_reviewed": True, "all_cross_references_reviewed": True, "all_locator_bearing_paths_checked_for_triggers": True, "unlisted_node_disposition": "passes", "unlisted_cross_reference_disposition": "supported", "pilot_pass_node_ids": [], "pilot_supported_cross_reference_ids": []}, "full_scope_attestation_mismatch", "Full mode requires complete scope and treats omitted denominator records as attested passes.")
        _require(
            all(record["component_judgments"][component]["status"] != "not_measured" for record in node_exceptions.values() for component in NODE_COMPONENTS)
            and all(record["judgment"] != "not_measured" for record in reference_exceptions.values()),
            "full_scope_contains_not_measured",
            "Full mode cannot contain not-measured structure exceptions.",
        )
    else:
        _require(attestation["complete"] is False and attestation["unlisted_node_disposition"] == "not_measured" and attestation["unlisted_cross_reference_disposition"] == "not_measured", "pilot_scope_attestation_mismatch", "Pilot mode must remain incomplete and preserve unlisted denominator items as not measured.")
        measured_node_ids = pilot_pass_nodes | {
            node_id for node_id, record in node_exceptions.items()
            if all(record["component_judgments"][component]["status"] != "not_measured" for component in NODE_COMPONENTS)
        }
        measured_reference_ids = pilot_supported_references | {
            reference_id for reference_id, record in reference_exceptions.items()
            if record["judgment"] != "not_measured"
        }
        _require(attestation["all_nodes_reviewed"] is (measured_node_ids == set(node_ids)), "pilot_scope_attestation_mismatch", "Pilot node coverage flag must reconstruct from explicit passes and measured exceptions.")
        _require(attestation["all_cross_references_reviewed"] is (measured_reference_ids == set(reference_ids)), "pilot_scope_attestation_mismatch", "Pilot cross-reference coverage flag must reconstruct from explicit passes and measured exceptions.")
        _require(not (attestation["all_nodes_reviewed"] and attestation["all_cross_references_reviewed"] and attestation["all_locator_bearing_paths_checked_for_triggers"]), "pilot_scope_attestation_mismatch", "An audit with complete coverage of every structure denominator must use full mode.")

    metrics = structure["metrics"]
    _require(metrics["page_bearing_paths"] == len(path_ids) and metrics["cross_references"] == len(reference_ids) and metrics["total_nodes"] == len(node_ids) and metrics["total_paths"] >= metrics["page_bearing_paths"], "candidate_denominator_metric_mismatch", "Structure metrics must agree with the bound candidate denominator.")

    defects = _unique_records(structure["defects"], "defect_id", "defects")
    _unique_records(structure["strengths"], "strength_id", "strengths")
    _unique_records(structure["uncertainties"], "uncertainty_id", "uncertainties")
    architecture = structure["locator_architecture"]
    _require(
        architecture["thresholds"] == {
            "long_displayed_locator_string": {"operator": ">", "displayed_locator_count": DISPLAYED_LOCATOR_THRESHOLD},
            "long_continuous_range": {"operator": ">", "inclusive_range_span": CONTINUOUS_RANGE_SPAN_THRESHOLD},
            "numeric_trigger_is_automatic_defect": False,
        },
        "architecture_threshold_mismatch",
        "The native V8 architecture thresholds are fixed.",
    )
    reviews = _unique_records(architecture["triggered_reviews"], "path_id", "locator_architecture.triggered_reviews")
    _require(sorted(reviews) == sorted(architecture["triggered_path_ids"]), "architecture_review_coverage_mismatch", "Every triggered path must have exactly one review row.")
    review_ids = [review["review_id"] for review in reviews.values()]
    display_ids = [display["display_id"] for review in reviews.values() for display in review["displayed_locators"]]
    range_ids = [display["range_id"] for review in reviews.values() for display in review["displayed_locators"] if display["range_id"] is not None]
    atomic_ids = [locator_id for review in reviews.values() for locator_id in review["expanded_atomic_locator_ids"]]
    for ids, label in ((review_ids, "architecture review"), (display_ids, "displayed locator"), (range_ids, "range"), (atomic_ids, "architecture atomic locator")):
        _require(len(ids) == len(set(ids)), "duplicate_or_invalid_id", f"{label.title()} IDs must be unique across the structure ledger.")
    for review in reviews.values():
        _validate_architecture_review(review, node_ids=set(node_ids), path_ids=set(path_ids), defect_by_id=defects)
    if structure["audit_mode"] == "full":
        unresolved = sorted(path_id for path_id, review in reviews.items() if review["review_status"] == "not_reviewed")
        _require(not unresolved, "architecture_review_incomplete", "Full mode requires a decision for every triggered architecture review.", unresolved)
    else:
        for review in reviews.values():
            if review["review_status"] != "not_reviewed":
                continue
            terminal_node_id = review["terminal_node_id"]
            _require(terminal_node_id not in pilot_pass_nodes, "unreviewed_architecture_marked_pass", "An unresolved pilot architecture trigger cannot be attested as a passing terminal node.", review["path_id"])
            if terminal_node_id in node_exceptions:
                status = node_exceptions[terminal_node_id]["component_judgments"]["heading_access_architecture"]["status"]
                _require(status in {"uninspectable", "not_measured"}, "unreviewed_architecture_missing_uncertainty", "An unresolved pilot architecture trigger must carry heading-access uncertainty.", review["path_id"])


def materialize_structure_records(structure: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    """Expand attested passes only in memory for unchanged arithmetic."""

    validate_structure_audit_semantics(structure)
    denominator = structure["candidate_denominator"]
    attestation = structure["full_scope_attestation"]
    exceptions = {item["node_id"]: deepcopy(item) for item in structure["node_judgments"]}
    pilot_pass_nodes = set(attestation["pilot_pass_node_ids"])
    nodes: list[dict[str, Any]] = []
    node_not_measured: list[str] = []
    for identity in denominator["nodes"]:
        node_id = identity["node_id"]
        if node_id in exceptions:
            record = exceptions[node_id]
            record.update(deepcopy(identity))
            nodes.append(record)
        elif attestation["unlisted_node_disposition"] == "passes" or node_id in pilot_pass_nodes:
            pass_component = {"status": "passes", "summary": "Covered by the structure-scope pass attestation.", "evidence_ids": list(attestation["evidence_ids"])}
            nodes.append({**deepcopy(identity), "component_judgments": {component: deepcopy(pass_component) for component in NODE_COMPONENTS}, "summary": "Attested pass.", "confidence": "high", "evidence_ids": list(attestation["evidence_ids"])})
        else:
            node_not_measured.append(node_id)

    reference_exceptions = {item["reference_id"]: deepcopy(item) for item in structure["cross_reference_judgments"]}
    pilot_supported = set(attestation["pilot_supported_cross_reference_ids"])
    references: list[dict[str, Any]] = []
    reference_not_measured: list[str] = []
    for reference_id in denominator["cross_reference_ids"]:
        if reference_id in reference_exceptions:
            references.append(reference_exceptions[reference_id])
        elif attestation["unlisted_cross_reference_disposition"] == "supported" or reference_id in pilot_supported:
            references.append({"reference_id": reference_id, "judgment": "supported", "summary": "Covered by the structure-scope pass attestation.", "severity": "none", "confidence": "high", "evidence_ids": list(attestation["evidence_ids"])})
        else:
            reference_not_measured.append(reference_id)
    return nodes, references, node_not_measured, reference_not_measured
