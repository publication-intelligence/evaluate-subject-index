#!/usr/bin/env python3
"""Normalize, validate, and register a current candidate index."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from benchmark_review_cli import final_benchmark_structure_errors
from item_projection_core import build_inventory
from state_cli import (
    STAGES,
    artifact_id as state_artifact_id,
    evaluation_mutation_lock,
    next_stage,
    portable_relative_path,
    save_state,
    validate_state,
)
from schema_validation import schema_errors


CANONICAL_ARTIFACT_KEYS = (
    "layout_extraction",
    "candidate_index",
    "item_inventory",
)
FORBIDDEN_PREJUDGMENT_KEYS = {
    "score",
    "rating",
    "density",
    "judgment",
    "defect",
    "coverage_judgment",
    "locator_support",
    "missing_access",
    "editorial_quality",
}
class PreparationError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require(condition: bool, code: str, message: str, details: Any = None) -> None:
    if not condition:
        raise PreparationError(code, message, details)


def emit(payload: dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    raise SystemExit(exit_code)


def load_json(path: Path, label: str = "JSON artifact") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PreparationError("file_not_found", f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PreparationError("invalid_json", f"{label} is invalid JSON: {exc}") from exc
    require(isinstance(value, dict), "invalid_document", f"{label} must be a JSON object.")
    return value


def load_json_snapshot(path: Path, label: str = "JSON artifact") -> tuple[dict[str, Any], bytes, str]:
    try:
        payload = path.read_bytes()
    except FileNotFoundError as exc:
        raise PreparationError("file_not_found", f"{label} does not exist: {path}") from exc
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreparationError("invalid_json", f"{label} is invalid UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict), "invalid_document", f"{label} must be a JSON object.")
    return value, payload, sha256_bytes(payload)


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    require(path.is_file(), "file_not_found", f"File does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value: dict[str, Any], own_hash_field: str) -> str:
    clone = deepcopy(value)
    clone.pop(own_hash_field, None)
    encoded = json.dumps(clone, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_id(prefix: str, candidate_sha256: str, identity: Any) -> str:
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{candidate_sha256}\n{canonical}".encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def artifact_id(path: str, digest: str) -> str:
    value = hashlib.sha256(f"{path}\0{digest}".encode("utf-8")).hexdigest()[:12].upper()
    return f"ART-{value}"


def normalize_candidate_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower())
    slug = slug.strip("-")
    require(bool(slug), "invalid_candidate_id", "candidate-id must contain at least one letter or digit.")
    return slug


def require_sha256(value: Any, field: str) -> str:
    require(isinstance(value, str) and bool(re.fullmatch(r"[a-f0-9]{64}", value)), "invalid_sha256", f"{field} must be a lowercase SHA-256 digest.")
    return value


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def require_no_symlink_components(path: Path, label: str) -> None:
    """Reject every existing symlink component before an output mutation."""
    lexical = Path(os.path.abspath(path))
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        require(not current.is_symlink(), "unsafe_output_symlink", f"{label} contains a symlink component: {current}")


def require_safe_output_path(path: Path, root: Path, label: str) -> None:
    """Require a lexical, symlink-free output path beneath a trusted real root."""
    lexical_root = Path(os.path.abspath(root))
    lexical_path = Path(os.path.abspath(path))
    try:
        lexical_path.relative_to(lexical_root)
    except ValueError as exc:
        raise PreparationError("unsafe_output_path", f"{label} is outside the canonical evaluation root: {lexical_path}") from exc
    require_no_symlink_components(lexical_root, "Canonical evaluation root")
    require_no_symlink_components(lexical_path.parent, label)
    require(not lexical_path.is_symlink(), "unsafe_output_symlink", f"{label} cannot be a symlink: {lexical_path}")
    require(path_is_within(lexical_path.parent, lexical_root), "unsafe_output_path", f"{label} resolves outside the canonical evaluation root: {lexical_path}")


def replace_bytes_atomic(path: Path, payload: bytes) -> None:
    """Replace one regular file using a same-directory temporary file."""
    require_no_symlink_components(path.parent, "Output parent")
    require(not path.is_symlink(), "unsafe_output_symlink", f"Output cannot be a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    require_no_symlink_components(path.parent, "Output parent")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    require(
        not path.is_absolute() and ".." not in path.parts and value not in {"", "."} and "\\" not in value,
        "unsafe_path",
        f"Path is not a safe relative POSIX path: {value}",
    )
    return str(path)


def normalize_locator_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"[‐‑‒–—−]", "-", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    if re.fullmatch(r"[0-9]+", normalized):
        normalized = str(int(normalized))
    return normalized.casefold()


def validate_self_hash(value: dict[str, Any], field: str, label: str) -> None:
    recorded = require_sha256(value.get(field), f"{label}.{field}")
    require(recorded == canonical_hash(value, field), "canonical_hash_mismatch", f"{label} canonical hash does not recompute.")


def require_schema(value: Any, schema_name: str, label: str) -> None:
    errors = schema_errors(value, schema_name)
    require(not errors, "schema_validation_failed", f"{label} is structurally invalid.", errors)


def load_source_identities(
    state_path: Path,
    page_map_path: Path,
    chunk_manifest_path: Path,
    policy_path: Path,
    source_edition: str | None,
    documents: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    documents = documents or {}
    state = documents.get("state") or load_json(state_path, "Evaluation state")
    page_map = documents.get("page_map") or load_json(page_map_path, "Page map")
    chunks = documents.get("chunk_manifest") or load_json(chunk_manifest_path, "Chunk manifest")
    policy = documents.get("policy") or load_json(policy_path, "Evaluation policy")
    require_schema(state, "evaluation-state.schema.json", "Evaluation state")
    require_schema(page_map, "page-map.schema.json", "Page map")
    require_schema(chunks, "chunk-manifest.schema.json", "Chunk manifest")
    require_schema(policy, "evaluation-policy-v4.schema.json", "Evaluation policy")
    validate_self_hash(page_map, "page_map_sha256", "Page map")
    validate_self_hash(chunks, "chunk_manifest_sha256", "Chunk manifest")
    validate_self_hash(policy, "policy_sha256", "Evaluation policy")
    source = state.get("source") if isinstance(state.get("source"), dict) else {}
    source_sha = require_sha256(source.get("sha256"), "state.source.sha256")
    edition = source_edition or source.get("edition")
    require(isinstance(edition, str) and edition.strip(), "edition_identity_required", "A frozen source-edition identity is required for candidate preparation.")
    require(page_map.get("source_sha256") == source_sha, "source_hash_mismatch", "Page map source hash does not match the evaluation state.")
    require(chunks.get("page_map_sha256") == page_map.get("page_map_sha256"), "page_map_mismatch", "Chunk manifest does not reference the supplied page map.")
    scope = policy.get("source_scope") if isinstance(policy.get("source_scope"), dict) else {}
    for key, actual in (
        ("source_sha256", source_sha),
        ("page_map_sha256", page_map.get("page_map_sha256")),
        ("chunk_manifest_sha256", chunks.get("chunk_manifest_sha256")),
    ):
        require(scope.get(key) == actual, "policy_identity_mismatch", f"Evaluation policy {key} does not match the frozen source identity.")
    configuration = state.get("configuration") if isinstance(state.get("configuration"), dict) else {}
    policy_profile = policy.get("policy_profile", {}).get("id")
    rubric_version = configuration.get("rubric_version")
    audit_mode = policy.get("audit_design", {}).get("mode")
    require(configuration.get("policy_profile") == policy_profile, "policy_identity_mismatch", "State and policy profile identities differ.")
    require(rubric_version == "subject-index-rubric-v8", "rubric_identity_mismatch", "Candidate preparation requires the current V8 rubric identity.")
    require(configuration.get("audit_mode") == audit_mode, "audit_mode_mismatch", "State and policy audit modes differ.")
    return {
        "state": state,
        "page_map": page_map,
        "chunk_manifest": chunks,
        "policy": policy,
        "source_sha256": source_sha,
        "source_edition": edition.strip(),
        "page_map_sha256": page_map["page_map_sha256"],
        "chunk_manifest_sha256": chunks["chunk_manifest_sha256"],
        "policy_sha256": policy["policy_sha256"],
        "policy_profile": policy_profile,
        "rubric_version": rubric_version,
        "audit_mode": audit_mode,
    }


def flatten_layout(layout: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    pages = layout.get("pages") if isinstance(layout.get("pages"), list) else []
    regions: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    for page in pages:
        for region in page.get("regions", []):
            region_copy = {**region, "candidate_pdf_page": page.get("candidate_pdf_page")}
            regions.append(region_copy)
            for line in region.get("lines", []):
                lines.append({
                    **line,
                    "candidate_pdf_page": page.get("candidate_pdf_page"),
                    "region_id": region.get("region_id"),
                    "region_order": region.get("region_order"),
                })
    return pages, regions, lines


def merge_continuation_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for line in lines:
        if line.get("inferred_boundary") == "header_footer" or line.get("excluded_from_index") is True:
            continue
        text = str(line.get("displayed_line_text", "")).strip()
        if not text:
            continue
        continuation = line.get("continuation_status") in {
            "continues_previous",
            "continued_from_previous_column",
            "continued_from_previous_page",
        }
        if continuation and groups:
            previous = groups[-1]
            joiner = "" if text[:1] in {",", ";", ":"} else " "
            previous["displayed_line_text"] += joiner + text
            previous["original_displayed_form"] += "\n" + str(line.get("original_displayed_form", text))
            previous["line_ids"].append(line.get("line_id"))
            previous["candidate_pdf_pages"].append(line.get("candidate_pdf_page"))
            previous["region_ids"].append(line.get("region_id"))
            previous["bboxes"].append(line.get("bbox"))
            previous["continuation_statuses"].append(line.get("continuation_status"))
            previous["extraction_warnings"].extend(line.get("extraction_warnings", []))
            continue
        groups.append({
            "displayed_line_text": text,
            "original_displayed_form": str(line.get("original_displayed_form", text)),
            "indentation_level": int(line.get("indentation_level", 0)),
            "line_ids": [line.get("line_id")],
            "candidate_pdf_pages": [line.get("candidate_pdf_page")],
            "region_ids": [line.get("region_id")],
            "bboxes": [line.get("bbox")],
            "continuation_statuses": [line.get("continuation_status")],
            "extraction_warnings": list(line.get("extraction_warnings", [])),
            "confidence": line.get("confidence"),
        })
    return groups


def split_references(payload: str) -> tuple[str, list[dict[str, str]], bool]:
    marker = re.compile(
        r"(?i)(?:^|[;,.]\s*)(see\s+also|see(?!\s+also\b))\s+(.+?)"
        r"(?=(?:\s*[;,.]\s*see(?:\s+also)?\s)|$)"
    )
    matches = list(marker.finditer(payload))
    references: list[dict[str, str]] = []
    for match in matches:
        target = match.group(2).strip(" ,;.")
        references.append({"type": "see also" if "also" in match.group(1).casefold() else "see", "target": target})
    malformed_marker = re.search(r"(?i)\bsee\b", payload) if not matches else None
    locator_text = (
        payload[: matches[0].start()].strip(" ,;.")
        if matches
        else payload[:malformed_marker.start()].strip(" ,;.") if malformed_marker
        else payload.strip()
    )
    malformed = malformed_marker is not None
    return locator_text, references, malformed


def looks_like_locator_payload(
    value: str,
    lookup: dict[str, dict[str, Any]],
    require_mapped: bool = False,
) -> bool:
    stripped = value.strip()
    if re.match(r"(?i)^see(?:\s+also)?\b", stripped):
        return True
    first = re.split(r"[,;]", stripped, maxsplit=1)[0].strip()
    if normalize_locator_key(first) in lookup:
        return True
    for separator in re.finditer(r"(?:–|—|‑|‒|−|--|-)", first):
        start = first[:separator.start()].strip()
        end = first[separator.end():].strip()
        if (
            start
            and end
            and normalize_locator_key(start) in lookup
            and normalize_locator_key(end) in lookup
        ):
            return True
    # Arbitrary alphabetic text is a heading continuation, not a locator.  Any
    # prefixed/alphabetic locator must be present in the frozen page map and is
    # accepted by the exact lookup above.  The fallback is limited to numeric
    # and Roman forms so prose such as ``continued mechanisms`` cannot create a
    # false heading boundary.
    return not require_mapped and bool(
        re.fullmatch(
            r"(?:[0-9]+|[ivxlcdm]+)(?:\s*[–—‑‒−-]\s*(?:[0-9]+|[ivxlcdm]+))?",
            first,
            re.I,
        )
    )


def split_heading_and_payload(text: str, lookup: dict[str, dict[str, Any]]) -> tuple[str, str]:
    for match in re.finditer(r"[,;:]|\s+", text):
        tail = text[match.end():].strip()
        if looks_like_locator_payload(tail, lookup, require_mapped=match.group().isspace()):
            return text[: match.start()].strip(), tail
    ref = re.search(r"(?i)\bsee(?:\s+also)?\b", text)
    if ref:
        return text[: ref.start()].strip(" ,;:."), text[ref.start():].strip()
    return text.strip(), ""


def page_map_lookup(page_map: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[int, int], list[dict[str, Any]]]:
    pages = page_map.get("pages") if isinstance(page_map.get("pages"), list) else []
    lookup: dict[str, dict[str, Any]] = {}
    index_by_document_page: dict[int, int] = {}
    for index, page in enumerate(pages):
        index_by_document_page[page.get("document_page")] = index
        key = page.get("normalized_locator_key")
        if isinstance(key, str) and page.get("accepts_index_locators"):
            require(key not in lookup, "ambiguous_page_map", f"Indexable locator key appears more than once: {key}")
            lookup[key] = page
    return lookup, index_by_document_page, pages


def resolve_abbreviated_endpoint(
    start: dict[str, Any],
    raw_end: str,
    pages: list[dict[str, Any]],
    index_by_document_page: dict[int, int],
) -> tuple[dict[str, Any] | None, str | None]:
    start_label = str(start.get("source_page_label", ""))
    if not (start_label.isdigit() and raw_end.isdigit() and len(raw_end) < len(start_label)):
        return None, None
    start_index = index_by_document_page[start["document_page"]]
    completed_label = start_label[:-len(raw_end)] + raw_end
    candidates = [
        page for page in pages[start_index + 1:]
        if page.get("mapping_id") == start.get("mapping_id")
        and page.get("accepts_index_locators")
        and str(page.get("source_page_label", "")) == completed_label
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, "abbreviated_endpoint_ambiguous"
    return None, "abbreviated_endpoint_unresolved"


def locator_assignments_for_display(
    displayed: str,
    display_id: str,
    candidate_sha: str,
    lookup: dict[str, dict[str, Any]],
    index_by_document_page: dict[int, int],
    pages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    token = displayed.strip()
    normalized = normalize_locator_key(token)
    exact = lookup.get(normalized or "")
    exceptions: list[dict[str, Any]] = []
    if exact:
        locator_id = stable_id("LOC", candidate_sha, {"display_id": display_id, "document_page": exact["document_page"]})
        assignment = {
            "locator_id": locator_id,
            "display_id": display_id,
            "displayed_locator": token,
            "source_page_label": exact.get("source_page_label"),
            "normalized_locator_key": exact.get("normalized_locator_key"),
            "document_page": exact.get("document_page"),
            "mapping_status": "resolved",
            "range_id": None,
        }
        return [assignment], {"display_id": display_id, "displayed_locator": token, "kind": "point", "range_id": None, "mapping_status": "resolved", "locator_ids": [locator_id]}, []

    split_candidates: list[tuple[str, str, dict[str, Any], dict[str, Any] | None, str | None]] = []
    for separator in re.finditer(r"(?:–|—|‑|‒|−|--|-)", token):
        raw_start = token[:separator.start()].strip()
        raw_end = token[separator.end():].strip()
        if not raw_start or not raw_end:
            continue
        start = lookup.get(normalize_locator_key(raw_start) or "")
        if not start:
            continue
        end = lookup.get(normalize_locator_key(raw_end) or "")
        end_reason = None
        direct_precedes_start = bool(
            end
            and index_by_document_page.get(end.get("document_page"), -1)
            < index_by_document_page.get(start.get("document_page"), -1)
        )
        if not end or direct_precedes_start:
            abbreviated, abbreviated_reason = resolve_abbreviated_endpoint(start, raw_end, pages, index_by_document_page)
            if abbreviated is not None:
                end, end_reason = abbreviated, None
            elif not end:
                end_reason = abbreviated_reason
            else:
                end_reason = "range_endpoint_reversed"
        split_candidates.append((raw_start, raw_end, start, end, end_reason))
    if split_candidates:
        uniquely_resolved = [item for item in split_candidates if item[3] is not None]
        selected_splits = uniquely_resolved if uniquely_resolved else split_candidates
        if len(selected_splits) == 1:
            raw_start, raw_end, start, end, end_reason = selected_splits[0]
        else:
            raw_start, raw_end, start, end, end_reason = selected_splits[0]
            end = None
            end_reason = "range_boundary_ambiguous"
        range_id = stable_id("RANGE", candidate_sha, {"display_id": display_id, "displayed_locator": token})
        if start and end:
            start_index = index_by_document_page[start["document_page"]]
            end_index = index_by_document_page[end["document_page"]]
            between = pages[start_index:end_index + 1] if end_index >= start_index else []
            compatible = bool(between) and all(
                page.get("mapping_id") == start.get("mapping_id") == end.get("mapping_id")
                and page.get("accepts_index_locators")
                for page in between
            )
            if compatible:
                assignments = []
                for page in between:
                    locator_id = stable_id("LOC", candidate_sha, {"display_id": display_id, "document_page": page["document_page"]})
                    assignments.append({
                        "locator_id": locator_id,
                        "display_id": display_id,
                        "displayed_locator": token,
                        "source_page_label": page.get("source_page_label"),
                        "normalized_locator_key": page.get("normalized_locator_key"),
                        "document_page": page.get("document_page"),
                        "mapping_status": "resolved",
                        "range_id": range_id,
                    })
                return assignments, {
                    "display_id": display_id,
                    "displayed_locator": token,
                    "kind": "range",
                    "range_id": range_id,
                    "start_display": raw_start,
                    "end_display": raw_end,
                    "mapping_status": "resolved",
                    "locator_ids": [item["locator_id"] for item in assignments],
                }, []
        reason = end_reason or ("range_mapping_segment_mismatch" if start and end else "range_endpoint_unresolved")
        locator_id = stable_id("LOC", candidate_sha, {"display_id": display_id, "unresolved": token})
        assignment = {
            "locator_id": locator_id,
            "display_id": display_id,
            "displayed_locator": token,
            "source_page_label": None,
            "normalized_locator_key": normalized,
            "document_page": None,
            "mapping_status": "unresolved",
            "range_id": range_id,
        }
        exceptions.append({"type": reason, "related_ids": [display_id, locator_id], "displayed_form": token})
        return [assignment], {"display_id": display_id, "displayed_locator": token, "kind": "range", "range_id": range_id, "mapping_status": "unresolved", "locator_ids": [locator_id]}, exceptions

    locator_id = stable_id("LOC", candidate_sha, {"display_id": display_id, "unresolved": token})
    assignment = {
        "locator_id": locator_id,
        "display_id": display_id,
        "displayed_locator": token,
        "source_page_label": token or None,
        "normalized_locator_key": normalized,
        "document_page": None,
        "mapping_status": "unresolved",
        "range_id": None,
    }
    exceptions.append({"type": "locator_unresolved_or_malformed", "related_ids": [display_id, locator_id], "displayed_form": token})
    return [assignment], {"display_id": display_id, "displayed_locator": token, "kind": "point", "range_id": None, "mapping_status": "unresolved", "locator_ids": [locator_id]}, exceptions


def normalize_layout(layout: dict[str, Any], page_map: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    require_schema(layout, "candidate-layout-extraction.schema.json", "Candidate layout extraction")
    require_schema(page_map, "page-map.schema.json", "Page map")
    candidate_id = layout["candidate_id"]
    candidate_sha = layout["candidate_sha256"]
    lookup, index_by_document_page, pages = page_map_lookup(page_map)
    _, _, lines = flatten_layout(layout)
    groups = merge_continuation_lines(lines)
    records: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    heading_stack: list[str] = []

    for record_index, group in enumerate(groups):
        text = group["displayed_line_text"]
        heading, payload = split_heading_and_payload(text, lookup)
        indent = max(0, int(group.get("indentation_level", 0)))
        reference_only = not heading and bool(payload) and bool(heading_stack)
        if not heading and not reference_only:
            exception_id = stable_id("EXC", candidate_sha, {"record_index": record_index, "type": "missing_heading", "text": text})
            exceptions.append({"exception_id": exception_id, "type": "missing_heading", "status": "needs_review", "related_ids": group["line_ids"], "displayed_form": text, "detail": "No entry or subentry heading could be identified."})
            continue
        indentation_gap = indent > len(heading_stack)
        if reference_only:
            heading_path = heading_stack[:max(1, min(indent, len(heading_stack)))]
        elif indent == 0:
            heading_path = [heading]
            heading_stack = [heading]
        else:
            parent_depth = min(indent, len(heading_stack))
            heading_path = heading_stack[:parent_depth] + [heading]
            heading_stack = heading_path
        path_id = stable_id("PATH", candidate_sha, {"record_index": record_index, "heading_path": heading_path})
        record_id = stable_id("REC", candidate_sha, {"record_index": record_index, "line_ids": group["line_ids"]})
        if indentation_gap:
            exception_id = stable_id("EXC", candidate_sha, {"record_id": record_id, "type": "indentation_gap"})
            exceptions.append({"exception_id": exception_id, "type": "indentation_gap", "status": "needs_review", "related_ids": [record_id, *group["line_ids"]], "displayed_form": text, "detail": "Delivered indentation skipped an available parent level; the available parent chain was preserved without editorial repair."})

        locator_text, reference_specs, malformed_reference = split_references(payload)
        locator_tokens = [item.strip() for item in re.split(r"[,;]", locator_text) if item.strip()]
        locator_displays: list[dict[str, Any]] = []
        locator_assignments: list[dict[str, Any]] = []
        for display_index, token in enumerate(locator_tokens):
            display_id = stable_id("DISPLAY", candidate_sha, {"record_id": record_id, "display_index": display_index, "displayed_locator": token})
            assignments, display, display_exceptions = locator_assignments_for_display(
                token, display_id, candidate_sha, lookup, index_by_document_page, pages
            )
            locator_displays.append(display)
            locator_assignments.extend(assignments)
            for exception in display_exceptions:
                exception_id = stable_id("EXC", candidate_sha, {"record_id": record_id, "display_id": display_id, "type": exception["type"]})
                exceptions.append({
                    "exception_id": exception_id,
                    "status": "needs_review",
                    "record_id": record_id,
                    "line_ids": group["line_ids"],
                    "detail": "The displayed locator was retained exactly and was not guessed or repaired.",
                    **exception,
                })

        cross_references: list[dict[str, Any]] = []
        for reference_index, spec in enumerate(reference_specs):
            reference_id = stable_id("XREF", candidate_sha, {"record_id": record_id, "reference_index": reference_index, **spec})
            cross_references.append({
                "reference_id": reference_id,
                "type": spec["type"],
                "target": spec["target"],
                "target_path_id": None,
                "original_displayed_form": spec["target"],
            })
            if not spec["target"]:
                exception_id = stable_id("EXC", candidate_sha, {"reference_id": reference_id, "type": "malformed_cross_reference"})
                exceptions.append({"exception_id": exception_id, "type": "malformed_cross_reference", "status": "needs_review", "related_ids": [record_id, reference_id], "record_id": record_id, "line_ids": group["line_ids"], "displayed_form": text, "detail": "Cross-reference target is empty."})
        if malformed_reference:
            exception_id = stable_id("EXC", candidate_sha, {"record_id": record_id, "type": "malformed_cross_reference"})
            exceptions.append({"exception_id": exception_id, "type": "malformed_cross_reference", "status": "needs_review", "related_ids": [record_id], "record_id": record_id, "line_ids": group["line_ids"], "displayed_form": text, "detail": "A see marker could not be parsed without changing the delivered text."})
        if cross_references and locator_assignments:
            record_type = "mixed"
        elif cross_references:
            record_type = "cross_reference"
        elif locator_assignments:
            record_type = "page_bearing"
        else:
            record_type = "container"
        records.append({
            "record_id": record_id,
            "record_type": record_type,
            "path_id": path_id,
            "heading_path": heading_path,
            "delivered_indentation_level": indent,
            "original_displayed_form": group["original_displayed_form"],
            "locator_displays": locator_displays,
            "locator_assignments": locator_assignments,
            "cross_references": cross_references,
            "normalization_confidence": group.get("confidence"),
            "extraction_warnings": sorted(set(group.get("extraction_warnings", []))),
            "private_evidence": {
                "layout_line_ids": group["line_ids"],
                "candidate_pdf_pages": sorted(set(group["candidate_pdf_pages"])),
                "region_ids": list(dict.fromkeys(group["region_ids"])),
                "bboxes": group["bboxes"],
                "continuation_statuses": group["continuation_statuses"],
            },
        })

    candidate = {
        "schema_version": "candidate-index-v2",
        "candidate_id": candidate_id,
        "candidate_sha256": candidate_sha,
        "page_map_sha256": page_map.get("page_map_sha256"),
        "records": records,
        "normalization": {
            "engine": "candidate-preparation-cli",
            "engine_version": "1.0.0",
            "record_count": len(records),
            "main_heading_count": sum(len(item["heading_path"]) == 1 for item in records),
            "subheading_count": sum(len(item["heading_path"]) > 1 for item in records),
            "complete_heading_path_count": len(records),
            "displayed_locator_count": sum(len(item["locator_displays"]) for item in records),
            "expanded_locator_assignment_count": sum(len(item["locator_assignments"]) for item in records),
            "cross_reference_count": sum(len(item["cross_references"]) for item in records),
            "unresolved_locator_count": sum(assignment["mapping_status"] != "resolved" for item in records for assignment in item["locator_assignments"]),
            "editorial_corrections_applied": False,
            "benchmark_content_used": False,
        },
    }
    inventory = build_inventory(candidate)
    issue_report = {
        "schema_version": "candidate-normalization-issues-v1",
        "candidate_id": candidate_id,
        "candidate_sha256": candidate_sha,
        "page_map_sha256": page_map.get("page_map_sha256"),
        "issues": exceptions,
        "counts": {
            "total": len(exceptions),
            "by_type": {key: sum(item.get("type") == key for item in exceptions) for key in sorted({item.get("type") for item in exceptions})},
        },
    }
    return candidate, inventory, issue_report


def layout_accounting_errors(layout: dict[str, Any], candidate: dict[str, Any], issues: dict[str, Any]) -> list[str]:
    """Compute the full layout and normalization denominator gate."""
    pages, regions, lines = flatten_layout(layout)
    errors: list[str] = []
    id_groups = {
        "candidate PDF page": [page.get("candidate_pdf_page") for page in pages],
        "region": [region.get("region_id") for region in regions],
        "line": [line.get("line_id") for line in lines],
        "excluded line": [item.get("excluded_line_id") for item in layout.get("excluded_lines", [])],
    }
    for label, values in id_groups.items():
        duplicates = _duplicate_values(values)
        if duplicates:
            errors.append(f"Duplicate {label} identities: {duplicates}")
    for page in pages:
        page_regions = page.get("regions", [])
        actual_region_ids = [region.get("region_id") for region in page_regions]
        actual_line_ids = [line.get("line_id") for region in page_regions for line in region.get("lines", [])]
        if page.get("region_ids") != actual_region_ids:
            errors.append(f"Candidate PDF page {page.get('candidate_pdf_page')} region_ids do not match its regions")
        if page.get("line_ids") != actual_line_ids:
            errors.append(f"Candidate PDF page {page.get('candidate_pdf_page')} line_ids do not match its reading-order lines")
        for region in page_regions:
            region_lines = region.get("lines", [])
            if region.get("line_ids") != [line.get("line_id") for line in region_lines]:
                errors.append(f"Region {region.get('region_id')} line_ids do not match its lines")
            if region.get("line_count") != len(region_lines):
                errors.append(f"Region {region.get('region_id')} line_count does not recompute")
            for line in region_lines:
                if line.get("candidate_pdf_page") != page.get("candidate_pdf_page") or line.get("region_id") != region.get("region_id"):
                    errors.append(f"Line {line.get('line_id')} has inconsistent page or region ownership")
    excluded = layout.get("excluded_lines", [])
    expected_counts = {
        "pages": len(pages),
        "regions": len(regions),
        "lines": len(lines),
        "index_lines": sum(not line.get("excluded_from_index", False) for line in lines),
        "excluded_lines": len(excluded),
        "excluded_repeated_headers": sum(item.get("reason") == "repeated_page_header" for item in excluded),
        "excluded_repeated_footers": sum(item.get("reason") == "repeated_page_footer" for item in excluded),
        "excluded_page_number_footers": sum(item.get("reason") == "page_number_footer" for item in excluded),
        "lines_with_extraction_warnings": sum(bool(line.get("extraction_warnings")) for line in lines),
        "column_continuations": sum(line.get("continuation_status") == "continued_from_previous_column" for line in lines),
        "page_continuations": sum(line.get("continuation_status") == "continued_from_previous_page" for line in lines),
    }
    if layout.get("counts") != expected_counts:
        errors.append("Layout extraction counts do not recompute exactly")
    expected_lines = {
        line.get("line_id") for line in lines
        if line.get("inferred_boundary") != "header_footer" and line.get("excluded_from_index") is not True
    }
    candidate_lines = [
        line_id
        for record in candidate.get("records", [])
        for line_id in record.get("private_evidence", {}).get("layout_line_ids", [])
    ]
    missing_heading_lines = [
        line_id
        for issue in issues.get("issues", []) if issue.get("type") == "missing_heading"
        for line_id in issue.get("related_ids", []) if line_id in expected_lines
    ]
    accounted_lines = candidate_lines + missing_heading_lines
    if _duplicate_values(accounted_lines):
        errors.append("Normalization accounts for one or more layout lines more than once")
    if set(accounted_lines) != expected_lines:
        errors.append("Normalization does not account for every retained layout line exactly once")
    return errors


def paths_for_normalization_output(root: Path, candidate_id: str) -> dict[str, Path]:
    normalized = normalize_candidate_id(candidate_id)
    return {
        "layout_extraction": root / "candidates" / normalized / "candidate-layout-extraction.v1.json",
        "candidate_index": root / "candidates" / normalized / "candidate-index.v2.json",
        "item_inventory": root / "candidates" / normalized / "item-inventory.v2.json",
        "normalization_issues": root / "validation" / f"candidate-normalization-issues.{normalized}.v1.json",
    }


def command_normalize(args: argparse.Namespace) -> None:
    state_path = Path(args.state).resolve()
    page_map_path = Path(args.page_map).resolve()
    chunk_manifest_path = Path(args.chunk_manifest).resolve()
    policy_path = Path(args.policy).resolve()
    candidate_path = Path(args.candidate_file).resolve()
    layout_input_path = Path(args.layout).resolve()
    layout = load_json(layout_input_path, "Candidate layout extraction")
    require_schema(layout, "candidate-layout-extraction.schema.json", "Candidate layout extraction")
    require(layout.get("candidate_id") == args.candidate_id, "candidate_id_mismatch", "Command candidate ID does not match layout extraction.")
    identities = load_source_identities(state_path, page_map_path, chunk_manifest_path, policy_path, args.source_edition)
    require(layout.get("source_sha256") in {None, identities["source_sha256"]}, "source_hash_mismatch", "Layout extraction source identity conflicts with the preparation state.")
    layout["source_sha256"] = identities["source_sha256"]
    page_map = identities["page_map"]
    require(sha256_file(candidate_path) == layout.get("candidate_sha256"), "candidate_hash_mismatch", "Candidate bytes do not match the layout extraction hash.")
    candidate, inventory, issues = normalize_layout(layout, page_map)
    output_root = Path(args.output_dir).resolve()
    paths = paths_for_normalization_output(output_root, args.candidate_id)
    existing = [str(path) for path in paths.values() if path.exists()]
    require(not existing or args.force, "output_exists", "Refusing to overwrite existing preparation artifacts.", existing)
    for document, schema_name, label in (
        (layout, "candidate-layout-extraction.schema.json", "Candidate layout extraction"),
        (candidate, "candidate-index-v2.schema.json", "Normalized candidate"),
        (inventory, "item-inventory-v2.schema.json", "Item inventory"),
    ):
        require_schema(document, schema_name, label)
    save_json(paths["layout_extraction"], layout)
    save_json(paths["candidate_index"], candidate)
    save_json(paths["item_inventory"], inventory)
    written = list(CANONICAL_ARTIFACT_KEYS)
    if issues["issues"]:
        require_schema(issues, "candidate-normalization-issues.schema.json", "Normalization issues")
        save_json(paths["normalization_issues"], issues)
        written.append("normalization_issues")
    elif paths["normalization_issues"].exists():
        paths["normalization_issues"].unlink()
    emit({
        "command": "normalize-candidate-layout",
        "ok": True,
        "candidate_id": args.candidate_id,
        "candidate_sha256": candidate.get("candidate_sha256"),
        "canonical_state_mutated": False,
        "artifacts_written": [
            {"artifact": key, "path": str(paths[key]), "sha256": sha256_file(paths[key])}
            for key in written
        ],
        "next_actions": ["review_normalization_issues"] if issues["issues"] else ["validate-private"],
        "warnings": [],
    })


def preparation_paths(root: Path, candidate_id: str) -> dict[str, Path]:
    paths = paths_for_normalization_output(root, candidate_id)
    return {
        key: path for key, path in paths.items()
        if key in CANONICAL_ARTIFACT_KEYS or path.is_file()
    }


def _duplicate_values(values: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    duplicates: list[Any] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _walk_object(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            yield child, item
            yield from _walk_object(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_object(item, f"{path}[{index}]")


def _check_prejudgment_separation(artifacts: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for label, document in artifacts.items():
        for path, _ in _walk_object(document):
            key = path.rsplit(".", 1)[-1].casefold().replace("-", "_")
            if key in FORBIDDEN_PREJUDGMENT_KEYS:
                errors.append(f"{label}:{path} contains a prohibited candidate-judgment field")
        encoded = json.dumps(document, ensure_ascii=False).casefold()
        if '"benchmark_content"' in encoded or '"benchmark_subjects"' in encoded:
            errors.append(f"{label} contains benchmark content rather than a pending identity")
    return errors


def validate_private_preparation(
    root: Path,
    candidate_id: str,
    candidate_file: Path | None,
    state_path: Path,
    page_map_path: Path,
    chunk_manifest_path: Path,
    policy_path: Path,
    source_edition: str | None = None,
    identity_documents: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    identities = load_source_identities(state_path, page_map_path, chunk_manifest_path, policy_path, source_edition, identity_documents)
    paths = preparation_paths(root.resolve(), candidate_id)
    documents = {key: load_json(path, key.replace("_", " ").title()) for key, path in paths.items()}
    layout = documents["layout_extraction"]
    candidate = documents["candidate_index"]
    inventory = documents["item_inventory"]
    issues = documents.get("normalization_issues")
    errors: list[str] = []

    schemas = {
        "layout_extraction": "candidate-layout-extraction.schema.json",
        "candidate_index": "candidate-index-v2.schema.json",
        "item_inventory": "item-inventory-v2.schema.json",
        **({"normalization_issues": "candidate-normalization-issues.schema.json"} if issues is not None else {}),
    }
    for key, schema_name in schemas.items():
        errors.extend(f"{key}: {error}" for error in schema_errors(documents[key], schema_name))
    require(not errors, "schema_validation_failed", "Candidate preparation artifacts are structurally invalid.", errors)
    normalized_id = normalize_candidate_id(candidate_id)
    for key, document in documents.items():
        if document.get("candidate_id") not in {None, candidate_id, normalized_id}:
            errors.append(f"{key}.candidate_id differs from the selected candidate")

    candidate_sha = require_sha256(layout.get("candidate_sha256"), "layout_extraction.candidate_sha256")
    actual_candidate_sha = sha256_file(candidate_file.resolve()) if candidate_file is not None else candidate_sha
    if candidate_file is not None and actual_candidate_sha != candidate_sha:
        errors.append("Candidate bytes do not match the layout extraction")
    for key in ("layout_extraction", "candidate_index", "item_inventory"):
        if documents[key].get("candidate_sha256") != candidate_sha:
            errors.append(f"{key}.candidate_sha256 differs from the verified candidate bytes")
    if layout.get("source_sha256") != identities["source_sha256"]:
        errors.append("Layout extraction source identity differs from the frozen state")

    if candidate.get("page_map_sha256") != identities["page_map_sha256"]:
        errors.append("Normalized candidate does not identify the frozen page map")
    regenerated_candidate, regenerated_inventory, regenerated_issues = normalize_layout(
        layout, identities["page_map"]
    )
    if candidate != regenerated_candidate:
        errors.append("Normalized candidate is not the exact deterministic projection of the delivered layout and frozen page map")
    expected_issue_items = regenerated_issues["issues"]
    if bool(expected_issue_items) != (issues is not None):
        errors.append("A non-empty normalization issues report must exist if and only if normalization found issues")
    if issues is not None:
        actual_issue_items = issues.get("issues", [])
        projected = [{key: value for key, value in item.items() if key not in {"status", "disposition"}} for item in actual_issue_items]
        expected_projected = [{key: value for key, value in item.items() if key not in {"status", "disposition"}} for item in expected_issue_items]
        if projected != expected_projected:
            errors.append("Normalization issues are not the exact deterministic projection of the delivered layout and frozen page map")
        if any(item.get("status") == "needs_review" for item in actual_issue_items):
            errors.append("Every normalization issue requires an explicit disposition before registration")
        if any(item.get("status") != "needs_review" and not item.get("disposition") for item in actual_issue_items):
            errors.append("Every reviewed normalization issue requires a disposition rationale")
    try:
        candidate_inventory = build_inventory(candidate)
    except SystemExit:
        candidate_inventory = None
        errors.append("Normalized candidate cannot regenerate a valid deterministic item inventory")
    if candidate_inventory is not None and candidate_inventory != inventory:
        errors.append("Item inventory is not the exact deterministic projection of the normalized candidate")
    if inventory != regenerated_inventory:
        errors.append("Item inventory is not the exact deterministic projection of the delivered layout and frozen page map")

    id_groups = {
        "record_id": [record.get("record_id") for record in candidate.get("records", [])],
        "path_id": [record.get("path_id") for record in candidate.get("records", [])],
        "display_id": [display.get("display_id") for record in candidate.get("records", []) for display in record.get("locator_displays", [])],
        "locator_id": [locator.get("locator_id") for record in candidate.get("records", []) for locator in record.get("locator_assignments", [])],
        "reference_id": [reference.get("reference_id") for record in candidate.get("records", []) for reference in record.get("cross_references", [])],
        "exception_id": [item.get("exception_id") for item in (issues or {}).get("issues", [])],
    }
    for label, values in id_groups.items():
        duplicates = _duplicate_values(values)
        if duplicates:
            errors.append(f"Duplicate {label} values: {duplicates}")

    records = candidate.get("records", [])
    recomputed_counts = {
        "record_count": len(records),
        "main_heading_count": sum(len(item.get("heading_path", [])) == 1 for item in records),
        "subheading_count": sum(len(item.get("heading_path", [])) > 1 for item in records),
        "complete_heading_path_count": len(records),
        "displayed_locator_count": sum(len(item.get("locator_displays", [])) for item in records),
        "expanded_locator_assignment_count": sum(len(item.get("locator_assignments", [])) for item in records),
        "cross_reference_count": sum(len(item.get("cross_references", [])) for item in records),
        "unresolved_locator_count": sum(
            assignment.get("mapping_status") != "resolved"
            for item in records
            for assignment in item.get("locator_assignments", [])
        ),
        "editorial_corrections_applied": False,
        "benchmark_content_used": False,
    }
    if candidate.get("normalization") != {"engine": "candidate-preparation-cli", "engine_version": "1.0.0", **recomputed_counts}:
        errors.append("Normalized candidate aggregate counts or preparation attestations do not recompute exactly")
    issue_items = (issues or {}).get("issues", [])
    if issues is not None:
        recomputed_issue_counts = {
            "total": len(issue_items),
            "by_type": {
                key: sum(item.get("type") == key for item in issue_items)
                for key in sorted({item.get("type") for item in issue_items})
            },
        }
        if issues.get("counts") != recomputed_issue_counts:
            errors.append("Normalization issue counts do not recompute exactly")

    lookup, index_by_document_page, mapped_pages = page_map_lookup(identities["page_map"])
    exception_related = {
        related
        for item in issue_items
        for related in item.get("related_ids", []) + item.get("line_ids", [])
        if isinstance(related, str)
    }
    for record in candidate.get("records", []):
        displays = {item.get("display_id"): item for item in record.get("locator_displays", [])}
        assignments_by_display: dict[str, list[dict[str, Any]]] = {}
        for assignment in record.get("locator_assignments", []):
            assignments_by_display.setdefault(assignment.get("display_id"), []).append(assignment)
            if assignment.get("mapping_status") == "resolved":
                mapped = next((page for page in mapped_pages if page.get("document_page") == assignment.get("document_page")), None)
                if not mapped or not mapped.get("accepts_index_locators"):
                    errors.append(f"Resolved locator {assignment.get('locator_id')} is outside the indexable page map")
                elif assignment.get("source_page_label") != mapped.get("source_page_label") or assignment.get("normalized_locator_key") != mapped.get("normalized_locator_key"):
                    errors.append(f"Resolved locator {assignment.get('locator_id')} does not reproduce its page-map record")
            elif assignment.get("locator_id") not in exception_related:
                errors.append(f"Unresolved locator {assignment.get('locator_id')} has no normalization issue")
        for display_id, display in displays.items():
            regenerated_assignments, regenerated_display, _ = locator_assignments_for_display(
                str(display.get("displayed_locator", "")), str(display_id), str(candidate_sha), lookup, index_by_document_page, mapped_pages
            )
            if display != regenerated_display or assignments_by_display.get(display_id, []) != regenerated_assignments:
                errors.append(f"Displayed locator {display_id} does not reproduce the frozen page-map expansion")

    errors.extend(layout_accounting_errors(layout, candidate, regenerated_issues))
    if candidate.get("normalization", {}).get("editorial_corrections_applied") is not False or candidate.get("normalization", {}).get("benchmark_content_used") is not False:
        errors.append("Normalization must preserve delivered content and remain benchmark-content blind")
    errors.extend(_check_prejudgment_separation(documents))
    require(not errors, "private_preparation_invalid", "Candidate preparation failed the private full-QA gate.", errors)
    return {
        "identities": identities,
        "paths": paths,
        "documents": documents,
        "hashes": {key: sha256_file(path) for key, path in paths.items()},
        "candidate_sha256": actual_candidate_sha,
        "counts": candidate.get("normalization", {}),
    }


def command_validate_private(args: argparse.Namespace) -> None:
    result = validate_private_preparation(
        Path(args.preparation_dir), args.candidate_id, Path(args.candidate_file), Path(args.state),
        Path(args.page_map), Path(args.chunk_manifest), Path(args.policy),
        args.source_edition,
    )
    emit({
        "command": "validate-private-preparation",
        "ok": True,
        "candidate_id": args.candidate_id,
        "candidate_sha256": result["candidate_sha256"],
        "artifact_hashes": result["hashes"],
        "qa_gate": "complete_exact_set",
        "candidate_quality_judgments_performed": False,
        "warnings": [],
    })


def command_register(args: argparse.Namespace) -> None:
    """Register a validated local preparation directly; no PR or evidence ceremony."""
    state_path = Path(args.state).resolve()
    result = validate_private_preparation(
        Path(args.preparation_dir), args.candidate_id, Path(args.candidate_file), state_path,
        Path(args.page_map), Path(args.chunk_manifest), Path(args.policy),
        args.source_edition,
    )
    benchmark_path = Path(args.benchmark).resolve()
    benchmark = load_json(benchmark_path, "Final benchmark")
    errors = final_benchmark_structure_errors(benchmark)
    require(not errors, "benchmark_invalid", "Final benchmark is invalid.", errors)
    with evaluation_mutation_lock(state_path):
        state = load_json(state_path, "Canonical evaluation state")
        errors, _ = validate_state(state, state_path=state_path)
        require(not errors, "canonical_state_invalid", "Canonical evaluation state failed validation.", errors)
        require(state.get("stages", {}).get("benchmark_freeze", {}).get("status") == "completed", "benchmark_stage_incomplete", "Freeze the benchmark before registering a candidate.")
        require(benchmark.get("evaluation_id") == state.get("evaluation_id"), "benchmark_identity_mismatch", "Benchmark and evaluation IDs differ.")
        require(benchmark.get("source_sha256") == state.get("source", {}).get("sha256"), "benchmark_identity_mismatch", "Benchmark and source identities differ.")
        require(benchmark.get("candidate_blindness") == "preserved", "candidate_blindness", "The benchmark must remain candidate-blind.")
        root = state_path.parent
        artifact_types = {
            "layout_extraction": "candidate_layout_extraction",
            "candidate_index": "candidate_index",
            "item_inventory": "item_inventory",
            "normalization_issues": "candidate_normalization_issues",
        }
        stamp = now()
        new_records = []
        for name, path in result["paths"].items():
            relative = portable_relative_path(path, root)
            digest = sha256_file(path)
            document = result["documents"].get(name, {})
            record = {
                "artifact_id": state_artifact_id(relative, digest),
                "stage": "candidate_normalization",
                "artifact_type": artifact_types[name],
                "path": relative,
                "sha256": digest,
                "media_type": "application/json",
                "visibility": "private",
                "retention": "required",
                "frozen": True,
                "recorded_at": stamp,
                **({"schema_version": document["schema_version"]} if isinstance(document, dict) and isinstance(document.get("schema_version"), str) else {}),
            }
            new_records.append(record)
        state["artifacts"] = [record for record in state.get("artifacts", []) if record.get("stage") != "candidate_normalization"]
        state["artifacts"].extend(new_records)
        state["artifacts"].sort(key=lambda record: record["path"])
        registered_candidate_id = result["documents"]["candidate_index"]["candidate_id"]
        normalized_record = next(record for record in new_records if record["artifact_type"] == "candidate_index")
        state["candidate"] = {
            "candidate_id": registered_candidate_id,
            "candidate_sha256": result["candidate_sha256"],
            "schema_version": "candidate-index-v2",
            "normalized_path": normalized_record["path"],
            "normalized_sha256": normalized_record["sha256"],
            "item_inventory_path": next(record["path"] for record in new_records if record["artifact_type"] == "item_inventory"),
            "benchmark_path": portable_relative_path(benchmark_path, root),
            "benchmark_sha256": benchmark.get("benchmark_sha256"),
        }
        state["stages"]["candidate_normalization"] = {"status": "completed", "updated_at": stamp, "notes": ["Validated and registered directly from local preparation outputs."]}
        state["updated_at"] = stamp
        validation_errors, warnings = validate_state(state, state_path=state_path)
        require(not validation_errors, "canonical_state_invalid", "Candidate registration would leave invalid state.", validation_errors)
        save_state(state_path, state)
    action = next_stage(state)
    emit({
        "command": "register-candidate-preparation", "ok": True,
        "evaluation_id": state["evaluation_id"], "candidate_id": registered_candidate_id,
        "artifacts_written": [record["path"] for record in new_records],
        "next_actions": [] if action is None else [action], "warnings": warnings,
    })


def _add_frozen_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", required=True)
    parser.add_argument("--page-map", required=True)
    parser.add_argument("--chunk-manifest", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--source-edition")


def _add_private_inputs(parser: argparse.ArgumentParser, include_candidate_file: bool = True) -> None:
    parser.add_argument("--candidate-id", required=True)
    if include_candidate_file:
        parser.add_argument("--candidate-file", required=True)
    parser.add_argument("--preparation-dir", required=True)
    _add_frozen_inputs(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser("normalize", help="Normalize a contract-valid layout into current candidate v2 artifacts")
    normalize.add_argument("--candidate-id", required=True)
    normalize.add_argument("--candidate-file", required=True)
    _add_frozen_inputs(normalize)
    normalize.add_argument("--layout", required=True)
    normalize.add_argument("--output-dir", required=True)
    normalize.add_argument("--force", action="store_true")
    normalize.set_defaults(func=command_normalize)

    validate_private = subparsers.add_parser("validate-private", help="Enforce full exact-set normalization QA")
    _add_private_inputs(validate_private)
    validate_private.set_defaults(func=command_validate_private)

    register = subparsers.add_parser("register", help="Register validated local preparation outputs in canonical state")
    _add_private_inputs(register)
    register.add_argument("--benchmark", required=True)
    register.set_defaults(func=command_register)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except PreparationError as exc:
        payload: dict[str, Any] = {"ok": False, "error": {"code": exc.code, "message": exc.message}}
        if exc.details is not None:
            payload["error"]["details"] = exc.details
        emit(payload, 1)
    except (OSError, ValueError) as exc:
        emit({"ok": False, "error": {"code": "candidate_preparation_failure", "message": str(exc)}}, 1)


if __name__ == "__main__":
    main()
