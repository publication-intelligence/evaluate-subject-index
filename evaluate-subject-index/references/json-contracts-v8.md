# Current V8 JSON contracts

The active workflow uses these primary identities:

| Artifact | Schema identity |
| --- | --- |
| Evaluation state | `subject-index-evaluation-state-v6` |
| Locator audit | `locator-audit-v2` |
| Missing-access audit | current schema declared by the V8 scoring input |
| Structure audit | `structure-audit-v5` |
| Evaluation policy | `subject-index-evaluation-policy-v4` |
| Candidate locator packet | `candidate-locator-chunk-v1` |
| Locator routing exceptions | `candidate-locator-routing-exceptions-v1` |
| Calculation input | `subject-index-dimension-calculation-input-v2` |
| Dimension calculations | `subject-index-dimension-calculations-v6` |
| Item assessments | `subject-index-item-assessments-v6` |
| Evaluation result | `subject-index-evaluation-result-v11` |
| Projection metadata | `subject-index-v8-projection-metadata-v1` |
| Web report | `subject-index-web-report-v9` |
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
- Locator-packet preparation registers exactly one packet per frozen manifest chunk plus an empty routing-exception ledger; any unresolved or ownerless assignment prevents the state transition.
- The candidate's frozen benchmark path and canonical benchmark identity in state are the locator-preparation binding. There is no candidate-benchmark repository-lock contract.
- Explanation fields are metadata, not calculation inputs.
- Dimension rows use percentage fields and `weighted_contribution`; caps use `maximum_percentage`. `overall_percentage` is the only rounded score field, with its exact input recorded in `final_rounding`.
- Checkpoint import validates safe ZIP structure, inventory membership, and current state shape; it does not require a previously published checksum.

Runtime commands accept current schemas only; they do not advertise migration or compatibility entry points.
The percentage-native arithmetic is a breaking score-contract change: calculation V5/profile V4, result V10, and report V8 artifacts are not accepted as current. Rebuild scoring and report projections from the unchanged frozen evidence under the identities above; do not relabel an older rounded artifact.
