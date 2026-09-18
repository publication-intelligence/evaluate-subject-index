#!/usr/bin/env python3
"""Register reviewed destinations for supported references omitted from the exception ledger."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json

import study_comparison as study
from schema_validation import schema_errors


SCHEMA = "subject-index-v10-reviewed-cross-reference-bindings-v1"
ARTIFACT = "reviewed_cross_reference_bindings"


def _candidate_references(candidate):
    rows = [row for record in candidate["records"] for row in record.get("cross_references", [])]
    result = {row["reference_id"]: row for row in rows}
    study.require(len(result) == len(rows), "Candidate contains duplicate cross-reference IDs")
    return result


def validate_document(
    document,
    *,
    evaluation_id,
    candidate_sha256,
    normalized_candidate_sha256,
    item_inventory_sha256,
    candidate,
    inventory,
    structure,
    structure_path,
    structure_file_sha256,
):
    """Validate a complete, score-neutral destination overlay against exact source bytes."""
    study.require(
        not schema_errors(document, "reviewed-cross-reference-bindings-v10.schema.json", profile="v10"),
        "Invalid reviewed cross-reference destination receipt",
    )
    study.require(document["evaluation_id"] == evaluation_id, "Reviewed bindings use another evaluation")
    study.require(document["candidate_sha256"] == candidate_sha256 == candidate["candidate_sha256"] == inventory["candidate_sha256"], "Reviewed bindings use another candidate")
    study.require(document["normalized_candidate_sha256"] == normalized_candidate_sha256, "Reviewed bindings do not bind the registered normalized candidate bytes")
    study.require(document["item_inventory_sha256"] == item_inventory_sha256, "Reviewed bindings do not bind the registered item inventory bytes")
    binding = document["structure_binding"]
    study.require(binding["path"] == structure_path and binding["sha256"] == structure_file_sha256, "Reviewed bindings do not bind the selected structure audit bytes")
    study.require(structure["evaluation_id"] == evaluation_id and structure["candidate_sha256"] == candidate_sha256, "Selected structure audit uses another evaluation or candidate")
    study.require(document["binding_set_sha256"] == study.digest(document["bindings"]), "Reviewed binding-set hash does not reconstruct")

    stamp = datetime.fromisoformat(document["reviewed_at"].replace("Z", "+00:00"))
    study.require(stamp.utcoffset() is not None and stamp <= datetime.now(timezone.utc), "Reviewed bindings timestamp must be timezone-aware and not in the future")

    candidate_references = _candidate_references(candidate)
    inventory_rows = inventory["cross_references"]
    inventory_references = {row["reference_id"]: row for row in inventory_rows}
    study.require(len(inventory_references) == len(inventory_rows), "Item inventory contains duplicate cross-reference IDs")
    delivered = set(structure["candidate_denominator"]["cross_reference_ids"])
    study.require(delivered == set(inventory_references) == set(candidate_references), "Structure, inventory, and candidate cross-reference populations differ")

    exceptions = {row["reference_id"] for row in structure.get("cross_reference_judgments", [])}
    attestation = structure["full_scope_attestation"]
    if attestation["unlisted_cross_reference_disposition"] == "supported":
        supported = delivered - exceptions
    else:
        supported = set(attestation.get("pilot_supported_cross_reference_ids", []))

    eligible = {
        reference_id
        for reference_id in supported
        if inventory_references[reference_id].get("target_path_id") is None
        and candidate_references[reference_id].get("target_path_id") is None
    }
    rows = document["bindings"]
    row_ids = [row["reference_id"] for row in rows]
    study.require(len(row_ids) == len(set(row_ids)), "Reviewed bindings contain duplicate reference IDs")
    study.require(set(row_ids) == eligible, "Reviewed bindings must cover the exact complete unresolved supported-reference set")

    uncertainty_scopes = {row["uncertainty_id"]: row for row in structure.get("uncertainty_gate_scopes", [])}
    ambiguous = set()
    for uncertainty in structure.get("uncertainties", []):
        scope = uncertainty_scopes.get(uncertainty["uncertainty_id"])
        if scope is None or scope["scope"] == "unknown":
            ambiguous.update(set(uncertainty["affected_item_ids"]) & eligible)
        elif scope["scope"] == "cross_reference_destination":
            ambiguous.update(set(scope["target_ids"]) & eligible)
    study.require(not ambiguous, "Reviewed bindings cannot clear unresolved or ambiguous reference destinations")

    candidate_paths = {record["path_id"] for record in candidate["records"]}
    inventory_paths = {row["path_id"] for row in inventory["paths"]}
    study.require(candidate_paths == inventory_paths, "Candidate and inventory path populations differ")
    for row in rows:
        reference_id = row["reference_id"]
        inventory_reference = inventory_references[reference_id]
        candidate_reference = candidate_references[reference_id]
        study.require(
            row["reference_type"] == inventory_reference["reference_type"] == candidate_reference["type"],
            f"Reviewed reference type differs for {reference_id}",
        )
        study.require(
            row["target_display"] == inventory_reference["target_display"] == candidate_reference["target"],
            f"Reviewed target text differs for {reference_id}",
        )
        study.require(
            set(row["resolved_path_ids"]) <= inventory_paths,
            f"Reviewed destination cites a nonexistent candidate path for {reference_id}",
        )
    return {row["reference_id"]: deepcopy(row) for row in rows}


def bound_bindings(state, state_path, *, structure, structure_path):
    records = [row for row in state["artifacts"] if row.get("artifact_type") == ARTIFACT]
    if not records:
        return {"bindings": {}, "receipt_file_sha256": None, "binding_set_sha256": None, "record": None}
    study.require(len(records) == 1 and records[0].get("schema_version") == SCHEMA, "Exactly one registered reviewed cross-reference binding receipt may apply")
    candidate, candidate_record = study.registered_document(state, state_path, "candidate_normalization", "candidate-index-v2")
    inventory, inventory_record = study.registered_document(state, state_path, "candidate_normalization", "subject-index-item-inventory-v2")
    document = study.bound_document(state_path.parent, records[0])
    relative_structure = Path(structure_path).resolve().relative_to(state_path.parent.resolve()).as_posix()
    bindings = validate_document(
        document,
        evaluation_id=state["evaluation_id"],
        candidate_sha256=state["candidate"]["candidate_sha256"],
        normalized_candidate_sha256=candidate_record["sha256"],
        item_inventory_sha256=inventory_record["sha256"],
        candidate=candidate,
        inventory=inventory,
        structure=structure,
        structure_path=relative_structure,
        structure_file_sha256=study.file_digest(structure_path),
    )
    return {
        "bindings": bindings,
        "receipt_file_sha256": records[0]["sha256"],
        "binding_set_sha256": document["binding_set_sha256"],
        "record": deepcopy(records[0]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    from state_cli import evaluation_mutation_lock, now, save_state, validate_state
    from study_cli import record
    try:
        state_path = Path(args.state).resolve()
        source = Path(args.input).resolve()
        with evaluation_mutation_lock(state_path):
            state = study.read(state_path)
            errors, _ = validate_state(state, state_path=state_path)
            study.require(not errors, "Invalid V10 state")
            study.require(
                state["stages"]["missing_access_audit"]["status"] == "completed"
                and state["stages"]["structure_audit"]["status"] == "not_started",
                "Register reviewed cross-reference bindings after missing-access audit and before structure registration",
            )
            study.require(source.is_relative_to(state_path.parent), "Reviewed bindings must be inside the evaluation directory")
            relative = source.relative_to(state_path.parent).as_posix()
            study.require(
                not any(row["path"] == relative or row.get("artifact_type") == ARTIFACT for row in state["artifacts"]),
                "Reviewed bindings must be one new in-evaluation artifact",
            )
            document = study.read(source)
            structure_path = state_path.parent / document["structure_binding"]["path"]
            structure = study.bound_document(state_path.parent, document["structure_binding"])
            canonical_structure_path = structure_path.resolve().relative_to(state_path.parent.resolve()).as_posix()
            candidate, candidate_record = study.registered_document(state, state_path, "candidate_normalization", "candidate-index-v2")
            inventory, inventory_record = study.registered_document(state, state_path, "candidate_normalization", "subject-index-item-inventory-v2")
            bindings = validate_document(
                document,
                evaluation_id=state["evaluation_id"],
                candidate_sha256=state["candidate"]["candidate_sha256"],
                normalized_candidate_sha256=candidate_record["sha256"],
                item_inventory_sha256=inventory_record["sha256"],
                candidate=candidate,
                inventory=inventory,
                structure=structure,
                structure_path=canonical_structure_path,
                structure_file_sha256=study.file_digest(structure_path),
            )
            updated = deepcopy(state)
            updated["artifacts"].append(record(state_path.parent, source, source.read_bytes(), "missing_access_audit", ARTIFACT, SCHEMA))
            updated["updated_at"] = now()
            save_state(state_path, updated)
        print(json.dumps({"ok": True, "binding_count": len(bindings), "binding_set_sha256": document["binding_set_sha256"], "score_fields_changed": False}, indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    __import__("runtime_profile").require_public_cli()
    main()
