# Archived V8 command record

These commands document the frozen V8 implementation only. They are not
executable entry points in the current tree. Reproduce V8 from its pinned Git
revision; use `python scripts/v10_cli.py TOOL ...` for every current operation.

All paths below are examples. Use absolute paths or run from a stable evaluation directory.

## State

```bash
python scripts/state_cli.py init ...
python scripts/state_cli.py status --state evaluation-state.json
python scripts/state_cli.py next --state evaluation-state.json
python scripts/state_cli.py validate --state evaluation-state.json
python scripts/state_cli.py set-stage --state evaluation-state.json ...
```

State V6 is the only control inventory. Generic `set-stage` does not complete benchmark review, benchmark freeze, structure audit, scoring, or web report.

## Benchmark review and freeze

```bash
python scripts/benchmark_review_cli.py screen --draft benchmark/source-benchmark.draft.v1.json --output validation/source-benchmark-review-inventory.json
python scripts/benchmark_review_cli.py validate-review --draft benchmark/source-benchmark.draft.v1.json --inventory validation/source-benchmark-review-inventory.json --review validation/source-benchmark-review.v1.json
python scripts/benchmark_review_cli.py freeze --state evaluation-state.json --draft benchmark/source-benchmark.draft.v1.json --inventory validation/source-benchmark-review-inventory.json --review validation/source-benchmark-review.v1.json --final benchmark/source-benchmark.v1.json
```

The inventory is a temporary deterministic queue. Freeze recomputes it, validates exact review coverage and approved changes, registers only the review ledger and final benchmark, and completes both stages atomically.

To import an exact fully reviewed legacy release under the registered V8 policy without rerunning discovery or editorial review, first copy every legacy evidence input and the independent compatibility approval inside the target evaluation directory, then run:

```bash
python scripts/benchmark_review_cli.py import-reviewed-legacy \
  --state evaluation-state.json \
  --page-map source/page-map.json \
  --chunk-manifest source/chunk-manifest.json \
  --policy source/evaluation-policy.v4.json \
  --legacy-state import/legacy/evaluation-state.json \
  --legacy-page-map import/legacy/page-map.json \
  --legacy-chunk-manifest import/legacy/chunk-manifest.json \
  --legacy-policy import/legacy/evaluation-policy.json \
  --legacy-benchmark import/legacy/source-benchmark.json \
  --legacy-review-inventory import/legacy/source-benchmark-review-inventory.json \
  --legacy-review import/legacy/source-benchmark-review.json \
  --compatibility-approval validation/benchmark-compatibility-approval.v1.json \
  --output source/source-benchmark.v8-import.json \
  --provenance-output validation/benchmark-compatibility-import-provenance.v1.json
```

The approval must validate against `benchmark-compatibility-approval.schema.json` and bind every old and new file/canonical identity, the legacy artifact-freeze commit, the planned current benchmark identity, and the reviewer's candidate-blind compatibility attestations. It is not a replacement full-review ledger. The command refuses candidate-exposed state, partial legacy review, nonidentical mapping/chunk inputs, ambiguous key normalization, existing outputs, and every identity or hash mismatch.

## Checkpoint and resume

```bash
python scripts/bundle_cli.py checkpoint --state evaluation-state.json --output checkpoint.zip
python scripts/bundle_cli.py import-bundle --input checkpoint.zip --output-dir resumed
```

No previous archive checksum is needed. Import validates safe structure and current state.

## Candidate preparation

```bash
python scripts/candidate_preparation_cli.py normalize --layout candidate-layout-extraction.v1.json ...
python scripts/candidate_preparation_cli.py validate-private ...
python scripts/candidate_preparation_cli.py register --benchmark source-benchmark.json ...
```

`normalize` validates the published candidate-layout schema before writing anything. Format-specific conversion is outside the skill. Registration is local and does not require publication evidence.
Clean normalization writes only the normalized candidate, fidelity layout extraction, and item inventory. `validate-private` computes the full exact-set QA gate without writing a pass artifact. A fourth, non-empty issues report exists only when normalization found issues and must be dispositioned before registration.

