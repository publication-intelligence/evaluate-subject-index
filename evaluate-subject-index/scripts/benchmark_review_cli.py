#!/usr/bin/env python3
"""Deterministic inventories and completion gates for source-benchmark review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from schema_validation import schema_errors
from state_cli import (
    artifact_id,
    evaluation_mutation_lock,
    next_stage,
    now,
    portable_relative_path,
    resolve_artifact_path,
    save_state,
    validate_state,
)


INVENTORY_SCHEMA = "source-benchmark-review-inventory-v1"
REVIEW_SCHEMA = "source-benchmark-review-v1"
COMPATIBILITY_APPROVAL_SCHEMA = "source-benchmark-compatibility-approval-v1"
COMPATIBILITY_PROVENANCE_SCHEMA = "source-benchmark-compatibility-import-provenance-v1"
COMPATIBILITY_OPERATION = "reviewed_legacy_benchmark_compatibility_import"
MECHANICAL_NORMALIZATION = "relationships[*].type->relationship_type"
NATIVE_V8_REUSE_MODE = "native_v8_exact"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail("file_not_found", f"File does not exist: {path}")
    except json.JSONDecodeError as exc:
        fail("invalid_json", f"Could not parse {path}: {exc}")
    if not isinstance(value, dict):
        fail("invalid_root", f"JSON root must be an object: {path}")
    return value


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: dict[str, Any]) -> str:
    clone = dict(value)
    clone.pop("benchmark_sha256", None)
    encoded = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def benchmark_content_hash(value: dict[str, Any]) -> str:
    """Hash editorial content while ignoring draft/freeze wrapper fields."""
    clone = dict(value)
    for field in (
        "schema_version", "benchmark_sha256", "synthesis", "freeze", "version",
        "benchmark_id", "evaluation_id", "source_sha256", "policy_sha256",
        "page_map_sha256", "chunk_manifest_sha256", "candidate_blindness",
    ):
        clone.pop(field, None)
    encoded = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_field_hash(value: dict[str, Any], field: str) -> str:
    clone = dict(value)
    clone.pop(field, None)
    encoded = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_label(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", folded))


def emit(payload: dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code)


def fail(code: str, message: str, details: Any = None) -> None:
    payload: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    emit(payload, 1)


def subject_id(subject: dict[str, Any]) -> str:
    return str(subject.get("subject_id", ""))


def relationship_id(relationship: dict[str, Any]) -> str:
    return str(relationship.get("relationship_id", ""))


def task_id(task: dict[str, Any]) -> str:
    return str(task.get("task_id", ""))


def final_benchmark_structure_errors(benchmark: dict[str, Any]) -> list[str]:
    """Validate the shared current frozen-benchmark content contract."""
    errors = schema_errors(benchmark, "source-benchmark.schema.json")
    if errors:
        return errors
    subjects = benchmark["subjects"]
    relationships = benchmark["relationships"]
    tasks = benchmark["reader_tasks"]
    subject_ids = [subject["subject_id"] for subject in subjects]
    if len(subject_ids) != len(set(subject_ids)):
        errors.append("Subject identifiers must be unique.")
    known_subject_ids = set(subject_ids)
    relationship_ids = [relationship["relationship_id"] for relationship in relationships]
    for relationship in relationships:
        if relationship["source_subject_id"] not in known_subject_ids:
            errors.append(f"Relationship {relationship['relationship_id']} has an unknown source subject.")
        if relationship.get("target_subject_id") not in known_subject_ids and "target_subject_id" in relationship:
            errors.append(f"Relationship {relationship['relationship_id']} has an unknown target subject.")
    if len(relationship_ids) != len(set(relationship_ids)):
        errors.append("Relationship identifiers must be unique.")
    task_ids = [task["task_id"] for task in tasks]
    for task in tasks:
        if not set(task["subject_ids"]).issubset(known_subject_ids):
            errors.append(f"Reader task {task['task_id']} refers to an unknown subject.")
    if len(task_ids) != len(set(task_ids)):
        errors.append("Reader-task identifiers must be unique.")
    return errors


def draft_benchmark_structure_errors(benchmark: dict[str, Any]) -> list[str]:
    errors = schema_errors(benchmark, "source-benchmark-draft.schema.json")
    if errors:
        return errors
    subjects = benchmark["subjects"]
    relationships = benchmark["relationships"]
    tasks = benchmark["reader_tasks"]
    subject_ids = [subject_id(item) for item in subjects]
    relationship_ids = [relationship_id(item) for item in relationships]
    task_ids = [task_id(item) for item in tasks]
    known_subject_ids = set(subject_ids)
    if len(subject_ids) != len(known_subject_ids):
        errors.append("Subject identifiers must be unique.")
    if len(relationship_ids) != len(set(relationship_ids)):
        errors.append("Relationship identifiers must be unique.")
    if len(task_ids) != len(set(task_ids)):
        errors.append("Reader-task identifiers must be unique.")
    for relationship in relationships:
        if relationship["source_subject_id"] not in known_subject_ids:
            errors.append(f"Relationship {relationship['relationship_id']} has an unknown source subject.")
        if relationship.get("target_subject_id") not in known_subject_ids and "target_subject_id" in relationship:
            errors.append(f"Relationship {relationship['relationship_id']} has an unknown target subject.")
    for task in tasks:
        if not set(task["subject_ids"]).issubset(known_subject_ids):
            errors.append(f"Reader task {task['task_id']} refers to an unknown subject.")
    return errors


def build_inventory(draft_path: Path, threshold: float) -> dict[str, Any]:
    draft = load_json(draft_path)
    structural_errors = draft_benchmark_structure_errors(draft)
    if structural_errors:
        fail("schema_validation_failed", "Benchmark draft is structurally invalid.", structural_errors)
    subjects = draft["subjects"]
    relationships = draft["relationships"]
    tasks = draft["reader_tasks"]
    subject_ids = [subject_id(item) for item in subjects]
    relationship_ids = [relationship_id(item) for item in relationships]
    task_ids = [task_id(item) for item in tasks]
    if len(subject_ids) != len(set(subject_ids)):
        fail("duplicate_subject_id", "Benchmark subject identifiers must be unique.")
    if len(relationship_ids) != len(set(relationship_ids)):
        fail("duplicate_relationship_id", "Benchmark relationship identifiers must be unique.")
    if len(task_ids) != len(set(task_ids)):
        fail("duplicate_task_id", "Reader-task identifiers must be unique.")

    labels: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in subjects:
        labels[normalize_label(str(item.get("label", "")))].append(item)
    exact_groups = [
        {"normalized_label": label, "subject_ids": [subject_id(item) for item in group], "labels": [item.get("label") for item in group]}
        for label, group in sorted(labels.items())
        if label and len(group) > 1
    ]

    normalized = [(subject_id(item), str(item.get("label", "")), normalize_label(str(item.get("label", "")))) for item in subjects]
    near_pairs: list[dict[str, Any]] = []
    for index, (left_id, left_label, left_normalized) in enumerate(normalized):
        if not left_normalized:
            continue
        for right_id, right_label, right_normalized in normalized[index + 1:]:
            if not right_normalized or left_normalized == right_normalized:
                continue
            ratio = SequenceMatcher(None, left_normalized, right_normalized).ratio()
            if ratio >= threshold:
                near_pairs.append({
                    "left_subject_id": left_id,
                    "left_label": left_label,
                    "right_subject_id": right_id,
                    "right_label": right_label,
                    "similarity": round(ratio, 4),
                })

    cross_chapter = [
        subject_id(item)
        for item in subjects
        if len(item.get("chapter_provenance", [])) > 1
    ]
    unresolved = [
        relationship_id(item)
        for item in relationships
        if item.get("resolution_status", "resolved") != "resolved"
    ]
    fallback_tasks = [
        task_id(item)
        for item in tasks
        if item.get("fallback_generated") is True
        or ("source_task_ids" in item and not item["source_task_ids"])
    ]
    task_subject_ids = {
        str(item)
        for task in tasks
        for item in task["subject_ids"]
    }
    subject_id_set = set(subject_ids)
    invalid_relationship_targets = [
        relationship_id(item)
        for item in relationships
        if item.get("target_subject_id") and item.get("target_subject_id") not in subject_id_set
    ]
    invalid_task_subject_ids = sorted(task_subject_ids - subject_id_set)
    missing_tasks = sorted(subject_id_set - task_subject_ids)
    priority_counts = Counter(str(item.get("priority", "missing")) for item in subjects)
    scored_count = priority_counts.get("essential", 0) + priority_counts.get("major", 0)
    unresolved_share = len(unresolved) / len(relationships) if relationships else 0.0
    scored_share = scored_count / len(subjects) if subjects else 0.0
    warnings: list[str] = []
    if exact_groups:
        warnings.append("Exact duplicate normalized labels require semantic disposition.")
    if near_pairs:
        warnings.append("Near-duplicate labels are diagnostic candidates, not automatic merges.")
    if unresolved:
        warnings.append("Every non-resolved relationship requires an individual editorial disposition.")
    if fallback_tasks:
        warnings.append("Every fallback-generated reader task requires independent editorial review.")
    if scored_share >= 0.9:
        warnings.append("Essential-plus-major priority share is at least 90%; review significance without imposing a quota.")

    result = {
        "schema_version": INVENTORY_SCHEMA,
        "evaluation_id": draft.get("evaluation_id"),
        "draft": {
            "version": draft.get("version"),
            "sha256": file_sha256(draft_path),
            "candidate_blindness": draft.get("candidate_blindness"),
        },
        "review_requirements": {
            "independent_fresh_context_required_for_full_mode": True,
            "candidate_must_remain_unseen": True,
            "density_is_not_a_subject_or_priority_quota": True,
            "full_mode_requires_complete_id_coverage": True,
        },
        "denominators": {
            "subjects": len(subjects),
            "relationships": len(relationships),
            "reader_tasks": len(tasks),
            "cross_chapter_subjects": len(cross_chapter),
            "unresolved_relationships": len(unresolved),
            "fallback_reader_tasks": len(fallback_tasks),
            "exclusions": len(draft.get("exclusions", [])),
            "uncertainties": len(draft.get("uncertainties", [])),
        },
        "queues": {
            "subject_ids": subject_ids,
            "relationship_ids": relationship_ids,
            "reader_task_ids": task_ids,
            "cross_chapter_subject_ids": cross_chapter,
            "unresolved_relationship_ids": unresolved,
            "fallback_reader_task_ids": fallback_tasks,
            "exact_duplicate_label_groups": exact_groups,
            "near_duplicate_label_pairs": sorted(near_pairs, key=lambda item: (-item["similarity"], item["left_subject_id"], item["right_subject_id"])),
            "subjects_missing_reader_tasks": missing_tasks,
            "subjects_missing_required_fields": {},
            "invalid_relationship_target_ids": invalid_relationship_targets,
            "invalid_task_subject_ids": invalid_task_subject_ids,
        },
        "diagnostics": {
            "priority_distribution": dict(sorted(priority_counts.items())),
            "essential_plus_major_share": round(scored_share, 6),
            "relationship_resolution_distribution": dict(sorted(Counter(str(item.get("resolution_status", "resolved")) for item in relationships).items())),
            "unresolved_relationship_share": round(unresolved_share, 6),
            "near_duplicate_threshold": threshold,
            "warnings": warnings,
        },
    }
    structural_errors = schema_errors(result, "source-benchmark-review-inventory.schema.json")
    if structural_errors:
        fail("schema_validation_failed", "Generated review inventory is structurally invalid.", structural_errors)
    return result


def validate_review_data(draft_path: Path, inventory_path: Path, review_path: Path) -> tuple[list[str], dict[str, Any]]:
    draft = load_json(draft_path)
    inventory = load_json(inventory_path)
    review = load_json(review_path)
    errors = [
        *(f"draft: {error}" for error in draft_benchmark_structure_errors(draft)),
        *(f"inventory: {error}" for error in schema_errors(inventory, "source-benchmark-review-inventory.schema.json")),
        *(f"review: {error}" for error in schema_errors(review, "source-benchmark-review.schema.json")),
    ]
    if errors:
        return errors, review
    threshold = inventory.get("diagnostics", {}).get("near_duplicate_threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0.0 < threshold <= 1.0:
        errors.append("inventory diagnostics.near_duplicate_threshold must be greater than 0 and no more than 1.")
    elif inventory != build_inventory(draft_path, float(threshold)):
        errors.append("Review inventory does not exactly match the deterministic inventory recomputed from the draft.")
    for value, label in ((inventory, "inventory"), (review, "review")):
        if value.get("evaluation_id") != draft.get("evaluation_id"):
            errors.append(f"{label} evaluation_id does not match the draft.")
    draft_ref = review["draft"]
    if draft_ref != inventory.get("draft"):
        errors.append("Review draft identity does not match the deterministic inventory.")
    if draft_ref.get("sha256") != file_sha256(draft_path):
        errors.append("Review draft sha256 does not identify the supplied draft.")
    if draft.get("candidate_blindness") != "preserved":
        errors.append("Benchmark draft candidate blindness must be preserved.")
    if review.get("candidate_blindness") != "preserved":
        errors.append("Candidate blindness must be preserved for an approved benchmark review.")
    independence = review["reviewer_independence"]
    if not independence.get("candidate_unseen"):
        errors.append("The benchmark reviewer must attest that the candidate remained unseen.")
    if independence.get("source_reconnected_sha256") != draft.get("source_sha256"):
        errors.append("The reviewer source hash does not match the benchmark source hash.")
    coverage = review["coverage"]
    queue = inventory["queues"]
    comparisons = (
        ("subject_ids_reviewed", "subject_ids"),
        ("relationship_ids_reviewed", "relationship_ids"),
        ("reader_task_ids_reviewed", "reader_task_ids"),
        ("cross_chapter_subject_ids_reviewed", "cross_chapter_subject_ids"),
        ("unresolved_relationship_ids_dispositioned", "unresolved_relationship_ids"),
        ("fallback_reader_task_ids_reviewed", "fallback_reader_task_ids"),
    )
    review_mode = review["review_mode"]
    if review_mode == "full" and not independence.get("fresh_context"):
        errors.append("Full benchmark review requires a fresh independent context.")
    for reviewed_field, expected_field in comparisons:
        reviewed_ids = set(coverage[reviewed_field])
        expected_ids = set(queue[expected_field])
        if not reviewed_ids.issubset(expected_ids):
            errors.append(f"coverage.{reviewed_field} contains identifiers outside the inventory.")
        if review_mode == "full" and reviewed_ids != expected_ids:
            errors.append(f"Full review has incomplete coverage for {reviewed_field}: expected {len(expected_ids)}, reviewed {len(reviewed_ids)}.")
    completion = review["completion"]
    if review_mode == "full":
        for field in ("structural_validation_passed", "editorial_review_complete", "source_first_omission_review_complete", "candidate_blindness_preserved", "no_unreviewed_required_items", "public_claims_allowed"):
            if completion.get(field) is not True:
                errors.append(f"Full review completion.{field} must be true.")
    elif completion.get("public_claims_allowed") is not False:
        errors.append("Pilot benchmark review must set completion.public_claims_allowed to false.")
    recommendation = review.get("recommendation")
    if review_mode == "pilot" and recommendation in {"retain_draft", "approve_revised"}:
        errors.append("Pilot review cannot approve a benchmark for final freeze.")
    return errors, review


def approved_changes(draft: dict[str, Any], final: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the smallest stable-ID ledger that describes the semantic revision."""
    changes: list[dict[str, Any]] = []
    collections = (
        ("subject", "subjects", "subject_id"),
        ("relationship", "relationships", "relationship_id"),
        ("reader_task", "reader_tasks", "task_id"),
    )
    for entity_type, collection, id_field in collections:
        before = {item[id_field]: item for item in draft[collection]}
        after = {item[id_field]: item for item in final[collection]}
        for entity_id in sorted(before.keys() | after.keys()):
            if entity_id not in before:
                changes.append({"entity_type": entity_type, "entity_id": entity_id, "action": "add"})
            elif entity_id not in after:
                changes.append({"entity_type": entity_type, "entity_id": entity_id, "action": "remove"})
            else:
                fields = sorted(
                    field for field in before[entity_id].keys() | after[entity_id].keys()
                    if field != id_field and (
                        (field in before[entity_id]) != (field in after[entity_id])
                        or before[entity_id].get(field) != after[entity_id].get(field)
                    )
                )
                if fields:
                    changes.append({"entity_type": entity_type, "entity_id": entity_id, "action": "update", "fields": fields})

    wrappers = {
        "schema_version", "benchmark_sha256", "synthesis", "freeze", "version",
        "benchmark_id", "evaluation_id", "source_sha256", "policy_sha256",
        "page_map_sha256", "chunk_manifest_sha256", "candidate_blindness",
        "subjects", "relationships", "reader_tasks",
    }
    fields = sorted(
        field for field in draft.keys() | final.keys()
        if field not in wrappers and (
            (field in draft) != (field in final) or draft.get(field) != final.get(field)
        )
    )
    if fields:
        changes.append({
            "entity_type": "benchmark", "entity_id": draft["benchmark_id"],
            "action": "update", "fields": fields,
        })
    return changes


