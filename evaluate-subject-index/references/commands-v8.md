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

State V6 is the only control inventory.

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

## Locator-packet preparation

```bash
python scripts/page_chunk_cli.py prepare-locator-chunks \
  --state evaluation-state.json \
  --normalized-candidate candidate/candidate-index.json \
  --page-map page-map.json \
  --chunk-manifest chunk-manifest.json \
  --benchmark source-benchmark.json
```

All supplied artifacts must be the exact current files registered in state. The output directory defaults to `locator-packets/` beside the normalized candidate; use `--output-dir` only for another path inside the same canonical evaluation directory. Success writes and registers one `candidate-locator-chunk-v1` file per frozen chunk and one `candidate-locator-routing-exceptions-v1` ledger, completes `locator_chunk_preparation`, and makes `audit-locators` available. Any validation or routing exception leaves canonical state unchanged.

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

The calculation input binds `structure_audit` directly; no intermediate structure artifact or derivation command is needed.
