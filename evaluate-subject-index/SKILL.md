---
name: evaluate-subject-index
description: Run a repeatable, source-grounded V8.2 evaluation of a finished subject index, including page mapping, source-first benchmark construction, candidate normalization, locator and missing-access audits, scoring, reporting, checkpoints, and resume.
---

# Evaluate Subject Index

Current methodology: **V8.2**. Read [Consequence policy and targeted migration](references/consequence-policy-v8.2.md); it supersedes older publication-gate language while retaining V8.1 scoring/caps and validity separation. Frozen evaluations require explicit migration and new policy/calculation identities.

Evaluate one finished subject index against its source and a frozen policy. Use the current V8.2 workflow and create current-schema artifacts.

## Explicit V9 cutover

V9 is available through `scripts/v9_cli.py TOOL ...`; existing entrypoints retain V8.2. Read [V9 percentage runtime and migration](references/percentage-runtime-v9.md) when V9 is explicitly selected. V9 changes representation and provenance only. It preserves the reviewed V8.2 source freeze, validates its unchanged state/policy/draft/review/final bytes, and creates separately identified candidate artifacts. Do not relabel or edit source proof, activate an unreviewed runtime, or reuse invalidated candidate audits by copying registrations. This feature does not itself authorize a study cutover.

## Method

1. Map one-based document pages to source page labels. Store labels as strings and require the user to approve chunk boundaries.
2. Freeze the standard V8.2 policy, then discover source subjects before exposing the candidate index to the discovery context.
3. Synthesize, independently review, and freeze the candidate-blind benchmark.
4. Preserve the delivered candidate while mechanically normalizing its complete hierarchy and locator assignments from the published layout contract.
5. Audit locator support by complete heading path, then audit missing access against the frozen benchmark.
6. Build the native exception-oriented structure ledger only after the locator and missing-access ledgers are complete. Bind its exact node, cross-reference, and locator-bearing-path denominators; omit attested passes; record exceptions, architecture decisions, defects, strengths, and uncertainties.
7. Calculate the six V8 dimensions from validated ledgers. Do not ask a model to maintain arithmetic or workflow state.
8. Produce structured JSON, `web-report.v10.json`, and its canonical public web projection bundle.

Use [standard-policy-v8.md](references/standard-policy-v8.md), [judgment-policy-v8.md](references/judgment-policy-v8.md), and [rubric-v8.md](references/rubric-v8.md) for substantive decisions. Default to a full audit. A pilot may calibrate the method but cannot support full-index claims.

## Current command surface

- `scripts/state_cli.py`: initialize, inspect, validate, and advance the single canonical state.
- `scripts/page_chunk_cli.py`: page mapping, source chunking, and registered-state locator-packet preparation.
- `scripts/policy_cli.py`: instantiate the standard policy.
- `scripts/parallel_discovery_cli.py`: validate and register source-discovery chunks.
- `scripts/benchmark_review_cli.py`: temporary benchmark screening, typed review/freeze, and the narrow reviewed-legacy compatibility import.
- `scripts/candidate_preparation_cli.py`: validate the published candidate-layout contract, then normalize and locally register candidate preparation.
- `scripts/parallel_candidate_audit_cli.py`: validate or register locator and missing-access chunks created in separate chats.
- `scripts/dimension_score_v8_cli.py`: typed structure registration, canonical-state input assembly, deterministic V8 scoring, and web-report projection; low-level preflight and calculation remain available for diagnostics.
- `scripts/item_grade_v8_cli.py`: low-level current item-projection validation.
- `scripts/bundle_cli.py`: optional checkpoints, artifact listing, and resume imports.
- `scripts/study_cli.py`: explicitly authorized retrospective study binding, comparison preflight, and comparison bundle assembly.

## State and artifacts

`evaluation-state.json` is the single source of truth. It contains the stage statuses and artifact inventory. Do not create or maintain a second manifest.

Artifact SHA-256 values are stable content labels used to join related JSON records. They are not security attestations. State validation reports missing or changed local artifact bytes as warnings; it does not block resume merely because a previously recorded checksum differs.

Keep source and candidate files restricted. Keep public reports free of source text, secrets, absolute paths, and storage-provider identifiers.

## Checkpoints and resume

Create checkpoints at useful milestones and before a likely conversation or network boundary. Checkpointing is a durability feature, not a mandatory stage gate.

A checkpoint contains the canonical state plus accessible registered artifacts. Portable checkpoints omit restricted files. Import validates archive path safety, member inventory, and the current state shape, but does not require an old archive hash or member hashes to match. After import, reconnect unavailable restricted inputs explicitly and continue from `state_cli.py next`.

Read [storage-and-checkpoints.md](references/storage-and-checkpoints.md) before checkpointing or resuming.

An already frozen, independently reviewed candidate-blind benchmark may bypass repeated discovery and full editorial review only through `benchmark_review_cli.py import-reviewed-legacy`. Read [benchmark-review.md](references/benchmark-review.md) first. The command requires exact legacy release evidence plus a separate current-schema compatibility approval, permits only its enumerated mechanical normalization and policy/release rebinding, and records explicitly that the four imported stages were not rerun. Never author the compatibility approval on the reviewer's behalf.

