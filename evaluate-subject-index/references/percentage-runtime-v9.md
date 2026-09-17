# V9 percentage runtime and explicit cutover

V9 preserves V8.2 judgments, weights, thresholds, consequences, gates, caps, uncertainty, benchmark content, density bands, and final rounding. It introduces explicit percentage-only output shapes and source/migration provenance. Existing CLI entrypoints and schemas retain V8.2. V9 is selected once, before workflow imports, with `v9_cli.py`; no environment setting or display label selects a runtime.

## Commands

Use `python scripts/v9_cli.py TOOL ...`, retaining the underlying tool's arguments. Tools are `state`, `policy`, `page-chunks`, `prepare-candidate`, `audit-candidate`, `score`, `grade`, `study`, and `bundle`. The source-only discovery/review/freeze workflow remains V8.2 for this cutover.

```bash
python scripts/v9_cli.py study policy-template \
  --input /preserved/source-policy.json --from-source-policy \
  --output /staging/v9-study-policy-template.json
python scripts/v9_cli.py study migrate-benchmark \
  --state /candidate/evaluation-state.json \
  --study-lock /reviewed/study-benchmark-lock.v2.json \
  --study-policy /reviewed/v9-study-policy-template.json \
  --release-state /preserved/source-state.json \
  --release-policy /preserved/source-policy.json \
  --release-draft /preserved/source-draft.json \
  --release-review /preserved/source-review.json \
  --release-benchmark /preserved/source-benchmark.json \
  --approval /approved/candidate-migration.json --output-dir migration-v9
```

These paths are examples, not a selected release. Migration requires the existing explicit retrospective approval, binding the actual prior candidate state/policy/benchmark and target lock/template. It preserves the previous state and source proof, records actual candidate-visible migration time, and invalidates downstream candidate audit/scoring registrations. It does not authorize audit transfer or manufacture a fresh source review.

## Version identities

| Artifact or profile | V8.2 | V9 |
|---|---|---|
| Policy profile | subject-index-standard-policy-v8.2 | subject-index-standard-policy-v9 |
| Rubric | subject-index-rubric-v8.2 | subject-index-rubric-v9 |
| Calculation profile | subject-index-dimension-calculation-v7 | subject-index-dimension-calculation-v8 |
| State | subject-index-evaluation-state-v6 | subject-index-evaluation-state-v7 |
| Policy | subject-index-evaluation-policy-v4 | subject-index-evaluation-policy-v5 |
| Calculation input | subject-index-dimension-calculation-input-v2 | subject-index-dimension-calculation-input-v3 |
| Calculations | subject-index-dimension-calculations-v6 | subject-index-dimension-calculations-v7 |
| Item assessments | subject-index-item-assessments-v7 | subject-index-item-assessments-v8 |
| Result | subject-index-evaluation-result-v12 | subject-index-evaluation-result-v13 |
| Report | subject-index-web-report-v10 | subject-index-web-report-v11 |
| Projection metadata | subject-index-v8-projection-metadata-v2 | subject-index-v9-projection-metadata-v1 |
| Web projection | ohfr-v8-canonical-web-projection-v1 | ohfr-v9-canonical-web-projection-v1 |
| Web collections | ohfr-v8-web-collection-v1 | ohfr-v9-web-collection-v1 |
| Study lock | subject-index-study-benchmark-lock-v1 / ohfr-study-benchmark-lock-v1 | corresponding v2 |

Benchmark, source draft/review, candidate normalization, locator/missing-access/structure audits and diagnostic grading policy retain their existing shape identities. Binary `rating_credit` is a keep decision and remains unchanged. Item diagnostic `grade.score` remains the existing numeric 0–100 display score with its existing rounding and bands; `grade.rating` is removed.

## Percentage contract

V9 artifacts reject `rating`, `rating_delta`, `maximum_rating`, and `*_rating` fields at every depth. Authoritative percentages and point contributions are decimal strings. Raw integer counts and source-word denominators retain their integer types. There is no intermediate display rounding added. Discrete 0–5 judgments map exactly to 0/20/40/60/80/100; V8.2 already calculated these percentages internally.

Editorial Selectivity exposes `substantive_selectivity_percentage`, `density_fit_percentage`, `substantive_points_out_of_10`, and `density_points_out_of_5` in its calculation and public scorecard. Public scorecard `awarded_points` and `maximum_points` are true points, represented as decimal strings and equality-validated against the authoritative contribution and weight.

Each density chapter preserves its frozen order, raw counts/rates and `indexable_source_words`, plus `path_fit_percentage`, `occurrence_fit_percentage`, `unit_fit_percentage`, and `weighted_percentage_numerator`. The aggregate exposes `total_weighted_percentage_numerator` and `total_indexable_source_words`.

