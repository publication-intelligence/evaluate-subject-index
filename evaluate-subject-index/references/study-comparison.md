# Retrospective study binding and comparison

Use `scripts/study_cli.py` when already candidate-visible evaluations must adopt a
reviewed common benchmark, semantic policy, and density basis. This workflow is
explicitly retrospective. It never selects a benchmark, performs fresh discovery
or editorial review, or authorizes transfer of candidate judgments. Ordinary
single-evaluation work does not require a study lock.

The lock is an approved comparison contract, not another canonical evaluation
state. Each evaluation keeps its own `evaluation-state.json`. The current V8.2
policy, rubric, calculation profile, formulas, and publication gates are unchanged.

## Prepare the reviewed inputs

1. Select a release only after the authorized source review. Preserve its exact
   benchmark, review, and review inventory. The command supports any reviewed
   release; release numbers and subject/treatment counts are not selection rules.
2. Validate the actual page map and manifest, including their reconstructed
   identities, source identity, unique locator keys, and exact owned-page coverage.
   All participating evaluations must use that same scope and chunk order.
3. Agree the semantic policy and exact density measurement map. A matching total
   is insufficient. Policy settings include audience, availability, eligible
   regions, exclusions, judgments, and deviations, including their explanations.
   Only identity/freeze/migration wrappers are omitted from the policy fingerprint.
4. Write one `study-benchmark-lock.schema.json` document and a separate
   `retrospective-benchmark-approval.schema.json` document for each candidate.
   The approval records existing explicit authorization and binds that candidate's
   current state bytes, previous policy/benchmark, target lock/release, and target
   semantic policy. Never invent an approval or reviewer identity.

Use `study_cli.py fingerprint --benchmark RELEASE.json --policy POLICY.json` to
obtain semantic identities. Benchmark fingerprinting preserves ordered content,
IDs, evidence, terminology, priorities, relationships, and reader tasks; it only
normalizes legacy relationship `type` to `relationship_type` and removes the
explicit provenance-wrapper allowlist in `study_comparison.py`. Unknown extensions
remain fingerprinted. Identical counts do not prove semantic equality. Different
wrappers can compare when they preserve semantic content and bind the same verified
historical release.

A shared policy reference must be unfrozen. Generate it with:

```sh
python scripts/study_cli.py policy-template --input study-policy-input.json --output study-policy-template.json
```

The input uses the standard policy build fields. This emits
`subject-index-study-policy-template-v1`, with `policy_semantic_content` and a
`template_sha256`; it makes no candidate-blind freeze claim. If adopting that
policy changes semantics, the per-candidate approval must also bind the exact
`study_policy_template_sha256` file bytes. Never ignore differing policy settings
merely to make comparison pass.

## Historical release lineage

The lock's `release.lineage` explicitly selects one review contract:

- `git_freeze`: the actual `artifact_freeze_commit`, plus the release's exact
  `release_descriptor_sha256`. Supply `--release-descriptor`. Its self-hash,
  benchmark identity, release ID, commit, and review-file bindings are verified.
- `native_source_freeze`: exact `source_only_state_sha256`, `draft_file_sha256`,
  `review_file_sha256`, and `review_inventory_file_sha256`. Supply `--release-state`
  and `--release-draft`. The preserved state must have no candidate, no candidate
  normalization, completed source review/freeze registrations, and no active
  candidate-era stages. The native draft-to-review-to-final chain is validated.
  `checkpoint_artifacts` records available transport provenance (it may be empty).
  A ZIP checksum is not a Git commit or a checkpoint-import gate.
- `current_source_freeze`: exact `source_only_state_sha256`, `draft_file_sha256`,
  and `review_file_sha256` from the current typed `benchmark_review_cli.py freeze`
  workflow. Supply `--release-state` and `--release-draft`; omit
  `--release-review-inventory`. The source-only state must register the actual
  typed draft, review, and final and preserve candidate blindness. Validation
  recomputes a temporary standard screening inventory (near-duplicate threshold
  0.93) and runs `validate_final_data`, including the current `approved_changes`
  contract. The inventory is neither copied nor registered. The preserved
  source-only state provides imported discovery provenance; this migration does
  not claim new discovery or review. Optional available transport provenance is
  recorded in `checkpoint_artifacts` (an empty array is valid).

All variants bind the exact original benchmark bytes, its self-hash, ID/version,
semantic fingerprint, source/map/manifest, and reviewed historical evidence. Do
not manufacture a descriptor or Git identity for a native checkpoint lineage.

## Density evidence

