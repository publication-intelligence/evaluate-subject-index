"""Shared JSON Schema validation for current evaluation artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
import runtime_profile


SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "references" / "schemas"


def _decimal_numbers(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _decimal_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimal_numbers(item) for item in value]
    return value


@lru_cache(maxsize=1)
def _schema_store() -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    for path in SCHEMA_ROOT.glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        store[path.name] = document
        store[path.resolve().as_uri()] = document
    return store


def schema_errors(document: Any, schema_name: str, *, profile: str | None = None) -> list[str]:
    """Return deterministic, path-qualified structural errors."""
    requested_schema = schema_name
    if (
        (profile or runtime_profile.ACTIVE) == "v10s"
        and requested_schema in {"evaluation-policy-v4.schema.json", "evaluation-policy-v6.schema.json"}
        and isinstance(document, dict)
        and document.get("schema_version") == "subject-index-evaluation-policy-v6"
    ):
        # Read-only compatibility for already frozen V10 policies. New policies
        # are created as V7; preserved V6 bytes remain valid source evidence.
        profile = "v10"
    if requested_schema == 'locator-audit-v2.schema.json' and (profile or runtime_profile.ACTIVE) == 'v10s' and document.get('schema_version') == 'locator-audit-v2':
        if any('axis_resolution' in row or row.get('judgment') in {'semantic_unresolved','not_kept_subtype_unresolved'} for row in document.get('judgments',[])):
            return ['Semantic uncertainty requires the new locator-audit-v3 identity']
        profile = 'v10'
    schema_name = runtime_profile.schema_name(schema_name, profile=profile)
    schema_path = SCHEMA_ROOT / schema_name
    schema = _schema_store()[schema_name]
    resolver = jsonschema.RefResolver(
        base_uri=schema_path.resolve().as_uri(),
        referrer=schema,
        store=_schema_store(),
    )
    errors = sorted(
        jsonschema.Draft202012Validator(schema, resolver=resolver).iter_errors(
            _decimal_numbers(document)
        ),
        key=lambda item: [str(part) for part in item.absolute_path],
    )
    messages = [
        f"{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in errors
    ]
    if not messages and requested_schema in {"evaluation-state.schema.json", "evaluation-state-v7.schema.json", "evaluation-state-v8.schema.json"} and "study_comparison" in document:
        messages.extend("study_comparison." + message for message in schema_errors(document["study_comparison"], "retrospective-study-binding.schema.json", profile=profile))
    if not messages and requested_schema in {"evaluation-policy-v4.schema.json", "evaluation-policy-v5.schema.json", "evaluation-policy-v6.schema.json"}:
        messages.extend(policy_migration_errors(document))
    if not messages and schema_name in (*runtime_profile.SCHEMAS.values(), *runtime_profile.V10_SCHEMAS.values(), *runtime_profile.V10S_SCHEMAS.values()):
        from v9_contract import contract_errors
        messages.extend(contract_errors(document, allow_semantic=schema_name in runtime_profile.V10S_SCHEMAS.values()))
    if not messages and schema_name in (*runtime_profile.V10_SCHEMAS.values(), *runtime_profile.V10S_SCHEMAS.values()):
        from v10_contract import contract_errors
        messages.extend(contract_errors(document))
    if not messages and (profile or runtime_profile.ACTIVE) in {'v10','v10s'} and schema_name in {'structure-audit-v5.schema.json','structure-audit-v6.schema.json'}:
        from v10_contract import candidate_defect_errors
        messages.extend(candidate_defect_errors(document))
    if not messages and schema_name in runtime_profile.V10S_SCHEMAS.values():
        from v10_semantic_contract import contract_errors
        messages.extend(contract_errors(document))
    return messages


def policy_migration_errors(policy: dict[str, Any]) -> list[str]:
    """Cross-field provenance checks shared by every policy schema consumer."""
    study = policy.get("retrospective_study_migration")
    if study is not None:
        errors = []
        if policy["freeze"] != {"frozen_at": study["migrated_at"], "candidate_seen": True}:
            errors.append("Study migration must preserve actual candidate-visible freeze.")
        if policy["policy_id"] == study["previous_policy"]["policy_id"] or policy["policy_sha256"] == study["previous_policy"]["policy_sha256"]:
            errors.append("Study policy migration requires a distinct policy identity.")
        try:
            dates = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in (study["original_freeze"]["frozen_at"], study["previous_policy"]["freeze"]["frozen_at"], study["migrated_at"])]
            if any(value.utcoffset() is None for value in dates) or not dates[0] <= dates[1] <= dates[2]:
                errors.append("Study migration chronology is inconsistent.")
        except ValueError:
            errors.append("Study policy migration dates require ISO 8601 timezones.")
        # This check covers every policy schema consumer, including audit import.
        from study_comparison import policy_semantic_hash
        if policy_semantic_hash(policy) != study["target_policy_semantic_sha256"]:
            errors.append("Study policy settings do not match the approved semantic fingerprint.")
        return errors
    migration = policy.get("retrospective_migration")
    if migration is None:
        return []
    errors = []
    original = migration["original_policy"]
    if policy["freeze"] != {"frozen_at": migration["migrated_at"], "candidate_seen": migration["candidate_seen"]}:
        errors.append("Migration timestamp/visibility must match the actual policy freeze.")
    if policy["policy_id"] == original["policy_id"] or policy["policy_sha256"] == original["policy_sha256"]:
        errors.append("Migration requires a new policy identity and hash.")
    if original["freeze"]["candidate_seen"] is not False:
        errors.append("Original policy must retain its candidate-blind freeze.")
    if "targeted_migration" in policy["policy_profile"]:
        errors.append("Use retrospective_migration instead of the targeted_migration workaround.")
    try:
        original_time = datetime.fromisoformat(original["freeze"]["frozen_at"].replace("Z", "+00:00"))
        migration_time = datetime.fromisoformat(migration["migrated_at"].replace("Z", "+00:00"))
        if original_time.utcoffset() is None or migration_time.utcoffset() is None:
            raise ValueError("timezone required")
        if migration_time < original_time:
            errors.append("Migration timestamp precedes the original freeze.")
    except ValueError:
        errors.append("Original freeze and migration timestamps must be ISO 8601 with timezones.")
    return errors
if __name__ == "__main__":
    __import__("runtime_profile").require_public_cli()