```text
unit_fit_percentage = (path_fit_percentage + occurrence_fit_percentage) / 2
weighted_percentage_numerator = unit_fit_percentage × indexable_source_words
density_fit_percentage = Σ weighted_percentage_numerator / Σ indexable_source_words
substantive_points_out_of_10 = substantive_selectivity_percentage × 10 / 100
density_points_out_of_5 = density_fit_percentage × 5 / 100
selectivity percentage = (substantive percentage × 10 + density percentage × 5) / 15
dimension contribution = dimension percentage × weight / 100
```

All operations retain the existing 28-digit Decimal context, canonical operation order and final `ROUND_HALF_UP` to 0.01. The canonical contribution is computed from the combined percentage, then multiplied by the dimension weight and divided by 100. The component-sum formula is mathematically equivalent but must not replace that operation order: for substantive `100/3` and density `50`, the canonical contribution is `5.833333333333333333333333334`, while reassociating the two point contributions produces `5.833333333333333333333333333`. Each component validates exactly against its own formula; `awarded_points` validates exactly against canonical `weighted_contribution`, not a reassociated sum. Existing non-attempt overrides still apply: public density reports expose the observed weighted density and separately `scoring_density_fit_percentage`; the selectivity component retains the actual scoring override. No threshold or override changes are implied by the added fields.

## Preserved source proof

The V9 lock requires `source_methodology` with exactly these fields:

```json
{
  "policy_profile": "subject-index-standard-policy-v8.2",
  "rubric_version": "subject-index-rubric-v8.2",
  "calculation_profile": "subject-index-dimension-calculation-v7",
  "source_policy_sha256": "actual canonical source-policy hash",
  "source_policy_file_sha256": "actual frozen source-policy file hash"
}
```

Actual hashes must be 64 lowercase hexadecimal characters. The lock selects `current_source_freeze` lineage and binds the actual unchanged source state/draft/review/final bytes. Source state and policy validate explicitly under V8 schemas; source policy must retain its candidate-blind freeze and exact typed state registration. V9 target policy must equal the complete source policy semantic content after only these substitutions: schema version, policy profile ID, content-policy profile IDs, and density-metric provenance profile IDs. Consequence-policy reference and every other field, including extensions, remain unchanged and fingerprinted. Unknown provenance fields/profiles, missing policy, wrong hashes or altered source chain fail closed.

The V9 state binding adds the preserved release-policy artifact and explicit methodology migration record. Public study comparison identities disclose the preserved source methodology and require agreement across candidates. Original source proof is never rewritten to make version strings agree.

## Benchmark repository validator adaptation

The pinned-7ed successor validator remains the reviewed V8 baseline. A separately reviewed V9 validator should pin the reviewed V9 methodology commit and select V9 before importing its workflow modules. Keep the same selected artifact roles and exact freeze-byte checks. Pass its existing `source_policy` role as `policy_path` to `study_comparison.validate_native_lineage`; validate the V9 lock/template against this preserved source policy, without constructing a replacement source policy or state. Use the new lock v2 and source-methodology fields above. Do not relabel an actual release descriptor or create a lock until the source freeze and V9 validator have been reviewed.

The existing 15 successor-validator fixtures/network bootstrap smoke remain baseline evidence only. The benchmark owner must add V9 source-profile/hash/missing-proof and semantic-change rejection tests, retain all original historical-v3 checks, and validate the actual selected release separately. This methodology change performs no activation, release selection, or candidate evaluation.

## Regression evidence

`tests/fixtures/v9/v8.2-boundaries.json` was generated from the verified staged runtime at commit `7ed97581c1e82eb13052874b0e82eb429580a7b1`. `tests/v9_golden_probe.py` supplies 29 density-band boundaries, 36 selectivity-cap boundaries, five reliability judgments/uncertainty cases, five selectivity cases, 12 destination-gate cases, and three final-rounding boundaries. Both runtime profiles must match the complete golden outcomes after removing only enumerated V9 representation additions and translating the calculation-profile prefix. No judgment, gate, cap, bound, threshold, contribution or score is removed from the comparison.

Additional tests exercise the real source-freeze/migration/scoring/report chain, preserved source bytes, prior-state retention, audit invalidation, V8 rejection of V9 state, exact denominator/numerator checks, forbidden aliases, and provenance/policy tampering. Original V8 fixtures remain unchanged.

Optional correction overlays use `ohfr-v9-representation-correction-overlay-v1` and `display_only_counterfactual_bound_to_canonical_v9`. They retain their display-only meaning and reject nested five-point aliases. An existing registered V8 overlay fails explicitly until recreated and rebound; it is never silently omitted or reinterpreted.

A future V10 needs separate profile/schema identities and an explicit semantic migration path. The V9 source-policy equality rule must remain frozen; it cannot admit new standards requirements by widening its allowed substitutions. The process selector is intentionally limited to V8/V9 today. V10 should extend profile dispatch explicitly and reuse the preserved percentage contract where applicable, rather than treating every future version as `is_v9()`.