Each ordered lock density row includes `chunk_id`, `indexable_source_words`, and
`source_artifact: {path, sha256}`. Paths resolve beside the lock. The
`density_basis.measurement_sha256` hashes the entire ordered array, including its
evidence references. `lock_sha256` hashes the lock without that self-hash field.
Use UTF-8 JSON, sorted keys, compact separators, and unescaped Unicode, as in
`study_comparison.digest`.

A source artifact may be a historical discovery chunk with complete page-review
counts and exact owned pages, or a standalone
`source-density-measurement.schema.json` document. For a standalone measurement,
all density rows can reference the same file. It declares source/map/manifest,
extractor, counting-script and extraction hashes, inclusions/exclusions/token
rules, every owned page count, and every ordered chunk count. Validation recomputes
chunk/overall totals, verifies source labels, and rejects duplicate, missing,
foreign, or reassigned owned pages. It must attest no candidate information used.

The measurement's proposal/review status is preserved. A counter or an embedded
hash is not an editorial approval: the explicitly approved lock selects its exact
bytes. Historical chunks lacking embedded scope IDs remain unchanged; the approved
lock binds their bytes to the separately verified map and manifest. New density
measurement never pretends to be new source discovery.

## Migrate an authorized evaluation

```sh
python scripts/study_cli.py migrate-benchmark \
  --state evaluation/evaluation-state.json \
  --study-lock reviewed/study-benchmark-lock.v1.json \
  --release-benchmark reviewed/benchmark.json \
  --release-review reviewed/review.json \
  --approval reviewed/this-candidate-approval.json \
  --output-dir migration/shared-study
```

For Git or historical native lineage, also pass the preserved
`--release-review-inventory`. Add the other lineage-specific arguments above and
`--study-policy` when an explicitly approved shared policy is needed. The output directory must be new and inside the
evaluation. The command locks state mutation and validates the complete proposed
binding before committing the new canonical state. A failure leaves the prior
state unchanged.

The original state remains beside the current state as
`evaluation-state.before-<approval-hash-prefix>.json`, so its relative paths still
resolve. Original policy and benchmark bytes/freezes remain available as private
historical checkpoint evidence. A changed policy records an actual new
`candidate_seen: true` freeze plus its original and immediately previous freezes.
The selected benchmark preserves historical source-review provenance and explicitly
records that candidate-visible rebinding is not fresh review.

If benchmark or policy semantics change, candidate audit registrations and later
results are invalidated; existing files are preserved. Candidate normalization and
source preparation remain. No old missing-access judgments may be relabeled with
new subject IDs. Independent audit reuse needs its own authorized evidence review;
this command always records `audit_transfer_authorized: false`.

When both semantics are already equal, existing candidate audit registrations stay
bound to their current wrapper. Scores and reports must be rebuilt. A changed
density map also invalidates structure registration. Old report/calibration
receipts registered under initialization are removed from active registration.

## Enforced comparison boundaries

Candidate registration, audit import, structure registration, scoring, report
construction, and checkpoint import run the study preflight when a study binding
is present. Retrospective policy/benchmark markers cannot silently lose their
binding. Structure/scoring/report checks require the exact ordered density map.
Checkpoint import validates in a temporary directory and publishes the imported
directory only on success. Transport checksums remain informational; approved
study artifact/content identities are substantive comparison requirements.

```sh
python scripts/study_cli.py preflight --state first/evaluation-state.json --state second/evaluation-state.json
python scripts/study_cli.py assemble-comparison --state first/evaluation-state.json --state second/evaluation-state.json --output-dir comparison
```

Multi-evaluation preflight and assembly require at least two comparable identities
for a comparison: identical source/scope/map/chunks, semantic benchmark, verified
release lineage, semantic policy/profile, audit mode, rubric/calculation profile,
and density basis/map. Unlocked or stale projections cannot enter a comparison.
Assembly validates public collection bytes and schemas and writes a new directory
atomically. It does not publish or deploy a website.

Generated reports and projection metadata carry `methodology.benchmark` beside
the methodology, including ID/version, wrapper and semantic identities, and the
selected release when present. Website consumers must display benchmark identity
next to methodology; a label such as “V8.2” alone does not establish comparability.

Public comparison identities contain only allowlisted release identity fields.
Checkpoint transport paths and archive hashes remain private provenance and are
omitted entirely. Density evidence is identified by content hashes, without
private paths; its public measurement digest hashes that path-free ordered map.
Source-only state documents are never embedded in public outputs. Public release,
benchmark, density-basis, and chunk labels cannot be absolute POSIX or Windows
paths. The private lock retains the complete original transport metadata.
