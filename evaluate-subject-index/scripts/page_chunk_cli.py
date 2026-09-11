#!/usr/bin/env python3
"""Expand page-label maps, validate chunks, split PDFs, and route candidate locators."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from benchmark_review_cli import final_benchmark_structure_errors
from candidate_preparation_cli import (
    PreparationError,
    path_is_within,
    replace_bytes_atomic,
    require,
    require_safe_output_path,
)
from state_cli import (
    STAGES,
    artifact_id,
    evaluation_mutation_lock,
    next_stage,
    resolve_artifact_path,
    save_state,
    validate_state,
)
from schema_validation import schema_errors


def emit(payload: dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    raise SystemExit(exit_code)


def fail(code: str, message: str, details: Any = None) -> None:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    emit({"ok": False, "error": error}, 1)


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


def require_schema(value: Any, schema_name: str, label: str) -> None:
    errors = schema_errors(value, schema_name)
    if errors:
        fail("schema_validation_failed", f"{label} is structurally invalid.", errors)


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonical_hash(value: dict[str, Any], hash_field: str) -> str:
    copy = dict(value)
    copy.pop(hash_field, None)
    encoded = json.dumps(copy, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_label(label: str | None, style: str | None = None) -> str | None:
    if label is None:
        return None
    normalized = unicodedata.normalize("NFKC", label).strip()
    normalized = re.sub(r"[‐‑‒–—−]", "-", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    if style == "arabic" and re.fullmatch(r"[0-9]+", normalized):
        return str(int(normalized))
    return normalized.casefold()


def roman_to_int(value: str) -> int:
    symbols = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    text = value.upper()
    if not text or any(char not in symbols for char in text):
        raise ValueError(f"Invalid Roman numeral: {value}")
    total = 0
    previous = 0
    for char in reversed(text):
        current = symbols[char]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    if int_to_roman(total) != text:
        raise ValueError(f"Noncanonical Roman numeral: {value}")
    return total


def int_to_roman(value: int) -> str:
    if value < 1 or value > 3999:
        raise ValueError("Roman numeral sequence supports values 1 through 3999")
    pairs = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    result = []
    remaining = value
    for number, symbol in pairs:
        while remaining >= number:
            result.append(symbol)
            remaining -= number
    return "".join(result)


def alpha_to_int(value: str) -> int:
    if not re.fullmatch(r"[A-Za-z]+", value):
        raise ValueError(f"Invalid alphabetic label: {value}")
    total = 0
    for char in value.upper():
        total = total * 26 + ord(char) - ord("A") + 1
    return total


def int_to_alpha(value: int) -> str:
    if value < 1:
        raise ValueError("Alphabetic sequence starts at 1")
    result = []
    remaining = value
    while remaining:
        remaining, remainder = divmod(remaining - 1, 26)
        result.append(chr(ord("A") + remainder))
    return "".join(reversed(result))


def sequence_value(style: str, start: str, offset: int) -> str:
    if style == "arabic":
        if not re.fullmatch(r"[0-9]+", start):
            raise ValueError(f"Invalid Arabic label_start: {start}")
        return str(int(start) + offset)
    if style in {"roman_lower", "roman_upper"}:
        value = int_to_roman(roman_to_int(start) + offset)
        return value.lower() if style == "roman_lower" else value
    if style in {"alpha_lower", "alpha_upper"}:
        value = int_to_alpha(alpha_to_int(start) + offset)
        return value.lower() if style == "alpha_lower" else value
    raise ValueError(f"Unsupported sequence label_style: {style}")


def parse_range(value: Any, field: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(item, int) for item in value):
        raise ValueError(f"{field} must be [start, end] integers")
    start, end = value
    if start < 1 or end < start:
        raise ValueError(f"{field} must be one-based and ascending")
    return start, end


def expand_ranges(ranges: Any, field: str) -> list[int]:
    if not isinstance(ranges, list):
        raise ValueError(f"{field} must be an array of ranges")
    pages: list[int] = []
    for index, item in enumerate(ranges):
        start, end = parse_range(item, f"{field}[{index}]")
        pages.extend(range(start, end + 1))
    return pages


def command_expand_page_map(args: argparse.Namespace) -> None:
    source = load_json(Path(args.input))
    require_schema(source, "page-map-input.schema.json", "Page-map input")
    count = source["document_page_count"]
    source_sha256 = source["source_sha256"]
    segments = source["segments"]

    records: dict[int, dict[str, Any]] = {}
    errors: list[str] = []
    for segment in segments:
        mapping_id = str(segment.get("mapping_id", ""))
        mode = segment.get("mode")
        try:
            start, end = parse_range(segment.get("document_page_range"), f"{mapping_id}.document_page_range")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if end > count:
            errors.append(f"{mapping_id} ends after document_page_count")
            continue
        overlap = [page for page in range(start, end + 1) if page in records]
        if overlap:
            errors.append(f"{mapping_id} overlaps previously mapped document pages: {overlap[:10]}")
            continue
        page_total = end - start + 1
        style = segment.get("label_style", "literal" if mode == "explicit" else None)
        labels: list[str | None]
        if mode == "sequence":
            label_start = segment.get("label_start")
            prefix = str(segment.get("prefix", ""))
            suffix = str(segment.get("suffix", ""))
            try:
                labels = [prefix + sequence_value(str(style), label_start, offset) + suffix for offset in range(page_total)]
            except ValueError as exc:
                errors.append(f"{mapping_id}: {exc}")
                continue
        elif mode == "explicit":
            raw_labels = segment.get("labels")
            if len(raw_labels) != page_total:
                errors.append(f"{mapping_id}.labels must contain exactly {page_total} values")
                continue
            labels = raw_labels
        else:
            errors.append(f"{mapping_id}.mode must be sequence or explicit")
            continue

        for offset, document_page in enumerate(range(start, end + 1)):
            label = labels[offset]
            records[document_page] = {
                "document_page": document_page,
                "source_page_label": label,
                "normalized_locator_key": normalize_label(label, str(style) if style else None),
                "label_style": style or "literal",
                "mapping_id": mapping_id,
                "in_evaluation_scope": bool(segment.get("in_evaluation_scope")),
                "accepts_index_locators": bool(segment.get("accepts_index_locators")),
            }

    missing = [page for page in range(1, count + 1) if page not in records]
    if missing:
        errors.append(f"Unmapped document pages: {missing[:25]}{'...' if len(missing) > 25 else ''}")

    key_pages: dict[str, list[int]] = {}
    for record in records.values():
        key = record["normalized_locator_key"]
        if record["accepts_index_locators"] and key is not None:
            key_pages.setdefault(key, []).append(record["document_page"])
    duplicates = {key: pages for key, pages in key_pages.items() if len(pages) > 1}
    if duplicates:
        errors.append(f"Ambiguous duplicate indexable labels: {duplicates}")
    if errors:
        fail("invalid_page_map", "Page map could not be expanded.", errors)

    output: dict[str, Any] = {
        "schema_version": "page-map-v1",
        "source_sha256": source_sha256,
        "document_page_count": count,
        "document_page_basis": "one_based_inclusive",
        "pages": [records[page] for page in range(1, count + 1)],
        "validation": {
            "all_document_pages_covered": True,
            "unique_indexable_locator_keys": True,
        },
        "page_map_sha256": None,
    }
    output["page_map_sha256"] = canonical_hash(output, "page_map_sha256")
    require_schema(output, "page-map.schema.json", "Page map")
    output_path = Path(args.output)
    save_json(output_path, output)
    emit({
        "ok": True,
        "command": "expand-page-map",
        "artifact_written": str(output_path.resolve()),
        "page_map_sha256": output["page_map_sha256"],
        "document_pages": count,
        "indexable_labels": len(key_pages),
    })


def command_validate_chunks(args: argparse.Namespace) -> None:
    manifest = load_json(Path(args.input))
    page_map = load_json(Path(args.page_map))
    require_schema(manifest, "chunk-manifest-input.schema.json", "Chunk-manifest input")
    require_schema(page_map, "page-map.schema.json", "Page map")
    if manifest.get("user_approved") is not True:
        fail("approval_required", "chunk manifest must record user_approved: true")
    chunks = manifest.get("chunks")
    count = page_map.get("document_page_count")
    in_scope = {record["document_page"] for record in page_map.get("pages", []) if record.get("in_evaluation_scope")}
    owners: dict[int, str] = {}
    errors: list[str] = []
    chunk_ids: set[str] = set()
    packet_orders: set[int] = set()
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if chunk_id in chunk_ids:
            errors.append(f"Duplicate chunk_id: {chunk_id}")
        chunk_ids.add(chunk_id)
        packet_order = chunk.get("packet_order")
        if packet_order in packet_orders:
            errors.append(f"Invalid or duplicate packet_order for {chunk_id}: {packet_order}")
        else:
            packet_orders.add(packet_order)
        try:
            owned = expand_ranges(chunk.get("owned_document_page_ranges"), f"{chunk_id}.owned_document_page_ranges")
            context = expand_ranges(chunk.get("context_document_page_ranges", []), f"{chunk_id}.context_document_page_ranges")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for page in owned + context:
            if page > count:
                errors.append(f"{chunk_id} references document page {page} beyond {count}")
        for page in owned:
            if page in owners:
                errors.append(f"Document page {page} is owned by both {owners[page]} and {chunk_id}")
            else:
                owners[page] = chunk_id

    missing_scope = sorted(in_scope - set(owners))
    outside_scope = sorted(set(owners) - in_scope)
    require_full = bool(manifest.get("require_full_scope_coverage"))
    if require_full and missing_scope:
        errors.append(f"In-scope document pages without an owner: {missing_scope[:25]}{'...' if len(missing_scope) > 25 else ''}")
    if outside_scope:
        errors.append(f"Owned document pages are outside evaluation scope: {outside_scope[:25]}{'...' if len(outside_scope) > 25 else ''}")
    if errors:
        fail("invalid_chunk_manifest", "Chunk manifest failed validation.", errors)

    output = dict(manifest)
    output["document_page_basis"] = "one_based_inclusive"
    output["page_map_sha256"] = page_map.get("page_map_sha256")
    output["validation"] = {
        "owned_pages_unique": True,
        "scope_coverage_complete": not missing_scope,
        "owned_document_page_count": len(owners),
        "in_scope_document_page_count": len(in_scope),
    }
    output["chunk_manifest_sha256"] = None
    output["chunk_manifest_sha256"] = canonical_hash(output, "chunk_manifest_sha256")
    require_schema(output, "chunk-manifest.schema.json", "Chunk manifest")
    output_path = Path(args.output)
    save_json(output_path, output)
    emit({
        "ok": True,
        "command": "validate-chunks",
        "artifact_written": str(output_path.resolve()),
        "chunk_manifest_sha256": output["chunk_manifest_sha256"],
        "chunk_count": len(chunks),
        "owned_document_pages": len(owners),
    })


def command_split_pdf(args: argparse.Namespace) -> None:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        fail("missing_dependency", "pypdf is required for split-pdf")
    source_path = Path(args.source)
    if not source_path.is_file():
        fail("source_not_found", f"Source PDF does not exist: {source_path}")
    page_map = load_json(Path(args.page_map))
    manifest = load_json(Path(args.chunks))
    require_schema(page_map, "page-map.schema.json", "Page map")
    require_schema(manifest, "chunk-manifest.schema.json", "Chunk manifest")
    actual_source_hash = sha256_file(source_path)
    if page_map.get("source_sha256") != actual_source_hash:
        fail("source_hash_mismatch", "Source PDF does not match the source_sha256 frozen in the page map")
    reader = PdfReader(str(source_path))
    expected = page_map.get("document_page_count")
    if len(reader.pages) != expected:
        fail("page_count_mismatch", f"PDF has {len(reader.pages)} pages; page map declares {expected}")
    page_records = {record["document_page"]: record for record in page_map.get("pages", [])}
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_files: list[dict[str, Any]] = []
    for chunk in sorted(manifest.get("chunks", []), key=lambda item: item["packet_order"]):
        owned = set(expand_ranges(chunk["owned_document_page_ranges"], "owned_document_page_ranges"))
        context = set(expand_ranges(chunk.get("context_document_page_ranges", []), "context_document_page_ranges"))
        selected = sorted(owned | context)
        writer = PdfWriter()
        sidecar_pages: list[dict[str, Any]] = []
        for chunk_page, document_page in enumerate(selected, start=1):
            writer.add_page(reader.pages[document_page - 1])
            mapping = page_records[document_page]
            sidecar_pages.append({
                "chunk_pdf_page": chunk_page,
                "document_page": document_page,
                "source_page_label": mapping.get("source_page_label"),
                "ownership": "owned" if document_page in owned else "context",
            })
        pdf_path = output_dir / f"{chunk['chunk_id']}.pdf"
        with pdf_path.open("wb") as handle:
            writer.write(handle)
        sidecar = {
            "schema_version": "source-chunk-sidecar-v1",
            "chunk_id": chunk["chunk_id"],
            "source_filename": source_path.name,
            "page_map_sha256": page_map.get("page_map_sha256"),
            "chunk_manifest_sha256": manifest.get("chunk_manifest_sha256"),
            "pages": sidecar_pages,
        }
        sidecar_path = output_dir / f"{chunk['chunk_id']}.pages.json"
        save_json(sidecar_path, sidecar)
        chunk_files.append({
            "chunk_id": chunk["chunk_id"],
            "pdf": str(pdf_path.resolve()),
            "sidecar": str(sidecar_path.resolve()),
            "page_count": len(selected),
            "owned_page_count": len(owned),
            "context_page_count": len(context - owned),
        })
    emit({
        "ok": True,
        "command": "split-pdf",
        "artifacts_written": [
            path
            for chunk in chunk_files
            for path in (chunk["pdf"], chunk["sidecar"])
        ],
        "chunk_count": len(chunk_files),
        "chunks": chunk_files,
    })


def require_current_schema(value: dict[str, Any], schema_name: str, label: str) -> None:
    errors = schema_errors(value, schema_name)
    require(not errors, "schema_validation_failed", f"{label} is structurally invalid.", errors)


def require_registered_artifact(
    state: dict[str, Any], state_path: Path, path: Path, *, stage: str, schema_version: str,
) -> dict[str, Any]:
    root = state_path.parent
    require(path_is_within(path, root), "artifact_outside_evaluation_directory", f"Artifact is outside the canonical evaluation directory: {path}")
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    matches = [item for item in state.get("artifacts", []) if item.get("path") == relative]
    require(len(matches) == 1, "artifact_not_registered", f"Expected one current registered artifact for {relative}.")
    record = matches[0]
    require(record.get("stage") == stage, "artifact_stage_mismatch", f"Registered artifact {relative} belongs to a different stage.")
    require(record.get("schema_version") == schema_version, "artifact_schema_mismatch", f"Registered artifact {relative} is not {schema_version}.")
    require(path.is_file(), "file_not_found", f"Registered artifact is not accessible: {path}")
    require(record.get("sha256") == sha256_file(path), "registered_artifact_hash_mismatch", f"Registered artifact bytes changed: {relative}")
    return record


def validated_chunk_owners(manifest: dict[str, Any], page_map: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[int, str]]:
    page_records = page_map["pages"]
    page_numbers = [record["document_page"] for record in page_records]
    page_number_set = set(page_numbers)
    require(len(page_numbers) == len(page_number_set), "duplicate_page_map_identity", "Page map repeats a document-page identity.")
    require(page_number_set == set(range(1, page_map["document_page_count"] + 1)), "page_map_coverage_mismatch", "Page map does not cover its declared document-page span exactly.")
    in_scope = {record["document_page"] for record in page_records if record["in_evaluation_scope"]}
    chunks: dict[str, dict[str, Any]] = {}
    packet_orders: set[int] = set()
    owners: dict[int, str] = {}
    for chunk in manifest["chunks"]:
        chunk_id = chunk["chunk_id"]
        require(chunk_id not in chunks, "duplicate_chunk_identity", f"Chunk manifest repeats {chunk_id}.")
        require(chunk["packet_order"] not in packet_orders, "duplicate_packet_order", f"Chunk manifest repeats packet order {chunk['packet_order']}.")
        chunks[chunk_id] = chunk
        packet_orders.add(chunk["packet_order"])
        try:
            owned_pages = expand_ranges(chunk["owned_document_page_ranges"], f"{chunk_id}.owned_document_page_ranges")
            context_pages = expand_ranges(chunk.get("context_document_page_ranges", []), f"{chunk_id}.context_document_page_ranges")
        except ValueError as exc:
            raise PreparationError("invalid_chunk_ranges", str(exc)) from exc
        for page in owned_pages + context_pages:
            require(page in page_number_set, "chunk_page_out_of_range", f"Chunk {chunk_id} references absent document page {page}.")
        for page in owned_pages:
            require(page not in owners, "overlapping_chunk_ownership", f"Document page {page} is owned by both {owners.get(page)} and {chunk_id}.")
            owners[page] = chunk_id
    owned_pages = set(owners)
    require(not (owned_pages - in_scope), "chunk_owns_out_of_scope_page", "Chunk manifest owns pages outside evaluation scope.", sorted(owned_pages - in_scope))
    scope_complete = owned_pages == in_scope
    require(manifest["validation"].get("owned_pages_unique") is True, "invalid_chunk_manifest", "Chunk manifest does not attest unique ownership.")
    require(manifest["validation"].get("scope_coverage_complete") is scope_complete, "chunk_scope_validation_mismatch", "Chunk manifest scope-coverage result does not recompute.")
    if manifest.get("require_full_scope_coverage"):
        require(scope_complete, "chunk_scope_incomplete", "Frozen chunk ownership does not cover every in-scope document page.", sorted(in_scope - owned_pages))
    return chunks, owners


def prepare_locator_documents(
    candidate: dict[str, Any], page_map: dict[str, Any], manifest: dict[str, Any], benchmark: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chunks, owners = validated_chunk_owners(manifest, page_map)
    page_records = {record["document_page"]: record for record in page_map["pages"]}
    routed: dict[str, list[dict[str, Any]]] = {chunk_id: [] for chunk_id in chunks}
    exceptions: list[dict[str, Any]] = []
    record_ids: set[str] = set()
    path_ids: set[str] = set()
    locator_ids: set[str] = set()
    expected_routed: set[str] = set()

    for record in candidate["records"]:
        record_id = record["record_id"]
        path_id = record["path_id"]
        require(record_id not in record_ids, "duplicate_candidate_record", f"Normalized candidate repeats {record_id}.")
        require(path_id not in path_ids, "duplicate_candidate_path", f"Normalized candidate repeats {path_id}.")
        record_ids.add(record_id)
        path_ids.add(path_id)
        by_chunk: dict[str, list[dict[str, Any]]] = {}
        for assignment in record["locator_assignments"]:
            locator_id = assignment["locator_id"]
            require(locator_id not in locator_ids, "duplicate_locator_assignment", f"Normalized candidate repeats {locator_id}.")
            locator_ids.add(locator_id)
            page = assignment.get("document_page")
            if assignment.get("mapping_status") != "resolved" or not isinstance(page, int):
                exceptions.append({
                    "record_id": record_id, "path_id": path_id, "heading_path": record["heading_path"],
                    "locator_assignment": assignment, "reason": "locator_not_resolved_to_one_document_page",
                })
                continue
            mapped = page_records.get(page)
            require(mapped is not None, "locator_page_map_mismatch", f"Resolved locator {locator_id} references absent document page {page}.")
            require(
                assignment.get("source_page_label") == mapped.get("source_page_label")
                and assignment.get("normalized_locator_key") == mapped.get("normalized_locator_key"),
                "locator_page_map_mismatch", f"Resolved locator {locator_id} differs from its frozen page-map record.",
            )
            chunk_id = owners.get(page)
            if chunk_id is None:
                exceptions.append({
                    "record_id": record_id, "path_id": path_id, "heading_path": record["heading_path"],
                    "locator_assignment": assignment, "reason": "mapped_document_page_has_no_chunk_owner",
                })
                continue
            expected_routed.add(locator_id)
            by_chunk.setdefault(chunk_id, []).append(assignment)
        routed_total = sum(len(assignments) for assignments in by_chunk.values())
        for chunk_id, assignments in by_chunk.items():
            routed[chunk_id].append({
                "record_id": record_id,
                "path_id": path_id,
                "heading_path": record["heading_path"],
                "locator_assignments": assignments,
                "other_locator_assignment_count": routed_total - len(assignments),
            })

    packets: list[dict[str, Any]] = []
    actual_routed: list[str] = []
    for chunk in sorted(chunks.values(), key=lambda item: item["packet_order"]):
        chunk_id = chunk["chunk_id"]
        paths = routed[chunk_id]
        for path in paths:
            actual_routed.extend(item["locator_id"] for item in path["locator_assignments"])
        packet = {
            "schema_version": "candidate-locator-chunk-v1",
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": candidate["candidate_sha256"],
            "page_map_sha256": page_map["page_map_sha256"],
            "chunk_manifest_sha256": manifest["chunk_manifest_sha256"],
            "chunk_id": chunk_id,
            "owned_document_pages": sorted(expand_ranges(chunk["owned_document_page_ranges"], f"{chunk_id}.owned_document_page_ranges")),
            "paths": paths,
            "summary": {
                "path_count": len(paths),
                "locator_assignment_count": sum(len(path["locator_assignments"]) for path in paths),
            },
        }
        require_current_schema(packet, "candidate-locator-chunk.schema.json", f"Locator packet {chunk_id}")
        packets.append(packet)
    require(len(actual_routed) == len(set(actual_routed)), "duplicate_routed_assignment", "A locator assignment was routed more than once.")
    require(set(actual_routed) == expected_routed, "incomplete_locator_routing", "Resolved owned locator assignments were not routed exactly once.")
    ledger = {
        "schema_version": "candidate-locator-routing-exceptions-v1",
        "candidate_id": candidate["candidate_id"],
        "candidate_sha256": candidate["candidate_sha256"],
        "benchmark_sha256": benchmark["benchmark_sha256"],
        "page_map_sha256": page_map["page_map_sha256"],
        "chunk_manifest_sha256": manifest["chunk_manifest_sha256"],
        "exceptions": exceptions,
        "exception_count": len(exceptions),
    }
    require_current_schema(ledger, "candidate-locator-routing-exceptions.schema.json", "Locator routing failure diagnostic")
    return packets, ledger


def locator_artifact_record(path: Path, root: Path, artifact_type: str, schema_version: str, stamp: str) -> dict[str, Any]:
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    digest = sha256_file(path)
    return {
        "artifact_id": artifact_id(relative, digest),
        "stage": "locator_chunk_preparation",
        "artifact_type": artifact_type,
        "path": relative,
        "sha256": digest,
        "media_type": "application/json",
        "schema_version": schema_version,
        "visibility": "private",
        "retention": "required",
        "frozen": True,
        "recorded_at": stamp,
    }


def command_prepare_locator_chunks(args: argparse.Namespace) -> None:
    state_path = Path(args.state).resolve()
    with evaluation_mutation_lock(state_path):
        state = load_json(state_path)
        errors, warnings = validate_state(state, state_path=state_path, check_files=True)
        require(not errors, "canonical_state_invalid", "Canonical evaluation state failed validation.", errors)
        stages = state["stages"]
        stage_index = STAGES.index("locator_chunk_preparation")
        unmet = [name for name in STAGES[:stage_index] if stages[name]["status"] != "completed"]
        require(not unmet, "stage_dependencies_incomplete", "Complete every prior stage before locator-packet preparation.", unmet)
        require(stages["benchmark_freeze"]["status"] == "completed", "benchmark_freeze_incomplete", "Benchmark freeze must be complete.")
        require(stages["candidate_normalization"]["status"] == "completed", "candidate_normalization_incomplete", "Candidate normalization must be complete.")
        require(stages["locator_chunk_preparation"]["status"] in {"not_started", "in_progress"}, "locator_preparation_already_completed", "Locator-packet preparation is already complete.")
        later_started = [name for name in STAGES[stage_index + 1:] if stages[name]["status"] != "not_started"]
        require(not later_started, "stage_boundary_crossed", "Later candidate-evaluation stages have already begun.", later_started)

        candidate_path = Path(args.normalized_candidate).resolve()
        page_map_path = Path(args.page_map).resolve()
        manifest_path = Path(args.chunk_manifest).resolve()
        benchmark_path = Path(args.benchmark).resolve()
        candidate = load_json(candidate_path)
        page_map = load_json(page_map_path)
        manifest = load_json(manifest_path)
        benchmark = load_json(benchmark_path)
        require_current_schema(candidate, "candidate-index-v2.schema.json", "Normalized candidate")
        require_current_schema(page_map, "page-map.schema.json", "Page map")
        require_current_schema(manifest, "chunk-manifest.schema.json", "Chunk manifest")
        benchmark_errors = final_benchmark_structure_errors(benchmark)
        require(not benchmark_errors, "benchmark_invalid", "Frozen benchmark is invalid.", benchmark_errors)
        require(page_map["page_map_sha256"] == canonical_hash(page_map, "page_map_sha256"), "page_map_hash_mismatch", "Page-map canonical identity does not recompute.")
        require(manifest["chunk_manifest_sha256"] == canonical_hash(manifest, "chunk_manifest_sha256"), "chunk_manifest_hash_mismatch", "Chunk-manifest canonical identity does not recompute.")
        require(benchmark["benchmark_sha256"] == canonical_hash(benchmark, "benchmark_sha256"), "benchmark_hash_mismatch", "Benchmark canonical identity does not recompute.")

        candidate_state = state.get("candidate")
        require(isinstance(candidate_state, dict), "candidate_not_registered", "Canonical state has no registered candidate.")
        require(candidate_state.get("candidate_id") == candidate["candidate_id"], "candidate_identity_mismatch", "Selected candidate ID differs from state.candidate.")
        require(candidate_state.get("candidate_sha256") == candidate["candidate_sha256"], "candidate_identity_mismatch", "Selected candidate SHA-256 differs from state.candidate.")
        require(candidate_state.get("schema_version") == candidate["schema_version"], "candidate_identity_mismatch", "Selected candidate schema differs from state.candidate.")
        require(resolve_artifact_path(state_path, candidate_state["normalized_path"]).resolve() == candidate_path, "candidate_path_mismatch", "Selected candidate is not the registered current normalized artifact.")
        require(candidate_state.get("normalized_sha256") == sha256_file(candidate_path), "candidate_identity_mismatch", "Selected normalized candidate hash differs from state.candidate.")
        require(resolve_artifact_path(state_path, candidate_state["benchmark_path"]).resolve() == benchmark_path, "benchmark_path_mismatch", "Selected benchmark is not the candidate's registered frozen benchmark.")
        require(candidate_state.get("benchmark_sha256") == benchmark["benchmark_sha256"], "benchmark_identity_mismatch", "Candidate benchmark identity differs from the selected frozen benchmark.")

        require_registered_artifact(state, state_path, candidate_path, stage="candidate_normalization", schema_version="candidate-index-v2")
        require_registered_artifact(state, state_path, page_map_path, stage="page_mapping", schema_version="page-map-v1")
        require_registered_artifact(state, state_path, manifest_path, stage="chunk_definition", schema_version="chunk-manifest-v1")
        require_registered_artifact(state, state_path, benchmark_path, stage="benchmark_freeze", schema_version="source-subject-benchmark-v2")
        source_sha = state["source"]["sha256"]
        require(page_map["source_sha256"] == source_sha, "page_map_identity_mismatch", "Page map source identity differs from canonical state.")
        require(candidate["page_map_sha256"] == page_map["page_map_sha256"], "candidate_page_map_mismatch", "Candidate references a different page map.")
        require(manifest["page_map_sha256"] == page_map["page_map_sha256"], "chunk_manifest_identity_mismatch", "Chunk manifest references a different page map.")
        for field, expected in (
            ("evaluation_id", state["evaluation_id"]),
            ("source_sha256", source_sha),
            ("page_map_sha256", page_map["page_map_sha256"]),
            ("chunk_manifest_sha256", manifest["chunk_manifest_sha256"]),
        ):
            require(benchmark.get(field) == expected, "benchmark_identity_mismatch", f"Benchmark {field} differs from canonical state and registered inputs.")
        require(benchmark.get("candidate_blindness") == "preserved", "benchmark_blindness", "Frozen benchmark must preserve candidate blindness.")

        packets, ledger = prepare_locator_documents(candidate, page_map, manifest, benchmark)
        output_dir = Path(args.output_dir).resolve() if args.output_dir else candidate_path.parent / "locator-packets"
        root = state_path.parent
        packet_outputs: list[tuple[dict[str, Any], Path, bytes]] = []
        for packet in packets:
            path = output_dir / f"candidate-locator-{packet['chunk_id']}.json"
            require_safe_output_path(path, root, "Candidate locator packet")
            packet_outputs.append((packet, path, json_bytes(packet)))
        artifact_details = [
            {"chunk_id": packet["chunk_id"], "path": path.resolve().relative_to(root.resolve()).as_posix(), "sha256": hashlib.sha256(payload).hexdigest(), **packet["summary"]}
            for packet, path, payload in packet_outputs
        ]
        if ledger["exceptions"]:
            diagnostic_path = output_dir / "candidate-locator-routing-exceptions.json"
            require_safe_output_path(diagnostic_path, root, "Locator routing diagnostic")
            diagnostic_relative = diagnostic_path.resolve().relative_to(root.resolve()).as_posix()
            collision = next((item["path"] for item in state["artifacts"] if item.get("path") == diagnostic_relative), None)
            require(collision is None, "registered_output_collision", "Locator routing diagnostic would overwrite a registered artifact.", [collision] if collision else [])
            diagnostic_bytes = json_bytes(ledger)
            replace_bytes_atomic(diagnostic_path, diagnostic_bytes)
            diagnostic = {
                "path": diagnostic_relative,
                "sha256": hashlib.sha256(diagnostic_bytes).hexdigest(),
                "exception_count": ledger["exception_count"],
            }
            emit({
                "command": "prepare-locator-chunks", "ok": False,
                "error": {
                    "code": "locator_routing_exceptions",
                    "message": "Resolve every routing exception before preparing locator packets.",
                },
                "evaluation_id": state["evaluation_id"], "candidate_id": candidate["candidate_id"],
                "artifacts_written": [diagnostic["path"]],
                "routing_diagnostic": diagnostic,
                "counts": {"frozen_chunks": len(packets), "packets": 0, "routed_assignments": sum(item["locator_assignment_count"] for item in artifact_details), "routing_exceptions": ledger["exception_count"]},
                "stage_status": stages["locator_chunk_preparation"]["status"],
                "warnings": ["Resolve every routing exception before completing locator_chunk_preparation."],
            }, 2)

        output_paths = {item["path"] for item in artifact_details}
        collisions = sorted(
            item["path"] for item in state["artifacts"]
            if item.get("path") in output_paths and item.get("stage") != "locator_chunk_preparation"
        )
        require(not collisions, "registered_output_collision", "Locator output would overwrite an artifact registered to another stage.", collisions)
        for _, path, payload in packet_outputs:
            replace_bytes_atomic(path, payload)
        updated = deepcopy(state)
        stamp = utc_now()
        records = [
            locator_artifact_record(path, root, "candidate_locator_chunk", packet["schema_version"], stamp)
            for packet, path, _ in packet_outputs
        ]
        updated["artifacts"] = [item for item in updated["artifacts"] if item.get("stage") != "locator_chunk_preparation"] + records
        updated["artifacts"].sort(key=lambda item: item["path"])
        updated["stages"]["locator_chunk_preparation"] = {
            "status": "completed", "updated_at": stamp,
            "notes": [f"Registered {len(packets)} frozen locator packets with complete exact-once routing."],
        }
        updated["updated_at"] = stamp
        validation_errors, final_warnings = validate_state(updated, state_path=state_path, check_files=True)
        require(not validation_errors, "canonical_state_invalid", "Locator preparation would leave invalid canonical state.", validation_errors)
        save_state(state_path, updated)
        action = next_stage(updated)
    emit({
        "command": "prepare-locator-chunks", "ok": True,
        "evaluation_id": updated["evaluation_id"], "candidate_id": candidate["candidate_id"],
        "artifacts_written": [item["path"] for item in artifact_details],
        "locator_packets": artifact_details,
        "counts": {"frozen_chunks": len(packets), "packets": len(packets), "routed_assignments": sum(item["locator_assignment_count"] for item in artifact_details), "routing_exceptions": 0},
        "stage_status": "completed", "next_actions": [] if action is None else [action],
        "warnings": [*warnings, *final_warnings],
    })


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    expand = commands.add_parser("expand-page-map")
    expand.add_argument("--input", required=True)
    expand.add_argument("--output", required=True)
    expand.set_defaults(func=command_expand_page_map)

    chunks = commands.add_parser("validate-chunks")
    chunks.add_argument("--input", required=True)
    chunks.add_argument("--page-map", required=True)
    chunks.add_argument("--output", required=True)
    chunks.set_defaults(func=command_validate_chunks)

    split_pdf = commands.add_parser("split-pdf")
    split_pdf.add_argument("--source", required=True)
    split_pdf.add_argument("--page-map", required=True)
    split_pdf.add_argument("--chunks", required=True)
    split_pdf.add_argument("--output-dir", required=True)
    split_pdf.set_defaults(func=command_split_pdf)

    prepare = commands.add_parser("prepare-locator-chunks")
    prepare.add_argument("--state", required=True)
    prepare.add_argument("--normalized-candidate", required=True)
    prepare.add_argument("--page-map", required=True)
    prepare.add_argument("--chunk-manifest", required=True)
    prepare.add_argument("--benchmark", required=True)
    prepare.add_argument("--output-dir")
    prepare.set_defaults(func=command_prepare_locator_chunks)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except PreparationError as exc:
        payload: dict[str, Any] = {"ok": False, "error": {"code": exc.code, "message": exc.message}}
        if exc.details is not None:
            payload["error"]["details"] = exc.details
        emit(payload, 1)


if __name__ == "__main__":
    main()
