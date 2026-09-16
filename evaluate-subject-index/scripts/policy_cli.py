#!/usr/bin/env python3
"""Instantiate the built-in subject-index evaluation policy deterministically."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schema_validation import schema_errors


POLICY_SCHEMA = "subject-index-evaluation-policy-v4"
POLICY_PROFILE = "subject-index-standard-policy-v8.1"

DEFAULT_INCLUDED = [
    "preparation-approved indexable content",
    "substantive body, chapter, and part text",
    "substantive block quotations",
    "substantive inspectable notes, footnotes, and endnotes",
    "substantive captions and table text",
    "eligible text whose role remains unknown",
]

DEFAULT_EXCLUDED = [
    "front or back matter designated nonindexable",
    "bibliographies and source lists",
    "publisher and candidate indexes",
    "contents pages and navigation lists",
    "running furniture and page numbers",
    "proof or production material",
    "graph internals and ignored regions",
    "material unavailable in the supplied source",
]

POLICY_AREAS = {
    "scope_compliance": "standard-policy-v8.md#locator-utility",
    "substantive_coverage": "standard-policy-v8.md#locator-utility",
    "editorial_selectivity": "standard-policy-v8.md#locator-utility",
    "conceptual_stance_fidelity": "standard-policy-v8.md#locator-utility",
    "heading_access_architecture": "standard-policy-v8.md#locator-strings-and-ranges",
    "locator_quality": "standard-policy-v8.md#locator-utility",
    "compound_heading_scope": "standard-policy-v8.md#locator-utility",
    "cross_references": "standard-policy-v8.md#locator-utility",
    "whole_index_coherence": "standard-policy-v8.md#locator-strings-and-ranges",
    "mechanical_validity": "standard-policy-v8.md#locator-strings-and-ranges",
}

STAGE_APPLICATION = {
    "source_subject_discovery": [
        "scope_compliance",
        "substantive_coverage",
        "editorial_selectivity",
        "conceptual_stance_fidelity",
        "locator_quality",
    ],
    "benchmark_freeze": [
        "substantive_coverage",
        "conceptual_stance_fidelity",
        "heading_access_architecture",
        "whole_index_coherence",
    ],
    "locator_audit": [
        "scope_compliance",
        "editorial_selectivity",
        "conceptual_stance_fidelity",
        "locator_quality",
        "compound_heading_scope",
    ],
    "missing_access_audit": [
        "substantive_coverage",
        "conceptual_stance_fidelity",
        "heading_access_architecture",
        "locator_quality",
        "cross_references",
    ],
    "structure_audit": [
        "scope_compliance",
        "editorial_selectivity",
        "conceptual_stance_fidelity",
        "heading_access_architecture",
        "compound_heading_scope",
        "cross_references",
        "whole_index_coherence",
        "mechanical_validity",
    ],
    "deterministic_validation": [
        "scope_compliance",
        "heading_access_architecture",
        "locator_quality",
        "cross_references",
        "mechanical_validity",
    ],
}

DENSITY_METRICS = [
    {
        "metric_id": "locator_bearing_heading_paths_per_1000_source_words",
        "unit": "locator-bearing complete heading paths per 1,000 indexable source words",
        "scored": True,
        "weight": 0.5,
        "target": 8.0,
        "ideal_min": 6.0,
        "ideal_max": 10.0,
        "acceptable_min": 4.0,
        "acceptable_max": 12.0,
        "provenance": POLICY_PROFILE,
    },
    {
        "metric_id": "locator_occurrences_per_1000_source_words",
        "unit": "expanded locator occurrences per 1,000 indexable source words",
        "scored": True,
        "weight": 0.5,
        "target": 20.0,
        "ideal_min": 15.0,
        "ideal_max": 25.0,
        "acceptable_min": 10.0,
        "acceptable_max": 30.0,
        "provenance": POLICY_PROFILE,
    },
]

CRITICAL_GATES = [
    ("GATE-SCOPE-LOCATOR", "Major/critical misleading or blocking delivered fabricated, nonexistent, or out-of-scope locator with severe mismatch/no fit"),
    ("GATE-SYSTEMIC-UNSUPPORTED", "Delivered severe/no-fit locator pattern: >=10 distinct items, >=5% of denominator, >=2 sections spanning >=25% of source or structure"),
    ("GATE-CENTRAL-OMISSION", "Critical central omission or major omission demonstrably destroying high-priority access"),
    ("GATE-STANCE", "Major/critical materially misleading reversal or misrepresentation of source stance or relationship"),
    ("GATE-COMPOUND", "Major/critical misleading or blocking compound heading supported by delivered severe-mismatch/no-fit locator evidence"),
    ("GATE-SEE-SUBSTITUTION", "Major/critical delivered substitutive see blocks warranted substantive access"),
    ("GATE-CROSS-REFERENCE", "Delivered broken reference with major/critical blocking or misleading consequence, or frozen systemic threshold; missing warranted routes excluded"),
    ("GATE-CLUTTER", "One clutter root cause: >=10 distinct items, >=5% of applicable population, >=2 sections spanning >=25% of source or structure"),
    ("GATE-GROUNDING", "Major/critical delivered severe-mismatch/no-fit locator materially misleads or blocks; stance, compound, and invalid destination gates own their specific evidence"),
    ("GATE-STRUCTURE", "True candidate-output structural failure: critical representation/mechanical corruption, or empty, incomplete, unparseable candidate output"),
]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_hash(payload: dict[str, Any], own_hash_field: str) -> str:
    clone = dict(payload)
    clone.pop(own_hash_field, None)
    encoded = json.dumps(clone, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def unique_strings(values: list[Any], field: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} values must be non-empty strings")
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def read_input(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    errors = schema_errors(value, "policy-build-input.schema.json")
    if errors:
        raise ValueError("Policy build input is structurally invalid: " + "; ".join(errors))
    return value


def build_policy(source: dict[str, Any], *, original_policy: dict[str, Any] | None = None,
                 base_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    scope = source.get("source_scope", {})
    audience = source.get("audience", {})
    audit = source.get("audit_design", {})
    span = scope.get("document_page_span")
    if not (isinstance(span, list) and len(span) == 2 and all(isinstance(item, int) for item in span) and span[0] <= span[1]):
        raise ValueError("source_scope.document_page_span must be an ascending integer pair")
    deviations = source.get("deviations", [])

    stamp = now()
    policy: dict[str, Any] = {
        "schema_version": POLICY_SCHEMA,
        "policy_id": source.get("policy_id") or "subject-index-policy",
        "policy_profile": {
            "id": POLICY_PROFILE,
            "consequence_policy_reference": "consequence-policy-v8.1.md",
        },
        "source_scope": {
            "source_sha256": scope["source_sha256"],
            "document_page_span": span,
            "page_map_sha256": scope["page_map_sha256"],
            "chunk_manifest_sha256": scope["chunk_manifest_sha256"],
            "included": unique_strings(DEFAULT_INCLUDED + list(scope.get("source_specific_included", [])), "source_scope.included"),
            "excluded": unique_strings(DEFAULT_EXCLUDED + list(scope.get("source_specific_excluded", [])), "source_scope.excluded"),
            "availability": scope.get("availability", {}),
            "mixed_page_rule": "Evaluate eligible regions and ignore excluded regions on the same page.",
            "word_count_basis": "indexable source words only",
        },
        "audience": {
            "label": audience["label"],
            "basis": audience["basis"],
            "confidence": audience["confidence"],
            "rationale": audience["rationale"],
        },
        "audit_design": {
            "mode": audit.get("mode", "full"),
            "candidate_blindness": audit.get("candidate_blindness", "required"),
            "uncertainty_policy": "Record uncertainty explicitly; adjudicate every critical, major, and uncertain item; exclude uninspectable locators from precision denominators and disclose them.",
            "uninspectable_locator_rate_tolerance": 0.01,
        },
        "content_policies": {
            key: {"rule_reference": value, "profile": POLICY_PROFILE}
            for key, value in POLICY_AREAS.items()
        },
        "stage_application": STAGE_APPLICATION,
        "density_profile": {
            "status": "scored",
            "measurement_level": "chapter_or_approved_intellectual_unit",
            "aggregation": "indexable_source_word_weighted_mean",
            "rounding": "none_dimension_and_contribution; overall_nearest_0.01",
            "metrics": DENSITY_METRICS,
            "short_unit_rule": "Treat an unstable short unit as descriptive or combine it with a declared adjacent unit.",
            "rationale": "Permissive calibration for finished-index scale and distribution; never a subject-discovery quota or hard ceiling.",
            "maximum_score_contribution": 5,
        },
        "critical_gates": [
            {"gate_id": gate_id, "description": description, "standard": True}
            for gate_id, description in CRITICAL_GATES
        ],
        "deviations": deviations,
        "freeze": {"frozen_at": stamp, "candidate_seen": False},
        "policy_sha256": None,
    }
    migration = source.get("retrospective_migration")
    if migration is not None:
        errors = schema_errors(migration, "retrospective-migration.schema.json")
        if errors:
            raise ValueError("Invalid migration provenance: " + "; ".join(errors))
        if original_policy is None:
            raise ValueError("Retrospective migration requires --original-policy.")
        if not isinstance(original_policy, dict) or not isinstance(original_policy.get("policy_profile"), dict):
            raise ValueError("Original policy must be a policy object with a profile.")
        original = migration["original_policy"]
        for field in ("policy_id", "policy_sha256", "freeze"):
            if original[field] != original_policy.get(field):
                raise ValueError(f"Original policy {field} does not match preserved evidence.")
        if original["policy_profile_id"] != original_policy.get("policy_profile", {}).get("id"):
            raise ValueError("Original policy profile does not match preserved evidence.")
        if original_policy.get("policy_sha256") != canonical_hash(original_policy, "policy_sha256"):
            raise ValueError("Original policy self-hash does not reconstruct.")
        # Validate archived V8's structure without relabeling its preserved bytes.
        original_shape = deepcopy(original_policy)
        original_shape["policy_profile"]["id"] = POLICY_PROFILE
        errors = schema_errors(original_shape, "evaluation-policy-v4.schema.json")
        if errors:
            raise ValueError("Invalid original policy: " + "; ".join(errors))
        if base_policy is not None:
            errors = schema_errors(base_policy, "evaluation-policy-v4.schema.json")
            if errors or base_policy.get("policy_sha256") != canonical_hash(base_policy, "policy_sha256"):
                raise ValueError("Migration base must be a valid self-hashed V8.1 policy: " + "; ".join(errors))
            policy = deepcopy(base_policy)
            policy["policy_id"] = source["policy_id"]
            if policy["policy_id"] == base_policy["policy_id"]:
                raise ValueError("Provenance cleanup requires a new policy_id distinct from its base.")
        # Retain the frozen evaluation settings, including any non-default density.
        for field in ("source_scope", "audience", "audit_design", "density_profile", "deviations"):
            if base_policy is not None and field in ("source_scope", "audience", "audit_design") and base_policy[field] != original_policy[field]:
                raise ValueError(f"Migration base changed original {field}; investigate before cleanup.")
            policy[field] = deepcopy((base_policy or original_policy)[field])
        for field in ("source_sha256", "document_page_span", "page_map_sha256", "chunk_manifest_sha256", "availability"):
            if scope.get(field, {}) != policy["source_scope"][field]:
                raise ValueError(f"Migration input changed original source_scope.{field}.")
        if audience != policy["audience"] or any(audit.get(k) != policy["audit_design"][k] for k in ("mode", "candidate_blindness")):
            raise ValueError("Migration input must preserve original audience and audit design.")
        if deviations != policy["deviations"]:
            raise ValueError("Migration input must preserve original deviations.")
        policy["policy_profile"].pop("targeted_migration", None)
        policy["retrospective_migration"] = deepcopy(migration)
        policy["freeze"] = {"frozen_at": migration["migrated_at"], "candidate_seen": migration["candidate_seen"]}
    elif original_policy is not None or base_policy is not None:
        raise ValueError("Original/base policies require explicit retrospective_migration input.")
    policy["policy_sha256"] = canonical_hash(policy, "policy_sha256")
    errors = schema_errors(policy, "evaluation-policy-v4.schema.json")
    if errors:
        raise ValueError("Generated policy is structurally invalid: " + "; ".join(errors))
    return policy


def command_build(args: argparse.Namespace) -> None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    try:
        source = read_input(input_path)
        migration = source.get("retrospective_migration")
        preserved_paths = [input_path]
        preserved_paths += [Path(p) for p in (args.original_policy, args.base_policy) if p]
        if migration is not None:
            # References resolve relative to build input, never to process cwd.
            references = [migration["original_policy"]["artifact"]]
            references += [ref for stage in migration["reused_stages"].values() for ref in stage["evidence"]]
            for reference in references:
                evidence_path = input_path.parent / reference["path"]
                preserved_paths.append(evidence_path)
                content = evidence_path.read_bytes()
                if hashlib.sha256(content).hexdigest() != reference["sha256"]:
                    raise ValueError(f"Preserved evidence hash mismatch: {reference['path']}")
            if args.original_policy and Path(args.original_policy).read_bytes() != (input_path.parent / migration["original_policy"]["artifact"]["path"]).read_bytes():
                raise ValueError("--original-policy differs from the recorded original artifact.")
        original = json.loads(Path(args.original_policy).read_text()) if args.original_policy else None
        baseline = json.loads(Path(args.base_policy).read_text()) if args.base_policy else None
        policy = build_policy(source, original_policy=original, base_policy=baseline)
        if any(output_path.resolve() == p.resolve() or (output_path.exists() and output_path.samefile(p)) for p in preserved_paths):
            raise ValueError("Output must not overwrite build input or preserved migration evidence, even with --force.")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        raise SystemExit(1)
    if output_path.exists() and not args.force:
        print(json.dumps({"ok": False, "error": f"Refusing to overwrite {output_path}"}, indent=2))
        raise SystemExit(1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(policy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "command": "define-policy",
        "artifact_written": str(output_path.resolve()),
        "policy_profile": POLICY_PROFILE,
        "policy_sha256": policy["policy_sha256"],
        "deviation_count": len(policy["deviations"]),
    }, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--input", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--force", action="store_true")
    build.add_argument("--original-policy", help="Preserved candidate-blind policy required for retrospective migration.")
    build.add_argument("--base-policy", help="Latest frozen V8.1 policy to preserve during provenance-only cleanup.")
    build.set_defaults(func=command_build)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
