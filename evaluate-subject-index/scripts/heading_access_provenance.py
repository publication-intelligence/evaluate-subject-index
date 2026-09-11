"""Validate and project score-free heading-access causal provenance."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


ADVERSE_STATUSES = frozenset({"minor_issues", "major_issues", "fails"})


class HeadingAccessProvenanceError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(f"{code}:{message}")
        self.code = code
        self.message = message
        self.details = details


def _require(condition: Any, code: str, message: str, details: Any = None) -> None:
    if not condition:
        raise HeadingAccessProvenanceError(code, message, details)


def _evidence_ids(value: Any, *, ignore_causal_findings: bool = False) -> set[str]:
    if isinstance(value, list):
        return set().union(
            *(_evidence_ids(item, ignore_causal_findings=ignore_causal_findings) for item in value),
            set(),
        )
    if not isinstance(value, Mapping):
        return set()
    found = {
        item
        for item in value.get("evidence_ids", [])
        if isinstance(item, str) and item.startswith("EVID-")
    }
    for key, item in value.items():
        if key == "evidence_ids" or (ignore_causal_findings and key == "causal_findings"):
            continue
        found.update(_evidence_ids(item, ignore_causal_findings=ignore_causal_findings))
    return found


def _add_source(
    sources: dict[str, set[str]], source_id: Any, record: Mapping[str, Any]
) -> None:
    if isinstance(source_id, str) and source_id:
        sources.setdefault(source_id, set()).update(
            _evidence_ids(record, ignore_causal_findings=True)
        )


def source_evidence_index(
    structure: Mapping[str, Any],
    locator_documents: Iterable[Mapping[str, Any]] = (),
    missing_documents: Iterable[Mapping[str, Any]] = (),
) -> dict[str, set[str]]:
    """Index stable source IDs to evidence already frozen in their records."""

    sources: dict[str, set[str]] = {}
    for document in locator_documents:
        for record in document.get("judgments", []):
            if not isinstance(record, Mapping):
                continue
            _add_source(sources, record.get("locator_id"), record)
            _add_source(sources, record.get("path_id"), record)
    for document in missing_documents:
        for collection, id_field in (
            ("subject_judgments", "subject_id"),
            ("reader_task_results", "task_id"),
            ("treatment_judgments", "treatment_id"),
        ):
            for record in document.get(collection, []):
                if not isinstance(record, Mapping):
                    continue
                _add_source(sources, record.get(id_field), record)
                for path_id in record.get("matched_path_ids", []):
                    _add_source(sources, path_id, record)
    nodes = {
        record.get("node_id"): record
        for record in structure.get("node_judgments", [])
        if isinstance(record, Mapping) and isinstance(record.get("node_id"), str)
    }
    references = {
        record.get("reference_id"): record
        for record in structure.get("cross_reference_judgments", [])
        if isinstance(record, Mapping) and isinstance(record.get("reference_id"), str)
    }
    decisions = {
        record.get("review_id"): record
        for record in structure.get("v7_architecture_review_decisions", [])
        if isinstance(record, Mapping) and isinstance(record.get("review_id"), str)
    }
    for source_id, record in (*nodes.items(), *references.items(), *decisions.items()):
        _add_source(sources, source_id, record)
        if source_id and source_id.startswith("ARCHREV-"):
            _add_source(sources, record.get("path_id"), record)
    for defect in structure.get("v5_scoring_context", {}).get("defects", []):
        if not isinstance(defect, Mapping):
            continue
        defect_id = defect.get("defect_id")
        _add_source(sources, defect_id, defect)
        related_evidence: set[str] = set()
        for item_id in defect.get("affected_item_ids", []):
            related_evidence.update(sources.get(item_id, set()))
        for decision in decisions.values():
            if defect_id in decision.get("defect_ids", []):
                related_evidence.update(_evidence_ids(decision))
        if isinstance(defect_id, str):
            sources.setdefault(defect_id, set()).update(related_evidence)
    return sources


def causal_provenance_by_node(structure: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the deterministic, display-safe projection in NODE-* order."""

    projected: list[dict[str, Any]] = []
    for node in sorted(
        structure.get("node_judgments", []), key=lambda item: str(item.get("node_id", ""))
    ):
        component = node.get("component_judgments", {}).get(
            "heading_access_architecture", {}
        )
        record = {
            "node_id": node.get("node_id"),
            "status": component.get("status"),
            "causal_findings": deepcopy(component.get("causal_findings", [])),
        }
        if "primary_finding_id" in component:
            record["primary_finding_id"] = component["primary_finding_id"]
            record["primary_basis"] = deepcopy(component["primary_basis"])
        projected.append(record)
    return projected