def normalized_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [
        {**change, **({"fields": sorted(change["fields"])} if "fields" in change else {})}
        for change in changes
    ]
    return sorted(normalized, key=lambda item: (
        item["entity_type"], item["entity_id"], item["action"], item.get("fields", [])
    ))


def registered_identity_matches(
    state: dict[str, Any], state_path: Path, stage: str, field: str, expected: str
) -> bool:
    for item in state.get("artifacts", []):
        if not isinstance(item, dict) or item.get("stage") != stage:
            continue
        try:
            path = resolve_artifact_path(state_path, item["path"])
            document = json.loads(path.read_text(encoding="utf-8"))
        except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
        if (
            isinstance(document, dict)
            and file_sha256(path) == item.get("sha256")
            and document.get(field) == expected
        ):
            return True
    return False


def registered_file_matches(
    state: dict[str, Any], state_path: Path, stage: str, path: Path
) -> bool:
    relative = portable_relative_path(path, state_path.parent)
    digest = file_sha256(path)
    return any(
        isinstance(item, dict)
        and item.get("stage") == stage
        and item.get("path") == relative
        and item.get("sha256") == digest
        for item in state.get("artifacts", [])
    )


def legacy_registered_hash(state: dict[str, Any], stage: str, digest: str) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("stage") == stage
        and item.get("sha256") == digest
        for item in state.get("artifacts", [])
    )


