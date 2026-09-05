# Current V8 JSON contracts

The active workflow uses these primary identities:

| Artifact | Schema identity |
| --- | --- |
| Evaluation state | `subject-index-evaluation-state-v6` |
| Locator audit | `locator-audit-v2` |
| Missing-access audit | current schema declared by the V8 scoring input |
| Structure audit | `structure-audit-v5` |
| Evaluation policy | `subject-index-evaluation-policy-v4` |
| Calculation input | `subject-index-dimension-calculation-input-v2` |
| Dimension calculations | `subject-index-dimension-calculations-v5` |
| Item assessments | `subject-index-item-assessments-v6` |
| Evaluation result | `subject-index-evaluation-result-v10` |
| Projection metadata | `subject-index-v8-projection-metadata-v1` |
| Web report | `subject-index-web-report-v8` |
| Checkpoint bundle | `subject-index-bundle-v2` |

## Contract rules

- JSON Schema is the single source of truth for artifact structure: required fields,
  types, enums, and nested object shapes live in `references/schemas/`.
- Python validators enforce only semantics that span fields or artifacts, such as
  identity agreement, exact workset coverage, ownership, and recomputed totals.
- `evaluation-state.json` is the only control inventory.
- Registered paths are relative to the evaluation root and unique.
- Stable IDs and content hashes join related records and detect accidental input mix-ups.
- Current audit denominators must be complete and non-overlapping before a stage is marked complete.
- Explanation fields are metadata, not calculation inputs.
- Checkpoint import validates safe ZIP structure, inventory membership, and current state shape; it does not require a previously published checksum.

Runtime commands accept current schemas only; they do not advertise migration or compatibility entry points.