For authorized comparison of already candidate-visible evaluations, read [Retrospective study binding and comparison](references/study-comparison.md). Preserve both historical freezes and actual candidate visibility; a reviewed release and approved common policy/density lock are required before binding or assembling comparable outputs. This workflow does not select a release or authorize audit transfer.

## Parallel chats

Parallel work is divided by deterministic chunk ownership. Workers return complete current-schema JSON artifacts. The coordinator validates the selected files together and registers them in the single state.

Branches, pull requests, and chat attachments may be used for transport or review, but GitHub receipts, blob proofs, merge evidence, recovery receipts, and matching checkpoint hashes are not prerequisites for canonical registration. Registration completes an audit stage only when every frozen chunk denominator is covered exactly once.

Candidate preparation is mechanical and benchmark-blind. Candidate input must match [candidate-layout-extraction.schema.json](references/schemas/candidate-layout-extraction.schema.json); convert it before invoking the skill if necessary. Then run `normalize`, disposition the optional non-empty issues report if one was created, run computed `validate-private`, and `register`. Clean preparation permanently registers only the normalized candidate, fidelity layout extraction, and currently required item inventory. It does not require a publication workflow.

After local registration, run `page_chunk_cli.py prepare-locator-chunks` with the canonical state and its registered normalized candidate, page map, chunk manifest, and frozen benchmark. The registered candidate-to-benchmark binding in `evaluation-state.json` is sufficient. Successful preparation writes and registers one frozen packet per manifest chunk, then completes `locator_chunk_preparation`. Routing exceptions write an unregistered diagnostic and leave state unchanged.

Read [candidate-preparation.md](references/candidate-preparation.md) and [parallel-candidate-audits.md](references/parallel-candidate-audits.md).

## Scoring

Native V8 uses evaluation-policy V4, state V6, `structure-audit-v6`, `locator-audit-v2`, calculation input V2, dimension calculations V6, item assessments V7, result V12, projection metadata V2, and web report V10. Every adverse heading-access judgment carries source-linked causal findings, which are reporting provenance and never arithmetic inputs. Every locator audit states `complete_path_fit` directly. Page treatment and complete-path fit remain independent diagnostics combined with `min(T,F)` for the displayed locator grade only. Page-reference Reliability uses binary keep precision: `supported` means keep unchanged and receives 1; `partially_supported` and `unsupported` receive 0. Diagnostic item grades are not a seventh dimension and do not replace the dimension calculation.

For an authorized retrospective migration, use the schema-defined `retrospective_migration` policy/build-input field and `policy_cli.py build --original-policy`; add `--base-policy` for provenance-only cleanup of a finished V8.2 migration. Read the [migration contract](references/consequence-policy-v8.2.md#retrospective-policy-provenance-contract) first. The current freeze records actual migration visibility; the original candidate-blind freeze and original review/release evidence remain separate preserved provenance. This does not authorize or claim fresh discovery, review, or approval.

Complete the final stages with `dimension_score_v8_cli.py register-structure`, `score`, and `build-report`. These commands select exact registered current artifacts from canonical state, validate their bytes and bindings, write current-schema outputs, and advance state atomically. Do not complete these stages with generic `state_cli.py set-stage`.

`build-report` is the standard final reporting action. From finalized registered artifacts only, it writes and registers `web-report.v10.json`, `v8-canonical-projection/projection.v1.json`, and the `data/index-records.v1.json`, `data/source-subjects.v1.json`, and `data/density.v1.json` collections. It includes `data/correction-overlay.v1.json` only when one confirmed, self-hashed correction overlay is already registered and bound to the evaluation. With no applicable overlay, omit the file and use the established `correction_outcomes` non-applicability shape. Read [json-contracts-v8.md](references/json-contracts-v8.md) before consuming or adapting the bundle.

## Output contract

Prefer JSON artifacts and concise JSON responses:

```json
{
  "command": "status",
  "ok": true,
  "evaluation_id": "example",
  "state": "source_subject_discovery",
  "artifacts_written": [],
  "next_actions": [],
  "warnings": []
}
```

Represent `not_measured`, `uninspectable`, and `uncertain` explicitly rather than converting them to failures or zeros. Compare independent evaluations only when their source, benchmark, page map, chunks, policy, audit mode, rubric, and calculation-profile identities match.

## References

- [workflow.md](references/workflow.md)
- [storage-and-checkpoints.md](references/storage-and-checkpoints.md)
- [candidate-preparation.md](references/candidate-preparation.md)
- [parallel-candidate-audits.md](references/parallel-candidate-audits.md)
- [benchmark-review.md](references/benchmark-review.md)
- [page-mapping-and-chunks.md](references/page-mapping-and-chunks.md)
- [structure-audit-v8.md](references/structure-audit-v8.md)
- [customer-methodology-v8.md](references/customer-methodology-v8.md)
- [json-contracts-v8.md](references/json-contracts-v8.md)
