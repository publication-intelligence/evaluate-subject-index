# Current V8 commands

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

Source-discovery chunks use the same local pattern:

```bash
python scripts/parallel_discovery_cli.py validate-discoveries ...
python scripts/parallel_discovery_cli.py register-discoveries ...
```

## Scoring

```bash
python scripts/dimension_score_v8_cli.py register-structure \
  --state evaluation-state.json \
  --input structure-audit.v5.json
python scripts/dimension_score_v8_cli.py score \
  --state evaluation-state.json
python scripts/dimension_score_v8_cli.py build-report \
  --state evaluation-state.json
```

`register-structure` validates the native V5 ledger and its exact candidate denominator before registering it. `score` resolves and verifies the registered policy, manifest, candidate, inventory, locator audits, missing-access audits, and structure audit; it then writes and registers calculation input V2, calculations V5, item assessments V6, projection metadata V1, and result V10. `build-report` validates the registered scoring set and writes web report V8. Each successful command advances canonical state under its mutation lock. Validation failure writes no output and leaves state unchanged.

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

The calculation input binds `structure_audit` directly; no intermediate structure artifact or derivation command is needed. The canonical `score` command assembles that input from state, so hand-authoring it is unnecessary in a normal run.
