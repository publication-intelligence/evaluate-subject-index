"""Shared JSON Schema validation for current evaluation artifacts."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema


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


def schema_errors(document: Any, schema_name: str) -> list[str]:
    """Return deterministic, path-qualified structural errors."""
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
    if not messages and schema_name == "evaluation-policy-v4.schema.json":
        messages.extend(policy_migration_errors(document))
    return messages


def policy_migration_errors(policy: dict[str, Any]) -> list[str]:
    """Cross-field provenance checks shared by every policy schema consumer."""
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