def build_structure_causal_projection(
    frozen_structure: Mapping[str, Any], projection_input: Mapping[str, Any]
) -> dict[str, Any]:
    """Copy a frozen V5 audit into V6 by adding only score-free causality."""

    _require(
        frozen_structure.get("schema_version") == "structure-audit-v5",
        "causal_projection_source_schema",
        "A score-free causal backfill must start from structure-audit-v5.",
    )
    _require(
        projection_input.get("evaluation_id") == frozen_structure.get("evaluation_id")
        and projection_input.get("candidate_sha256")
        == frozen_structure.get("candidate_sha256"),
        "causal_projection_identity_mismatch",
        "The causal projection input does not bind the frozen structure audit identity.",
    )
    records = projection_input.get("node_causal_provenance", [])
    by_node = {item.get("node_id"): item for item in records}
    nodes = frozen_structure.get("node_judgments", [])
    node_ids = {item.get("node_id") for item in nodes}
    _require(
        len(by_node) == len(records) and set(by_node) == node_ids,
        "causal_projection_node_mismatch",
        "The causal projection must cover every and only frozen NODE-* judgment once.",
        {
            "missing": sorted(str(item) for item in node_ids - set(by_node)),
            "unexpected": sorted(str(item) for item in set(by_node) - node_ids),
        },
    )
    result = deepcopy(frozen_structure)
    result["schema_version"] = "structure-audit-v6"
    for node in result["node_judgments"]:
        component = node["component_judgments"]["heading_access_architecture"]
        projected = by_node[node["node_id"]]
        _require(
            projected.get("status") == component.get("status"),
            "causal_projection_status_mismatch",
            "A score-free causal projection cannot change a heading-access status.",
            {"node_id": node["node_id"]},
        )
        component["causal_findings"] = deepcopy(projected["causal_findings"])
        if "primary_finding_id" in projected:
            component["primary_finding_id"] = projected["primary_finding_id"]
            component["primary_basis"] = deepcopy(projected["primary_basis"])
    return result


def validate_causal_projection_source(
    projected_structure: Mapping[str, Any], frozen_structure: Mapping[str, Any]
) -> None:
    """Prove the projection differs only by schema tag and causal metadata."""

    reconstructed = deepcopy(projected_structure)
    reconstructed.pop("causal_projection", None)
    reconstructed["schema_version"] = "structure-audit-v5"
    for node in reconstructed.get("node_judgments", []):
        component = node.get("component_judgments", {}).get(
            "heading_access_architecture", {}
        )
        for field in ("causal_findings", "primary_finding_id", "primary_basis"):
            component.pop(field, None)
    _require(
        reconstructed == frozen_structure,
        "causal_projection_changed_scoring_fields",
        "The causal projection changes fields other than score-free heading-access provenance.",
    )


def validate_heading_access_provenance(
    structure: Mapping[str, Any],
    locator_documents: Iterable[Mapping[str, Any]] = (),
    missing_documents: Iterable[Mapping[str, Any]] = (),
) -> None:
    """Reject generic-only adverse judgments and unresolved source/evidence IDs."""

    _require(
        structure.get("schema_version") == "structure-audit-v6",
        "heading_access_provenance_schema",
        "Heading-access causal provenance requires structure-audit-v6.",
    )
    sources = source_evidence_index(structure, locator_documents, missing_documents)
    all_evidence = set().union(*sources.values(), set())
    seen_finding_ids: set[str] = set()
    for node in structure.get("node_judgments", []):
        node_id = node.get("node_id")
        component = node.get("component_judgments", {}).get(
            "heading_access_architecture", {}
        )
        findings = component.get("causal_findings", [])
        if component.get("status") in ADVERSE_STATUSES:
            _require(
                bool(findings),
                "generic_only_adverse_heading_access",
                "Every adverse heading_access_architecture judgment requires at least one structured causal finding.",
                {"node_id": node_id, "status": component.get("status")},
            )
        finding_ids: set[str] = set()
        for finding in findings:
            finding_id = finding.get("finding_id")
            _require(
                finding_id not in seen_finding_ids,
                "duplicate_heading_access_finding_id",
                "Heading-access finding IDs must be globally unique.",
                finding_id,
            )
            seen_finding_ids.add(finding_id)
            finding_ids.add(finding_id)
            source_ids = set(finding.get("source_ids", []))
            unknown_sources = source_ids - set(sources)
            _require(
                not unknown_sources,
                "unknown_heading_access_source_id",
                "A heading-access finding cites a source ID absent from the frozen artifacts.",
                {"finding_id": finding_id, "source_ids": sorted(unknown_sources)},
            )
            evidence_ids = set(finding.get("evidence_ids", []))
            unknown_evidence = evidence_ids - all_evidence
            _require(
                not unknown_evidence,
                "unknown_heading_access_evidence_id",
                "A heading-access finding cites an evidence ID absent from the frozen artifacts.",
                {"finding_id": finding_id, "evidence_ids": sorted(unknown_evidence)},
            )
            linked_evidence = set().union(
                *(sources.get(source_id, set()) for source_id in source_ids), set()
            )
            unlinked_evidence = evidence_ids - linked_evidence
            _require(
                not unlinked_evidence,
                "unlinked_heading_access_evidence_id",
                "A heading-access finding's evidence must be carried by at least one of its cited source records.",
                {"finding_id": finding_id, "evidence_ids": sorted(unlinked_evidence)},
            )
        primary_id = component.get("primary_finding_id")
        if primary_id is not None:
            _require(
                primary_id in finding_ids,
                "heading_access_primary_finding_mismatch",
                "A primary heading-access finding must identify one finding on the same node.",
                {"node_id": node_id, "primary_finding_id": primary_id},
            )
            basis = component.get("primary_basis", {}).get("basis")
            _require(
                basis in {"deterministic_rule", "explicit_adjudication"},
                "heading_access_primary_basis_required",
                "Primary causation requires a deterministic rule or explicit adjudication.",
                {"node_id": node_id, "primary_finding_id": primary_id},
            )
            basis_id = component.get("primary_basis", {}).get("basis_id")
            if basis == "explicit_adjudication":
                _require(
                    isinstance(basis_id, str)
                    and basis_id.startswith("ARCHREV-")
                    and basis_id in sources,
                    "heading_access_primary_adjudication_id_mismatch",
                    "An explicitly adjudicated primary cause must cite an existing ARCHREV-* decision.",
                    {"node_id": node_id, "basis_id": basis_id},
                )
