# Current V8 JSON contracts

Current methodology: **V8.2**. Read [Consequence policy and targeted migration](consequence-policy-v8.2.md); it supersedes older cap, publication-gate, and validity language below. Frozen V8 evaluations require explicit migration and new policy/calculation identities.

The active workflow uses these primary identities:

| Artifact | Schema identity |
| --- | --- |
| Evaluation state | `subject-index-evaluation-state-v6` |
| Locator audit | `locator-audit-v2` |
| Missing-access audit | current schema declared by the V8 scoring input |
| Structure audit | `structure-audit-v6` |
| Evaluation policy | `subject-index-evaluation-policy-v4` |
| Reviewed-legacy compatibility approval | `source-benchmark-compatibility-approval-v1` |
| Reviewed-legacy import provenance | `source-benchmark-compatibility-import-provenance-v1` |
| Candidate locator packet | `candidate-locator-chunk-v1` |
| Candidate normalization issues | `candidate-normalization-issues-v1` (only when non-empty) |
| Locator routing failure diagnostic | `candidate-locator-routing-exceptions-v1` |
| Calculation input | `subject-index-dimension-calculation-input-v2` |
| Dimension calculations | `subject-index-dimension-calculations-v6` |
| Item assessments | `subject-index-item-assessments-v7` |
| Evaluation result | `subject-index-evaluation-result-v12` |
| Projection metadata | `subject-index-v8-projection-metadata-v2` |
| Web report | `subject-index-web-report-v10` |
| Canonical web projection | `ohfr-v8-canonical-web-projection-v1` |
| Web collections | `ohfr-v8-web-collection-v1` |
| Optional correction overlay | `ohfr-v8-representation-correction-overlay-v1` |
| Checkpoint bundle | `subject-index-bundle-v2` |

`subject-index-heading-access-causal-projection-input-v1` is a score-free, exact-hash-bound input used only to project a frozen `structure-audit-v5` into a new V6 reporting artifact. It does not migrate or recalculate scores.

## Contract rules

- JSON Schema is the single source of truth for artifact structure: required fields,
  types, enums, and nested object shapes live in `references/schemas/`.
- Python validators enforce only semantics that span fields or artifacts, such as
  identity agreement, exact workset coverage, ownership, and recomputed totals.
- Policy V4 and build-input V1 optionally carry `retrospective_migration`, defined by `retrospective-migration.schema.json`. Fresh freezes remain candidate-blind; migrations bind the original policy/freeze, actual migration visibility/time, authorization, change ledger, and reused stage evidence. See the [migration contract](consequence-policy-v8.2.md#retrospective-policy-provenance-contract). This field never enters score arithmetic.
- Structure V6 optionally carries `uncertainty_gate_scopes`, an evidence-bound supplement to unchanged uncertainty records. It distinguishes exact locator support, explicitly path-wide support, benchmark access, measurement/provenance limitations, reference destinations, and unknown scope. Missing/unknown applicability yields a gate-assessment gap; contextual paths do not automatically make sibling locators uncertain. See [scoped uncertainty](consequence-policy-v8.2.md#scoped-uncertainty). The supplement never enters arithmetic.
- `evaluation-state.json` is the only control inventory.
- Registered paths are relative to the evaluation root and unique.
- Stable semantic IDs join worker records. Calculation-input file references and their
  verified bytes define the selected scoring artifacts.
- Benchmark review uses one draft artifact SHA-256, exact stable-ID coverage, and an exact normalized `approved_changes` ledger. Its deterministic screen is recomputed as a temporary queue and is not registered.
- `benchmark_review_cli.py freeze` is the normal completion path for `benchmark_review` and `benchmark_freeze`; it registers the review and final benchmark in one atomic state replacement.
- `benchmark_review_cli.py import-reviewed-legacy` is the narrow exception for exact candidate-blind releases with completed full review. Its distinct compatibility approval does not claim a new full editorial review.
- `dimension_score_v8_cli.py register-structure`, `score`, and `build-report` are the normal completion paths for the final three stages. They select exact registered inputs, reject missing, duplicate, changed, or cross-boundary artifacts, and replace state only after all current-schema outputs validate. `build-report` registers the report, projection, and every collection in the same state inventory and rolls back new output files if the commit fails.
- The projection preserves the established `correction_outcomes` contract and adjustment-status vocabulary. A confirmed registered overlay adds the fourth collection binding and `data/correction-overlay.v1.json`; otherwise exactly three collection bindings are emitted and the overlay file is absent.
- Public collections may retain evidence IDs and finalized judgments but never source excerpts, quotes, PDFs, absolute paths, private layout evidence, storage-provider identifiers, secrets, or restricted inputs.
- The V10 web report may include the optional typed `presentation_summary` projection. It contains only public-safe numeric/category reporting values derived from the canonical calculation and registered inputs. Its legacy-named `web_report_sha256` provenance field is the registered dimension-calculation file SHA-256 (`calculation_explainer.sha256`); the canonical projection separately binds the final report-file SHA-256.
- The V10 calculation explainer and canonical projection score view expose the canonical per-dimension component denominator records. These distinguish diagnostic item outcomes from aggregate-score applicability, including frozen optional-subject exclusions.
- Canonical projection scorecards preserve authoritative `dimension_percentage` and `weighted_contribution` values as exact decimal strings. The numeric `rating`, `awarded_points`, and `maximum_points` fields remain nonauthoritative transport aliases solely for the established generic website adapter; canonical arithmetic never consumes them. The density collection likewise preserves authoritative `fit_percentage` alongside its adapter-only `fit_rating` alias.
- `build-report --replace-complete-bundle` may read either exact registered predecessor shape—adapter aliases only or authoritative percentage fields only—solely to validate and atomically replace that bundle. New output always has to include both the corrected authoritative fields and the compatibility aliases.
- Within that presentation projection, the established legacy metric ID `valid_entry_precision_at_least_partial` is an explicit display alias for the canonical Reliability F1 component; consumers must not infer that relationship from the ID text.
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
- The public web report preserves the structure audit's raw density measurements and
  projects `density_fit_percentage` plus `chapter_fit_by_chunk` from the canonical
  `editorial_selectivity` `density_fit` component. Chunk IDs are the join key; array
  position is never a binding.
- Heading-access causal findings are source-linked reporting metadata, not calculation inputs. Generic-only adverse heading-access judgments and unresolved source or evidence IDs fail validation.
- Checkpoint import validates safe ZIP structure, inventory membership, and current state shape; it does not require a previously published checksum.

Runtime commands accept the listed schemas directly.