## Locator-packet preparation

```bash
python scripts/page_chunk_cli.py prepare-locator-chunks \
  --state evaluation-state.json \
  --normalized-candidate candidate/candidate-index.json \
  --page-map page-map.json \
  --chunk-manifest chunk-manifest.json \
  --benchmark source-benchmark.json
```

All supplied artifacts must be the exact current files registered in state. The output directory defaults to `locator-packets/` beside the normalized candidate; use `--output-dir` only for another path inside the same canonical evaluation directory. Success writes and registers one `candidate-locator-chunk-v1` file per frozen chunk, completes `locator_chunk_preparation`, and makes `audit-locators` available. A routing exception writes an unregistered `candidate-locator-routing-exceptions-v1` diagnostic instead of packet files and leaves canonical state unchanged. Other validation failures write nothing.

This command uses the local candidate/benchmark binding recorded by `candidate_preparation_cli.py register`. It accepts no publication, repository, branch, commit, pull-request, blob-proof, preparation-receipt, or benchmark-lock input.

## Parallel audit chunks

```bash
python scripts/parallel_candidate_audit_cli.py validate-audits --audit-kind locator ...
python scripts/parallel_candidate_audit_cli.py register-audits --audit-kind locator ...
python scripts/parallel_candidate_audit_cli.py validate-audits --audit-kind missing_access ...
python scripts/parallel_candidate_audit_cli.py register-audits --audit-kind missing_access ...
```

Repeat `--audit` for the selected chunk files. Locator calls pair them with `--locator-packet`. Missing-access calls include the complete registered locator-audit set through repeated `--locator-audit`.
Add `--replace-complete-batch` only when replacing an already registered locator
or missing-access batch. Replacement requires exactly one valid audit per frozen
chunk, completes that audit stage, and invalidates all later stage and artifact
registrations without deleting their files.

Source-discovery chunks use the same local pattern:

```bash
python scripts/parallel_discovery_cli.py validate-discoveries ...
python scripts/parallel_discovery_cli.py register-discoveries ...
```

## Scoring

```bash
python scripts/dimension_score_v8_cli.py register-structure \
  --state evaluation-state.json \
  --input structure-audit.v6.json
python scripts/dimension_score_v8_cli.py score \
  --state evaluation-state.json
python scripts/dimension_score_v8_cli.py build-report \
  --state evaluation-state.json
```

`register-structure` validates the native V6 ledger, its exact candidate denominator, and every adverse heading-access causal finding before registering it. `score` resolves and verifies the registered policy, manifest, candidate, inventory, locator audits, missing-access audits, and structure audit; it then writes and registers calculation input V2, calculations V6, item assessments V7, projection metadata V2, and result V12. `build-report` validates the registered scoring set and writes web report V10. Each successful command advances canonical state under its mutation lock. Validation failure writes no output and leaves state unchanged.

For isolated calculation diagnostics, the lower-level commands remain available:

```bash
python scripts/dimension_score_v8_cli.py preflight --input dimension-calculation-input.json
python scripts/dimension_score_v8_cli.py calculate \
  --input dimension-calculation-input.json \
  --output dimension-calculations.json
python scripts/item_grade_v8_cli.py build-assessments \
  --base-items base-item-assessments.json \
  --calculation dimension-calculations.json \
  --structure-audit structure-audit.json \
  --locator-audit locator-audit.CHUNK-001.v2.json \
  --output item-assessments.json
```

For a frozen V5 structure audit, `item_grade_v8_cli.py project-structure-causality` creates an exact-hash-bound V6 copy that adds only score-free causal metadata.

The calculation input binds `structure_audit` directly; no intermediate structure artifact or derivation command is needed. The canonical `score` command assembles that input from state, so hand-authoring it is unnecessary in a normal run.
