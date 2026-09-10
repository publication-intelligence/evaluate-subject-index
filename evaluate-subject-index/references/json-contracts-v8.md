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
| Candidate normalization issues | `candidate-normalization-issues-v1` (only when non-empty) |
| Locator routing failure diagnostic | `candidate-locator-routing-exceptions-v1` |
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
- Stable semantic IDs join worker records. Calculation-input file references and their
  verified bytes define the selected scoring artifacts.
- Benchmark review uses one draft artifact SHA-256, exact stable-ID coverage, and an exact normalized `approved_changes` ledger. Its deterministic screen is recomputed as a temporary queue and is not registered.
- `benchmark_review_cli.py freeze` is the normal completion path for `benchmark_review` and `benchmark_freeze`; it registers the review and final benchmark in one atomic state replacement.
- `dimension_score_v8_cli.py register-structure`, `score`, and `build-report` are the normal completion paths for the final three stages. They select exact registered inputs, reject missing, duplicate, changed, or cross-boundary artifacts, and replace state only after all current-schema outputs validate.
- Worker provenance is informational. Repeated source, policy, page-map, manifest,
  candidate-file, inventory-file, and audit-set hashes are not scoring gates.
- Locator- and missing-access-audit set hashes are computed deterministically from
  the selected files and their stable IDs, then recorded in calculation outputs.
- The structure audit binds complete stable-ID denominators for nodes, cross-references, and locator-bearing paths. Full mode stores only exceptions plus a complete-scope pass attestation; pilot mode lists observed passes and preserves every unlisted denominator identity as `not_measured`.
- Every locator judgment states `complete_path_fit`; scoring does not infer it from prose or another artifact.
- Current audit denominators must be complete and non-overlapping before a stage is marked complete.
- Candidate preparation computes its exact-set fidelity checks and registers no empty or pass-only report artifact.
- Locator-packet preparation registers exactly one packet per frozen manifest chunk. An unresolved or ownerless assignment writes an unregistered failure diagnostic and prevents packet writes and the state transition.
- The candidate's frozen benchmark path and canonical benchmark identity in state are the locator-preparation binding. There is no candidate-benchmark repository-lock contract.
- Explanation fields are metadata, not calculation inputs.
- Checkpoint import validates safe ZIP structure, inventory membership, and current state shape; it does not require a previously published checksum.

Runtime commands accept the listed schemas directly.