def stable_id_summary(benchmark: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    def identifiers(collection: str, field: str) -> list[Any]:
        values = benchmark.get(collection, [])
        if not isinstance(values, list):
            errors.append(f"Benchmark {collection} must be an array.")
            return []
        return [item.get(field) if isinstance(item, dict) else None for item in values]

    subjects = benchmark.get("subjects", [])
    groups = {
        "subjects": identifiers("subjects", "subject_id"),
        "relationships": identifiers("relationships", "relationship_id"),
        "reader_tasks": identifiers("reader_tasks", "task_id"),
        "evidence": [
            evidence.get("evidence_id") if isinstance(evidence, dict) else None
            for subject in subjects if isinstance(subject, dict)
            for evidence in subject.get("evidence", []) if isinstance(subject.get("evidence", []), list)
        ],
    }
    summary: dict[str, Any] = {}
    for name, identifiers in groups.items():
        valid = [identifier for identifier in identifiers if isinstance(identifier, str) and identifier]
        if len(valid) != len(identifiers):
            errors.append(f"Every {name} stable ID must be a non-empty string.")
        if len(valid) != len(set(valid)):
            errors.append(f"Every {name} stable ID must be unique.")
        encoded = json.dumps(sorted(valid), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        summary[name] = {"count": len(identifiers), "sha256": hashlib.sha256(encoded).hexdigest()}
    return summary, errors


def normalized_legacy_benchmark(
    legacy: dict[str, Any], approval: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    normalized = deepcopy(legacy)
    native_v8 = approval.get("reuse_mode") == NATIVE_V8_REUSE_MODE
    relationships = normalized.get("relationships")
    if not isinstance(relationships, list):
        return normalized, ["Legacy benchmark relationships must be an array."]
    for relationship in relationships:
        if not isinstance(relationship, dict):
            errors.append("Every legacy relationship must be an object.")
            continue
        has_old = "type" in relationship
        has_new = "relationship_type" in relationship
        if native_v8 and (has_old or not has_new):
            errors.append(
                f"Native V8 relationship {relationship.get('relationship_id')} must contain relationship_type and no legacy type key."
            )
            continue
        if not native_v8 and (not has_old or has_new):
            errors.append(
                f"Relationship {relationship.get('relationship_id')} must contain exactly one legacy type key and no relationship_type key."
            )
            continue
        if not native_v8:
            relationship["relationship_type"] = relationship.pop("type")
    if errors:
        return normalized, errors

    current = approval["current"]
    legacy_identity = approval["legacy"]
    compatibility_import = {
        "operation": COMPATIBILITY_OPERATION,
        "approval_id": approval["approval_id"],
        "legacy_benchmark_file_sha256": legacy_identity["benchmark_file_sha256"],
        "legacy_benchmark_sha256": legacy_identity["benchmark_sha256"],
        "normalization": [] if native_v8 else [MECHANICAL_NORMALIZATION],
        "no_discovery_or_editorial_review_rerun": True,
    }
    if native_v8:
        compatibility_import.update({
            "reuse_mode": NATIVE_V8_REUSE_MODE,
            "legacy_state_file_sha256": legacy_identity["state_file_sha256"],
            "policy_identity": current["policy_sha256"],
            "release_transport": deepcopy(approval["release_transport"]),
        })
    else:
        compatibility_import.update({
            "legacy_artifact_freeze_commit": legacy_identity["artifact_freeze_commit"],
            "policy_rebinding": {
                "from": legacy_identity["policy_sha256"],
                "to": current["policy_sha256"],
            },
        })
    normalized.update({
        "benchmark_id": current["benchmark_id"],
        "version": current["version"],
        "evaluation_id": current["evaluation_id"],
        "policy_sha256": current["policy_sha256"],
        "freeze": {
            "frozen_at": current["frozen_at"],
            "synthesis_pass_complete": True,
            "page_coverage_complete": True,
        },
        "compatibility_import": compatibility_import,
    })
    normalized["benchmark_sha256"] = canonical_hash(normalized)
    return normalized, errors


def legacy_review_errors(
    benchmark: dict[str, Any], benchmark_file_sha256: str,
    inventory: dict[str, Any], review: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if inventory.get("schema_version") != INVENTORY_SCHEMA:
        errors.append("Legacy review inventory has an unsupported schema_version.")
    if review.get("schema_version") != REVIEW_SCHEMA:
        errors.append("Legacy review ledger has an unsupported schema_version.")
    for value, label in ((inventory, "inventory"), (review, "review")):
        if value.get("evaluation_id") != benchmark.get("evaluation_id"):
            errors.append(f"Legacy {label} evaluation_id does not match the benchmark.")
    if review.get("review_mode") != "full":
        errors.append("Legacy benchmark review must be full.")
    if review.get("candidate_blindness") != "preserved":
        errors.append("Legacy review candidate blindness must be preserved.")
    independence = review.get("reviewer_independence", {})
    if independence.get("fresh_context") is not True or independence.get("candidate_unseen") is not True:
        errors.append("Legacy full review must attest a fresh context with the candidate unseen.")
    if independence.get("source_reconnected_sha256") != benchmark.get("source_sha256"):
        errors.append("Legacy review source identity does not match the benchmark.")
    for field in (
        "structural_validation_passed", "editorial_review_complete",
        "source_first_omission_review_complete", "candidate_blindness_preserved",
        "no_unreviewed_required_items", "public_claims_allowed",
    ):
        if review.get("completion", {}).get(field) is not True:
            errors.append(f"Legacy full review completion.{field} must be true.")
    if review.get("recommendation") not in {"retain_draft", "approve_revised"}:
        errors.append("Legacy review recommendation does not authorize the frozen benchmark.")

    draft = review.get("draft", {})
    inventory_draft = inventory.get("draft", {})
    for field in ("version", "file_sha256", "canonical_sha256"):
        if draft.get(field) != inventory_draft.get(field):
            errors.append(f"Legacy review and inventory draft {field} do not match.")
    comparisons = (
        ("subject_ids_reviewed", "subject_ids"),
        ("relationship_ids_reviewed", "relationship_ids"),
        ("reader_task_ids_reviewed", "reader_task_ids"),
        ("cross_chapter_subject_ids_reviewed", "cross_chapter_subject_ids"),
        ("unresolved_relationship_ids_dispositioned", "unresolved_relationship_ids"),
        ("fallback_reader_task_ids_reviewed", "fallback_reader_task_ids"),
    )
    coverage = review.get("coverage", {})
    queues = inventory.get("queues", {})
    for reviewed_field, expected_field in comparisons:
        reviewed = coverage.get(reviewed_field)
        expected = queues.get(expected_field)
        if not isinstance(reviewed, list) or not isinstance(expected, list):
            errors.append(f"Legacy full review coverage is missing {reviewed_field}.")
        elif not all(isinstance(item, str) for item in [*reviewed, *expected]):
            errors.append(f"Legacy full review coverage {reviewed_field} must contain string IDs.")
        elif len(reviewed) != len(set(reviewed)) or set(reviewed) != set(expected):
            errors.append(f"Legacy full review has incomplete or duplicate coverage for {reviewed_field}.")

    proposed = review.get("proposed_final", {})
    if proposed.get("version") != benchmark.get("version"):
        errors.append("Legacy review proposed-final version does not match the benchmark.")
    if proposed.get("file_sha256") != benchmark_file_sha256:
        errors.append("Legacy review proposed-final file hash does not match the benchmark.")
    if proposed.get("canonical_sha256") != benchmark.get("benchmark_sha256"):
        errors.append("Legacy review proposed-final canonical hash does not match the benchmark.")
    return errors


def set_of_strings(value: Any, field: str, errors: list[str]) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        errors.append(f"{field} must be an array of strings.")
        return set()
    if len(value) != len(set(value)):
        errors.append(f"{field} contains duplicate identifiers.")
    return set(value)


def native_v8_review_errors(
    draft_path: Path,
    draft: dict[str, Any],
    benchmark: dict[str, Any],
    inventory: dict[str, Any],
    review: dict[str, Any],
) -> list[str]:
    """Validate the exact historical V8 review contract used by native freezes."""
    errors = [
        *(f"Native V8 draft: {error}" for error in draft_benchmark_structure_errors(draft)),
        *(f"Native V8 benchmark: {error}" for error in final_benchmark_structure_errors(benchmark)),
    ]
    if inventory.get("schema_version") != INVENTORY_SCHEMA:
        errors.append("Native V8 review inventory has an unsupported schema_version.")
    if review.get("schema_version") != REVIEW_SCHEMA:
        errors.append("Native V8 review ledger has an unsupported schema_version.")
    for value, label in ((inventory, "inventory"), (review, "review")):
        if value.get("evaluation_id") != draft.get("evaluation_id"):
            errors.append(f"Native V8 {label} evaluation_id does not match the draft.")

    draft_file_sha256 = file_sha256(draft_path)
    draft_canonical_sha256 = canonical_hash(draft)
    inventory_draft = inventory.get("draft", {})
    review_draft = review.get("draft", {})
    expected_draft = {
        "version": draft.get("version"),
        "file_sha256": draft_file_sha256,
        "canonical_sha256": draft_canonical_sha256,
    }
    for field, expected in expected_draft.items():
        if inventory_draft.get(field) != expected or review_draft.get(field) != expected:
            errors.append(f"Native V8 inventory/review draft {field} does not identify the supplied draft.")
    if inventory_draft.get("candidate_blindness") != "preserved" or draft.get("candidate_blindness") != "preserved":
        errors.append("Native V8 draft candidate blindness must be preserved.")

    threshold = inventory.get("diagnostics", {}).get("near_duplicate_threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not 0.0 < threshold <= 1.0:
        errors.append("Native V8 inventory near-duplicate threshold is invalid.")
    else:
        recomputed = build_inventory(draft_path, float(threshold))
        recomputed["draft"] = {
            "path": inventory_draft.get("path"),
            **expected_draft,
            "candidate_blindness": draft.get("candidate_blindness"),
        }
        if recomputed != inventory:
            errors.append("Native V8 review inventory does not exactly match deterministic recomputation from the draft.")

    if review.get("review_mode") != "full" or review.get("candidate_blindness") != "preserved":
        errors.append("Native V8 benchmark review must be full and candidate-blind.")
    independence = review.get("reviewer_independence", {})
    if independence.get("fresh_context") is not True or independence.get("candidate_unseen") is not True:
        errors.append("Native V8 review must attest a fresh context with the candidate unseen.")
    if independence.get("source_reconnected_sha256") != draft.get("source_sha256"):
        errors.append("Native V8 review source identity does not match the draft.")
    for field in (
        "structural_validation_passed", "editorial_review_complete",
        "source_first_omission_review_complete", "candidate_blindness_preserved",
        "no_unreviewed_required_items", "public_claims_allowed",
    ):
        if review.get("completion", {}).get(field) is not True:
            errors.append(f"Native V8 full review completion.{field} must be true.")

    comparisons = (
        ("subject_ids_reviewed", "subject_ids"),
        ("relationship_ids_reviewed", "relationship_ids"),
        ("reader_task_ids_reviewed", "reader_task_ids"),
        ("cross_chapter_subject_ids_reviewed", "cross_chapter_subject_ids"),
        ("unresolved_relationship_ids_dispositioned", "unresolved_relationship_ids"),
        ("fallback_reader_task_ids_reviewed", "fallback_reader_task_ids"),
    )
    coverage = review.get("coverage", {})
    queues = inventory.get("queues", {})
    for reviewed_field, expected_field in comparisons:
        reviewed = set_of_strings(coverage.get(reviewed_field), f"coverage.{reviewed_field}", errors)
        expected = set_of_strings(queues.get(expected_field), f"inventory.queues.{expected_field}", errors)
        if reviewed != expected:
            errors.append(f"Native V8 full review has incomplete coverage for {reviewed_field}.")

    changes = review.get("changes")
    required_change_fields = (
        "merges", "splits", "priority_changes", "relationship_changes",
        "reader_task_changes", "subjects_added", "subjects_removed", "terminology_changes",
    )
    if not isinstance(changes, dict):
        errors.append("Native V8 review changes must be an object.")
    elif any(not isinstance(changes.get(field), list) for field in required_change_fields):
        errors.append("Native V8 review changes ledger is incomplete.")
    remaining_issues = review.get("remaining_issues")
    if not isinstance(remaining_issues, list):
        errors.append("Native V8 review remaining_issues must be an array.")
    elif any(issue.get("blocking") is True for issue in remaining_issues if isinstance(issue, dict)):
        errors.append("Native V8 review retains a blocking issue.")

    for field in (
        "benchmark_id", "evaluation_id", "source_sha256", "policy_sha256",
        "page_map_sha256", "chunk_manifest_sha256",
    ):
        if benchmark.get(field) != draft.get(field):
            errors.append(f"Native V8 final benchmark changed frozen identity field: {field}.")
    if benchmark.get("candidate_blindness") != "preserved":
        errors.append("Native V8 final benchmark candidate blindness must be preserved.")
    if benchmark.get("benchmark_sha256") != canonical_hash(benchmark):
        errors.append("Native V8 final benchmark canonical hash does not recompute.")
    recommendation = review.get("recommendation")
    freeze = benchmark.get("freeze", {})
    for field, expected in (
        ("synthesis_pass_complete", True), ("page_coverage_complete", True),
        ("review_mode", "full"), ("review_recommendation", recommendation),
        ("candidate_blindness", "preserved"),
        ("source_reconnected_sha256", draft.get("source_sha256")),
    ):
        if freeze.get(field) != expected:
            errors.append(f"Native V8 final freeze.{field} does not match the reviewed release.")
    if recommendation == "retain_draft":
        if benchmark_content_hash(draft) != benchmark_content_hash(benchmark):
            errors.append("Native V8 retain_draft review changed canonical benchmark content.")
        if benchmark.get("version") != draft.get("version"):
            errors.append("Native V8 retain_draft review changed the benchmark version.")
    elif recommendation == "approve_revised":
        if benchmark_content_hash(draft) == benchmark_content_hash(benchmark):
            errors.append("Native V8 approve_revised review requires substantively different editorial content.")
        if not isinstance(benchmark.get("version"), int) or benchmark.get("version", 0) <= draft.get("version", 0):
            errors.append("Native V8 revised benchmark must increment the version.")
    else:
        errors.append("Native V8 review recommendation does not authorize the frozen benchmark.")
    return errors


def validate_final_data(
    draft_path: Path,
    inventory_path: Path,
    review_path: Path,
    final_path: Path,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    errors, review = validate_review_data(draft_path, inventory_path, review_path)
    draft = load_json(draft_path)
    final = load_json(final_path)
    errors.extend(final_benchmark_structure_errors(final))
    if errors:
        return errors, review, final
    for field in (
        "benchmark_id", "evaluation_id", "source_sha256", "policy_sha256",
        "page_map_sha256", "chunk_manifest_sha256",
    ):
        if final.get(field) != draft.get(field):
            errors.append(f"Final benchmark changed frozen identity field: {field}")
    if final.get("candidate_blindness") != "preserved":
        errors.append("Final benchmark candidate blindness must be preserved.")
    if final.get("benchmark_sha256") != canonical_hash(final):
        errors.append("Final benchmark canonical hash does not recompute.")

    actual_changes = normalized_changes(approved_changes(draft, final))
    if normalized_changes(review.get("approved_changes", [])) != actual_changes:
        errors.append("Review approved_changes does not exactly match the final benchmark revision.")
    recommendation = review.get("recommendation")
    if recommendation == "retain_draft":
        if actual_changes:
            errors.append("retain_draft review must preserve the draft's semantic benchmark content.")
        if final.get("version") != draft.get("version"):
            errors.append("retain_draft review must retain the draft version.")
    elif recommendation == "approve_revised":
        if not actual_changes:
            errors.append("approve_revised review requires a substantive approved change.")
        if final.get("version", 0) <= draft.get("version", 0):
            errors.append("A revised benchmark must increment the benchmark version.")
    else:
        errors.append("Review recommendation does not authorize final freeze.")
    return errors, review, final


def command_screen(args: argparse.Namespace) -> None:
    if not 0.0 < args.near_duplicate_threshold <= 1.0:
        fail("invalid_threshold", "near-duplicate-threshold must be greater than 0 and no more than 1.")
    output = Path(args.output)
    result = build_inventory(Path(args.draft), args.near_duplicate_threshold)
    save_json(output, result)
    emit({
        "command": "screen",
        "ok": True,
        "evaluation_id": result.get("evaluation_id"),
        "inventory_path": str(output.resolve()),
        "denominators": result["denominators"],
        "diagnostics": result["diagnostics"],
    })


def command_validate_review(args: argparse.Namespace) -> None:
    errors, review = validate_review_data(Path(args.draft), Path(args.inventory), Path(args.review))
    emit({
        "command": "validate-review",
        "ok": not errors,
        "evaluation_id": review.get("evaluation_id"),
        "review_mode": review.get("review_mode"),
        "recommendation": review.get("recommendation"),
        "errors": errors,
        "warnings": [],
    }, 0 if not errors else 1)


def command_freeze(args: argparse.Namespace) -> None:
    state_path = Path(args.state).resolve()
    draft_path = Path(args.draft)
    final_path = Path(args.final)
    inventory_path = Path(args.inventory)
    review_path = Path(args.review)
    errors, review, final = validate_final_data(
        draft_path, inventory_path, review_path, final_path
    )
    state = load_json(state_path)
    state_errors, warnings = validate_state(state, state_path=state_path)
    errors.extend(f"state: {error}" for error in state_errors)
    if state.get("evaluation_id") != final.get("evaluation_id"):
        errors.append("Final benchmark evaluation_id does not match canonical state.")
    if state.get("source", {}).get("sha256") != final.get("source_sha256"):
        errors.append("Final benchmark source_sha256 does not match canonical state.")
    if state.get("stages", {}).get("benchmark_synthesis", {}).get("status") != "completed":
        errors.append("Benchmark synthesis must be complete before freeze.")
    for stage in ("benchmark_review", "benchmark_freeze"):
        if state.get("stages", {}).get(stage, {}).get("status") == "completed":
            errors.append(f"{stage} is already completed.")
    for stage, field in (
        ("page_mapping", "page_map_sha256"),
        ("chunk_definition", "chunk_manifest_sha256"),
        ("define_policy", "policy_sha256"),
    ):
        if not registered_identity_matches(state, state_path, stage, field, final.get(field)):
            errors.append(f"Final benchmark {field} does not identify a registered {stage} artifact.")

    root = state_path.parent
    draft_relative = portable_relative_path(draft_path, root)
    review_relative = portable_relative_path(review_path, root)
    final_relative = portable_relative_path(final_path, root)
    if review_relative == final_relative:
        errors.append("Review ledger and final benchmark must be separate artifacts.")
    draft_digest = file_sha256(draft_path)
    if not any(
        item.get("stage") == "benchmark_synthesis"
        and item.get("path") == draft_relative
        and item.get("sha256") == draft_digest
        and item.get("schema_version") == "source-subject-benchmark-draft-v1"
        for item in state.get("artifacts", []) if isinstance(item, dict)
    ):
        errors.append("Supplied draft is not the exact registered benchmark_synthesis artifact.")
    if errors:
        emit({
            "command": "freeze", "ok": False,
            "evaluation_id": final.get("evaluation_id"), "errors": errors,
            "warnings": warnings,
        }, 1)

    stamp = now()
    updated = deepcopy(state)
    records = []
    for path, relative, stage, artifact_type, schema_version in (
        (review_path, review_relative, "benchmark_review", "source_benchmark_review", REVIEW_SCHEMA),
        (final_path, final_relative, "benchmark_freeze", "source_benchmark", "source-subject-benchmark-v2"),
    ):
        digest = file_sha256(path)
        records.append({
            "artifact_id": artifact_id(relative, digest), "stage": stage,
            "artifact_type": artifact_type, "path": relative, "sha256": digest,
            "media_type": "application/json", "schema_version": schema_version,
            "visibility": "private", "retention": "required", "frozen": True,
            "recorded_at": stamp,
        })
    registered_paths = {record["path"] for record in records}
    updated["artifacts"] = [
        item for item in updated.get("artifacts", []) if item.get("path") not in registered_paths
    ] + records
    updated["artifacts"].sort(key=lambda item: item["path"])
    updated["stages"]["benchmark_review"] = {
        "status": "completed", "updated_at": stamp,
        "notes": ["Validated independent candidate-blind review ledger."],
    }
    updated["stages"]["benchmark_freeze"] = {
        "status": "completed", "updated_at": stamp,
        "notes": ["Validated and registered the approved final benchmark atomically with review."],
    }
    updated["updated_at"] = stamp
    state_errors, warnings = validate_state(updated, state_path=state_path)
    if state_errors:
        fail("canonical_state_invalid", "Benchmark freeze would leave invalid canonical state.", state_errors)
    save_state(state_path, updated)
    action = next_stage(updated)
    emit({
        "command": "freeze", "ok": True, "evaluation_id": final["evaluation_id"],
        "version": final["version"], "benchmark_sha256": final["benchmark_sha256"],
        "artifacts_registered": [record["path"] for record in records],
        "artifacts_written": [str(state_path)],
        "next_actions": [] if action is None else [action], "warnings": warnings,
    })


def command_import_reviewed_legacy(args: argparse.Namespace) -> None:
    state_path = Path(args.state).resolve()
    root = state_path.parent
    paths = {
        "page_map": Path(args.page_map).resolve(),
        "chunk_manifest": Path(args.chunk_manifest).resolve(),
        "policy": Path(args.policy).resolve(),
        "legacy_state": Path(args.legacy_state).resolve(),
        "legacy_page_map": Path(args.legacy_page_map).resolve(),
        "legacy_chunk_manifest": Path(args.legacy_chunk_manifest).resolve(),
        "legacy_policy": Path(args.legacy_policy).resolve(),
        "legacy_benchmark": Path(args.legacy_benchmark).resolve(),
        "legacy_review_inventory": Path(args.legacy_review_inventory).resolve(),
        "legacy_review": Path(args.legacy_review).resolve(),
        "compatibility_approval": Path(args.compatibility_approval).resolve(),
        "output": Path(args.output).resolve(),
        "provenance_output": Path(args.provenance_output).resolve(),
    }
    if args.legacy_draft:
        paths["legacy_draft"] = Path(args.legacy_draft).resolve()
    documents = {
        name: load_json(path)
        for name, path in paths.items()
        if name not in {"output", "provenance_output"}
    }
    state = load_json(state_path)
    errors: list[str] = []
    state_errors, warnings = validate_state(state, state_path=state_path)
    errors.extend(f"state: {error}" for error in state_errors)

    output_path = paths["output"]
    provenance_path = paths["provenance_output"]
    if output_path == provenance_path:
        errors.append("Benchmark and provenance outputs must be different files.")
    for path in (output_path, provenance_path):
        try:
            portable_relative_path(path, root)
        except SystemExit:
            raise
        if path.exists():
            errors.append(f"Refusing to overwrite an existing output: {path}")

    approval = documents["compatibility_approval"]
    errors.extend(
        f"compatibility approval: {error}"
        for error in schema_errors(approval, "benchmark-compatibility-approval.schema.json")
    )
    if errors:
        emit({"command": "import-reviewed-legacy", "ok": False, "errors": errors, "warnings": warnings}, 1)

    native_v8 = approval.get("reuse_mode") == NATIVE_V8_REUSE_MODE
    if native_v8 and "legacy_draft" not in paths:
        emit({
            "command": "import-reviewed-legacy", "ok": False,
            "errors": ["Native V8 exact reuse requires --legacy-draft."],
            "warnings": warnings,
        }, 1)

    current_page_map = documents["page_map"]
    current_manifest = documents["chunk_manifest"]
    current_policy = documents["policy"]
    legacy_state = documents["legacy_state"]
    legacy_page_map = documents["legacy_page_map"]
    legacy_manifest = documents["legacy_chunk_manifest"]
    legacy_policy = documents["legacy_policy"]
    legacy_benchmark = documents["legacy_benchmark"]
    legacy_inventory = documents["legacy_review_inventory"]
    legacy_review = documents["legacy_review"]
    legacy_draft = documents.get("legacy_draft")
    digests = {name: file_sha256(path) for name, path in paths.items() if path.is_file()}

    for document, schema_name, label in (
        (current_page_map, "page-map.schema.json", "Current page map"),
        (legacy_page_map, "page-map.schema.json", "Legacy page map"),
        (current_manifest, "chunk-manifest.schema.json", "Current chunk manifest"),
        (legacy_manifest, "chunk-manifest.schema.json", "Legacy chunk manifest"),
        (current_policy, "evaluation-policy-v4.schema.json", "Current policy"),
    ):
        errors.extend(f"{label}: {error}" for error in schema_errors(document, schema_name))
    if native_v8:
        errors.extend(f"Legacy policy: {error}" for error in schema_errors(legacy_policy, "evaluation-policy-v4.schema.json"))
    for document, field, label in (
        (current_page_map, "page_map_sha256", "Current page map"),
        (legacy_page_map, "page_map_sha256", "Legacy page map"),
        (current_manifest, "chunk_manifest_sha256", "Current chunk manifest"),
        (legacy_manifest, "chunk_manifest_sha256", "Legacy chunk manifest"),
        (current_policy, "policy_sha256", "Current policy"),
        (legacy_policy, "policy_sha256", "Legacy policy"),
        (legacy_benchmark, "benchmark_sha256", "Legacy benchmark"),
    ):
        if document.get(field) != canonical_field_hash(document, field):
            errors.append(f"{label} canonical {field} does not recompute.")

    if digests["page_map"] != digests["legacy_page_map"]:
        errors.append("Legacy and current page maps are not byte-identical.")
    if digests["chunk_manifest"] != digests["legacy_chunk_manifest"]:
        errors.append("Legacy and current chunk manifests are not byte-identical.")
    if current_page_map.get("page_map_sha256") != legacy_page_map.get("page_map_sha256"):
        errors.append("Legacy and current page-map canonical identities differ.")
    if current_manifest.get("chunk_manifest_sha256") != legacy_manifest.get("chunk_manifest_sha256"):
        errors.append("Legacy and current chunk-manifest canonical identities differ.")
    if native_v8 and digests["policy"] != digests["legacy_policy"]:
        errors.append("Native V8 reuse requires byte-identical legacy and current policies.")

    source_sha256 = state.get("source", {}).get("sha256")
    for document, label in (
        (current_page_map, "current page map"), (legacy_page_map, "legacy page map"),
        (current_policy.get("source_scope", {}), "current policy"),
        (legacy_policy.get("source_scope", {}), "legacy policy"),
        (legacy_benchmark, "legacy benchmark"), (legacy_state.get("source", {}), "legacy state"),
    ):
        if document.get("source_sha256") != source_sha256 and label != "legacy state":
            errors.append(f"The {label} source identity does not match canonical state.")
        if label == "legacy state" and document.get("sha256") != source_sha256:
            errors.append("The legacy state source identity does not match canonical state.")
    if native_v8 and legacy_draft.get("source_sha256") != source_sha256:
        errors.append("The native V8 draft source identity does not match canonical state.")
    for policy, label in ((current_policy, "Current"), (legacy_policy, "Legacy")):
        scope = policy.get("source_scope", {})
        if scope.get("page_map_sha256") != current_page_map.get("page_map_sha256"):
            errors.append(f"{label} policy page-map identity does not match.")
        if scope.get("chunk_manifest_sha256") != current_manifest.get("chunk_manifest_sha256"):
            errors.append(f"{label} policy chunk-manifest identity does not match.")
        if policy.get("freeze", {}).get("candidate_seen") is not False:
            errors.append(f"{label} policy must have been frozen before candidate exposure.")
    if current_policy.get("audit_design", {}).get("candidate_blindness") != "required":
        errors.append("Current V8 policy must require candidate blindness.")
    if current_policy.get("audit_design", {}).get("mode") != "full":
        errors.append("Current V8 policy must select a full audit.")

    for stage in ("initialize", "page_mapping", "chunk_definition", "define_policy", "source_chunk_preparation"):
        if state.get("stages", {}).get(stage, {}).get("status") != "completed":
            errors.append(f"Canonical state stage {stage} must already be completed.")
    for stage in ("source_subject_discovery", "benchmark_synthesis", "benchmark_review", "benchmark_freeze"):
        if state.get("stages", {}).get(stage, {}).get("status") != "not_started":
            errors.append(f"Canonical state stage {stage} must be not_started for compatibility import.")
    if state.get("candidate") is not None or any(
        item.get("stage") == "candidate_normalization"
        for item in state.get("artifacts", []) if isinstance(item, dict)
    ):
        errors.append("Canonical state shows candidate exposure or registration.")
    for stage in (
        "candidate_normalization", "locator_chunk_preparation", "locator_audit",
        "missing_access_audit", "structure_audit", "scoring", "web_report",
    ):
        if state.get("stages", {}).get(stage, {}).get("status") != "not_started":
            errors.append(f"Canonical state shows candidate-era activity at {stage}.")
    if not registered_file_matches(state, state_path, "page_mapping", paths["page_map"]):
        errors.append("Current page map is not the exact registered page_mapping artifact.")
    if not registered_file_matches(state, state_path, "chunk_definition", paths["chunk_manifest"]):
        errors.append("Current chunk manifest is not the exact registered chunk_definition artifact.")
    if not registered_file_matches(state, state_path, "define_policy", paths["policy"]):
        errors.append("Current policy is not the exact registered define_policy artifact.")

    if legacy_state.get("evaluation_id") != legacy_benchmark.get("evaluation_id"):
        errors.append("Legacy state evaluation_id does not match the benchmark.")
    for stage in ("source_subject_discovery", "benchmark_synthesis", "benchmark_review", "benchmark_freeze"):
        if legacy_state.get("stages", {}).get(stage, {}).get("status") != "completed":
            errors.append(f"Legacy state does not complete {stage}.")
    if (
        legacy_state.get("candidate") is not None
        or legacy_benchmark.get("candidate_blindness") != "preserved"
    ):
        errors.append("Legacy benchmark state does not preserve candidate blindness.")
    if any(
        item.get("stage") == "candidate_normalization"
        for item in legacy_state.get("artifacts", []) if isinstance(item, dict)
    ):
        errors.append("Legacy release evidence contains candidate-normalization artifacts.")
    if native_v8:
        native_state_for_validation = deepcopy(legacy_state)
        historical_profile = native_state_for_validation.get("configuration", {}).get("scoring_identity", {}).get("dimension_calculation_profile")
        if historical_profile in {"subject-index-dimension-calculation-v4", "subject-index-dimension-calculation-v5"}:
            if legacy_state.get("stages", {}).get("scoring", {}).get("status") != "not_started":
                errors.append("Native V8 historical calculation profile is allowed only before scoring.")
            # Explicit reviewed source-only import: normalize the validation copy,
            # preserve original release bytes, and never reinterpret a scored result.
            config = native_state_for_validation["configuration"]
            config["policy_profile"] = "subject-index-standard-policy-v8.2"
            config["rubric_version"] = "subject-index-rubric-v8.2"
            config["scoring_identity"] = {"rubric_version": "subject-index-rubric-v8.2", "dimension_calculation_profile": "subject-index-dimension-calculation-v7"}
        elif historical_profile != "subject-index-dimension-calculation-v7":
            errors.append("Native V8 source-only state has an unsupported calculation-profile identity.")
        native_state_errors, _ = validate_state(native_state_for_validation, state_path=paths["legacy_state"], check_files=False)
        errors.extend(f"Native V8 state: {error}" for error in native_state_errors)
        for stage in (
            "candidate_normalization", "locator_chunk_preparation", "locator_audit",
            "missing_access_audit", "structure_audit", "scoring", "web_report",
        ):
            if legacy_state.get("stages", {}).get(stage, {}).get("status") != "not_started":
                errors.append(f"Native V8 source-only state shows candidate-era activity at {stage}.")
        registrations = (
            ("define_policy", "legacy_policy"), ("page_mapping", "legacy_page_map"),
            ("chunk_definition", "legacy_chunk_manifest"), ("benchmark_synthesis", "legacy_draft"),
            ("benchmark_review", "legacy_review_inventory"), ("benchmark_review", "legacy_review"),
            ("benchmark_freeze", "legacy_benchmark"),
        )
        for stage, name in registrations:
            if not legacy_registered_hash(legacy_state, stage, digests[name]):
                errors.append(f"Native V8 state does not register the exact {name} artifact at {stage}.")
        errors.extend(native_v8_review_errors(
            paths["legacy_draft"], legacy_draft, legacy_benchmark,
            legacy_inventory, legacy_review,
        ))
    else:
        legacy_workflow = legacy_state.get("benchmark_workflow", {})
        if legacy_workflow.get("candidate_blindness") != "preserved":
            errors.append("Legacy benchmark workflow does not preserve candidate blindness.")
        final_identity = legacy_workflow.get("final_benchmark", {})
        if final_identity.get("file_sha256") != digests["legacy_benchmark"] or final_identity.get("canonical_sha256") != legacy_benchmark.get("benchmark_sha256"):
            errors.append("Legacy state final-benchmark identity does not match the supplied frozen artifact.")
        for stage, name in (
            ("define_policy", "legacy_policy"), ("page_mapping", "legacy_page_map"),
            ("chunk_definition", "legacy_chunk_manifest"), ("benchmark_review", "legacy_review_inventory"),
            ("benchmark_review", "legacy_review"), ("benchmark_freeze", "legacy_benchmark"),
        ):
            if not legacy_registered_hash(legacy_state, stage, digests[name]):
                errors.append(f"Legacy state does not register the exact {name} artifact at {stage}.")
        errors.extend(legacy_review_errors(legacy_benchmark, digests["legacy_benchmark"], legacy_inventory, legacy_review))

    expected_legacy = {
        "evaluation_id": legacy_benchmark.get("evaluation_id"),
        "source_sha256": legacy_benchmark.get("source_sha256"),
        "benchmark_id": legacy_benchmark.get("benchmark_id"),
        "version": legacy_benchmark.get("version"),
        "benchmark_file_sha256": digests["legacy_benchmark"],
        "benchmark_sha256": legacy_benchmark.get("benchmark_sha256"),
        "policy_file_sha256": digests["legacy_policy"],
        "policy_sha256": legacy_policy.get("policy_sha256"),
        "page_map_file_sha256": digests["legacy_page_map"],
        "page_map_sha256": legacy_page_map.get("page_map_sha256"),
        "chunk_manifest_file_sha256": digests["legacy_chunk_manifest"],
        "chunk_manifest_sha256": legacy_manifest.get("chunk_manifest_sha256"),
        "review_file_sha256": digests["legacy_review"],
        "review_inventory_file_sha256": digests["legacy_review_inventory"],
        "state_file_sha256": digests["legacy_state"],
    }
    if native_v8:
        expected_legacy.update({
            "draft_file_sha256": digests["legacy_draft"],
            "draft_canonical_sha256": canonical_hash(legacy_draft),
        })
        if approval["release_transport"]["checkpoint_state_file_sha256"] != digests["legacy_state"]:
            errors.append("Native V8 release transport does not identify the supplied source-only state.")
    else:
        expected_legacy["artifact_freeze_commit"] = approval["legacy"]["artifact_freeze_commit"]
    if approval.get("legacy") != expected_legacy:
        errors.append("Compatibility approval legacy identity does not exactly match the supplied release evidence.")
    expected_current = {
        "evaluation_id": state.get("evaluation_id"),
        "source_sha256": source_sha256,
        "benchmark_id": approval["current"]["benchmark_id"],
        "version": approval["current"]["version"],
        "policy_file_sha256": digests["policy"],
        "policy_sha256": current_policy.get("policy_sha256"),
        "page_map_file_sha256": digests["page_map"],
        "page_map_sha256": current_page_map.get("page_map_sha256"),
        "chunk_manifest_file_sha256": digests["chunk_manifest"],
        "chunk_manifest_sha256": current_manifest.get("chunk_manifest_sha256"),
        "frozen_at": approval["current"]["frozen_at"],
        "benchmark_sha256": approval["current"]["benchmark_sha256"],
    }
    if approval.get("current") != expected_current:
        errors.append("Compatibility approval current identity does not exactly match canonical V8 inputs.")
    if approval["current"]["benchmark_id"] == legacy_benchmark.get("benchmark_id"):
        errors.append("Compatibility import must issue a distinct V8-bound benchmark_id.")
    if not native_v8 and approval["current"]["policy_sha256"] == legacy_benchmark.get("policy_sha256"):
        errors.append("Compatibility import requires an actual policy identity rebind.")
    if native_v8 and approval["current"]["policy_sha256"] != legacy_benchmark.get("policy_sha256"):
        errors.append("Native V8 reuse requires the unchanged frozen policy identity.")

    normalized, normalization_errors = normalized_legacy_benchmark(legacy_benchmark, approval)
    errors.extend(normalization_errors)
    if not normalization_errors:
        errors.extend(f"Imported benchmark: {error}" for error in final_benchmark_structure_errors(normalized))
        if normalized.get("benchmark_sha256") != approval["current"]["benchmark_sha256"]:
            errors.append("Compatibility approval expected benchmark identity does not match deterministic normalization.")
        restored = deepcopy(normalized)
        for field in ("benchmark_id", "version", "evaluation_id", "policy_sha256", "freeze", "benchmark_sha256"):
            restored[field] = deepcopy(legacy_benchmark[field])
        restored.pop("compatibility_import", None)
        if not native_v8:
            for relationship in restored.get("relationships", []):
                relationship["type"] = relationship.pop("relationship_type")
        if restored != legacy_benchmark:
            errors.append("Normalization is not lossless outside the explicitly approved fields.")
    stable_ids, stable_id_errors = stable_id_summary(normalized)
    errors.extend(stable_id_errors)
    legacy_stable_ids, legacy_stable_id_errors = stable_id_summary(legacy_benchmark)
    errors.extend(legacy_stable_id_errors)
    if stable_ids != legacy_stable_ids:
        errors.append("Stable subject, relationship, reader-task, or evidence identities changed.")

    if errors:
        emit({
            "command": "import-reviewed-legacy", "ok": False,
            "evaluation_id": state.get("evaluation_id"), "errors": errors,
            "warnings": warnings, "artifacts_written": [],
        }, 1)

    stamp = now()
    benchmark_content = json_bytes(normalized)
    benchmark_file_sha256 = bytes_sha256(benchmark_content)
    provenance = {
        "schema_version": COMPATIBILITY_PROVENANCE_SCHEMA,
        "migration_id": approval["approval_id"],
        "imported_at": stamp,
        "operation": COMPATIBILITY_OPERATION,
        "compatibility_approval": {
            "approval_id": approval["approval_id"],
            "file_sha256": digests["compatibility_approval"],
        },
        "legacy": expected_legacy,
        "current": {**expected_current, "benchmark_file_sha256": benchmark_file_sha256},
        "normalization": {
            "operations": [] if native_v8 else [MECHANICAL_NORMALIZATION],
            "relationships_normalized": 0 if native_v8 else len(normalized["relationships"]),
            "semantic_content_preserved": True,
        },
        "preserved_stable_ids": stable_ids,
    }
    if native_v8:
        provenance.update({
            "reuse_mode": NATIVE_V8_REUSE_MODE,
            "release_transport": deepcopy(approval["release_transport"]),
        })
    provenance_errors = schema_errors(provenance, "benchmark-compatibility-import-provenance.schema.json")
    if provenance_errors:
        fail("generated_provenance_invalid", "Generated migration provenance is invalid.", provenance_errors)
    provenance_content = json_bytes(provenance)
    provenance_file_sha256 = bytes_sha256(provenance_content)

    updated = deepcopy(state)
    records: list[dict[str, Any]] = []
    evidence_kind = "native_v8" if native_v8 else "legacy"
    registrations = [
        (paths["legacy_state"], "source_subject_discovery", f"reviewed_{evidence_kind}_discovery_release_evidence", legacy_state.get("schema_version")),
        (paths["legacy_page_map"], "source_subject_discovery", f"reviewed_{evidence_kind}_page_map_evidence", legacy_page_map.get("schema_version")),
        (paths["legacy_chunk_manifest"], "source_subject_discovery", f"reviewed_{evidence_kind}_chunk_manifest_evidence", legacy_manifest.get("schema_version")),
        (paths["legacy_policy"], "source_subject_discovery", f"reviewed_{evidence_kind}_policy_evidence", legacy_policy.get("schema_version")),
        (paths["legacy_benchmark"], "benchmark_synthesis", f"imported_reviewed_{evidence_kind}_benchmark", legacy_benchmark.get("schema_version")),
        (paths["legacy_review_inventory"], "benchmark_review", "legacy_full_review_inventory_evidence", legacy_inventory.get("schema_version")),
        (paths["legacy_review"], "benchmark_review", "legacy_full_review_evidence", legacy_review.get("schema_version")),
        (paths["compatibility_approval"], "benchmark_review", "benchmark_compatibility_approval", COMPATIBILITY_APPROVAL_SCHEMA),
        (output_path, "benchmark_freeze", "source_benchmark", normalized.get("schema_version")),
        (provenance_path, "benchmark_freeze", "benchmark_compatibility_import_provenance", COMPATIBILITY_PROVENANCE_SCHEMA),
    ]
    if native_v8:
        registrations.insert(4, (
            paths["legacy_draft"], "benchmark_synthesis", "imported_reviewed_native_v8_draft", legacy_draft.get("schema_version")
        ))
    planned_digests = {output_path: benchmark_file_sha256, provenance_path: provenance_file_sha256}
    for path, stage, artifact_type, schema_version in registrations:
        relative = portable_relative_path(path, root)
        digest = planned_digests[path] if path in planned_digests else file_sha256(path)
        records.append({
            "artifact_id": artifact_id(relative, digest), "stage": stage,
            "artifact_type": artifact_type, "path": relative, "sha256": digest,
            "media_type": "application/json", "schema_version": schema_version,
            "visibility": "private", "retention": "required", "frozen": True,
            "recorded_at": stamp,
        })
    updated["artifacts"].extend(records)
    updated["artifacts"].sort(key=lambda item: item["path"])
    notes = {
        "source_subject_discovery": "Imported exact candidate-blind native V8 release evidence; discovery was not rerun.",
        "benchmark_synthesis": "Imported the exact independently reviewed native V8 draft and frozen benchmark; synthesis was not rerun.",
        "benchmark_review": "Validated the historical full review and a separate candidate-blind exact-reuse approval; editorial review was not rerun.",
        "benchmark_freeze": "Rebound only evaluation wrapper metadata under the unchanged V8 policy; the full freeze workflow was not rerun.",
    } if native_v8 else {
        "source_subject_discovery": "Imported exact candidate-blind legacy discovery release evidence; discovery was not rerun.",
        "benchmark_synthesis": "Imported the exact independently reviewed legacy frozen benchmark as synthesis evidence; synthesis was not rerun.",
        "benchmark_review": "Validated the legacy full review and a separate candidate-blind V8 compatibility approval; editorial review was not rerun.",
        "benchmark_freeze": "Mechanically normalized and rebound the reviewed legacy benchmark to the registered V8 policy; the full freeze workflow was not rerun.",
    }
    for stage, note in notes.items():
        updated["stages"][stage] = {"status": "completed", "updated_at": stamp, "notes": [note]}
    updated["updated_at"] = stamp
    updated_errors, updated_warnings = validate_state(updated, state_path=state_path, check_files=False)
    if updated_errors:
        fail("canonical_state_invalid", "Compatibility import would leave invalid canonical state.", updated_errors)

    state_content = json_bytes(updated)
    temporary_files = {
        output_path.with_suffix(output_path.suffix + ".compat-import.tmp"): benchmark_content,
        provenance_path.with_suffix(provenance_path.suffix + ".compat-import.tmp"): provenance_content,
        state_path.with_suffix(state_path.suffix + ".compat-import.tmp"): state_content,
    }
    if any(path.exists() for path in temporary_files):
        fail("temporary_path_exists", "A compatibility-import temporary file already exists; remove it after verifying no import is active.")
    created_temporaries: list[Path] = []
    created_outputs: list[Path] = []
    try:
        for path, content in temporary_files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            created_temporaries.append(path)
        output_temporary, provenance_temporary, state_temporary = temporary_files
        output_temporary.replace(output_path)
        created_outputs.append(output_path)
        provenance_temporary.replace(provenance_path)
        created_outputs.append(provenance_path)
        state_temporary.replace(state_path)
    except OSError as exc:
        for path in [*created_outputs, *created_temporaries]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        fail("atomic_write_failed", f"Compatibility import did not commit: {exc}")

    action = next_stage(updated)
    result = {
        "command": "import-reviewed-legacy", "ok": True,
        "evaluation_id": updated["evaluation_id"],
        "benchmark_id": normalized["benchmark_id"],
        "benchmark_sha256": normalized["benchmark_sha256"],
        "stages_completed": list(notes),
        "artifacts_registered": [record["path"] for record in records],
        "artifacts_written": [str(output_path), str(provenance_path), str(state_path)],
        "next_actions": [] if action is None else [action],
        "warnings": [*warnings, *updated_warnings],
    }
    if native_v8:
        result["legacy_state_file_sha256"] = expected_legacy["state_file_sha256"]
    else:
        result["legacy_artifact_freeze_commit"] = expected_legacy["artifact_freeze_commit"]
    emit(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    screen = subparsers.add_parser("screen")
    screen.add_argument("--draft", required=True)
    screen.add_argument("--output", required=True)
    screen.add_argument("--near-duplicate-threshold", type=float, default=0.93)
    screen.set_defaults(func=command_screen)
    review = subparsers.add_parser("validate-review")
    review.add_argument("--draft", required=True)
    review.add_argument("--inventory", required=True)
    review.add_argument("--review", required=True)
    review.set_defaults(func=command_validate_review)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--state", required=True)
    freeze.add_argument("--draft", required=True)
    freeze.add_argument("--inventory", required=True)
    freeze.add_argument("--review", required=True)
    freeze.add_argument("--final", required=True)
    freeze.set_defaults(func=command_freeze)
    migration = subparsers.add_parser(
        "import-reviewed-legacy",
        help="Import a candidate-blind, fully reviewed legacy benchmark under the current V8 policy.",
    )
    migration.add_argument("--state", required=True)
    migration.add_argument("--page-map", required=True)
    migration.add_argument("--chunk-manifest", required=True)
    migration.add_argument("--policy", required=True)
    migration.add_argument("--legacy-state", required=True)
    migration.add_argument("--legacy-page-map", required=True)
    migration.add_argument("--legacy-chunk-manifest", required=True)
    migration.add_argument("--legacy-policy", required=True)
    migration.add_argument("--legacy-draft")
    migration.add_argument("--legacy-benchmark", required=True)
    migration.add_argument("--legacy-review-inventory", required=True)
    migration.add_argument("--legacy-review", required=True)
    migration.add_argument("--compatibility-approval", required=True)
    migration.add_argument("--output", required=True)
    migration.add_argument("--provenance-output", required=True)
    migration.set_defaults(func=command_import_reviewed_legacy)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command in {"freeze", "import-reviewed-legacy"}:
        with evaluation_mutation_lock(Path(args.state)):
            args.func(args)
    else:
        args.func(args)


if __name__ == "__main__":
    main()
