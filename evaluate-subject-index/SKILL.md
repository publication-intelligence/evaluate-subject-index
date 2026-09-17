---
name: evaluate-subject-index
description: Run repeatable, source-grounded V10 evaluations of finished subject indexes, including benchmark discovery or reconciliation, candidate audits, scoring, comparison, reporting, checkpoints, and study closeout.
---

# Evaluate Subject Index

Use **V10 only** through `scripts/v10_cli.py`. Historical artifacts may be read as evidence, but all current state, policy, benchmark binding, candidate audit, scoring, reporting, and comparison work must use V10 identities and contracts.

## Benchmark discovery and confirmation gate

Before source-subject discovery, benchmark synthesis or migration, or candidate inspection:

1. Search the current evaluation directory and repository, every relevant `evaluation-state.json`, sibling repositories and worktrees, study locks, reviewed releases, checkpoints, and accessible remote branches or releases. Search by schema identity, benchmark ID, source hash, title, edition, and page-map identity rather than filename alone.
2. Record the searched locations and every plausible benchmark, review ledger, release, and lock. Validate identity and review status before recommending anything.
3. Present the valid benchmark choices and evidence to the user and explicitly ask which benchmark to use. Wait for confirmation before binding a benchmark or beginning candidate evaluation.
4. If several benchmarks exist, recommend source-first, candidate-blind reconciliation when appropriate, but do not reconcile or create a successor until the user confirms that direction.
5. If none is found, explicitly ask whether a benchmark exists elsewhere that the workflow should know about. Wait for the answer. Create a new candidate-blind benchmark only after the user confirms that no existing benchmark should be used, and preserve that confirmation in the workpapers.

Never silently choose a benchmark, create a duplicate, or expose candidate output or scores to benchmark discovery, reconciliation, synthesis, or review.

## Method

1. Initialize one V10 state and map one-based document pages to source page labels. Store labels as strings and obtain approval for chunk boundaries.
2. Freeze the V10 policy and source scope.
3. Complete the benchmark discovery and confirmation gate. Reuse, reconcile, or, only after confirmation, synthesize and independently review one candidate-blind benchmark.
4. Freeze one V10 benchmark release and create one shared execution kit containing its source, page map, chunks, policy, semantic fingerprint, study lock, runtime revision and payload, comparison compatibility receipt, density evidence, and a manifest of their exact file hashes. Distribute those exact common bytes to every candidate; candidate workers must not regenerate equivalent-looking locks, policies, density evidence, or compatibility receipts.
5. Preserve the delivered candidate while mechanically normalizing its complete hierarchy and locator assignments.
6. Audit every locator against the complete delivered heading path, then audit missing access against the frozen benchmark.
7. Build the exception-oriented structure ledger after locator and missing-access audits are complete. Bind exact denominators and record exceptions, architecture decisions, defects, strengths, and real uncertainties.
8. As soon as two candidates have adopted the shared execution kit, run a multi-state study preflight; repeat it with every candidate before scoring. Register benchmark-access review, calculate the six V10 dimensions deterministically, build the V10 report and canonical public projection, and run the final all-candidate preflight before comparison assembly.

Default to a full audit. A pilot may calibrate the method but cannot support full-index claims.

## V10 command surface

Use `scripts/v10_cli.py TOOL ...` for every user-facing operation:

- `state`: initialize, inspect, validate, and advance canonical state.
- `policy`: construct the V10 policy.
- `page-chunks`: page mapping, chunking, and locator-packet preparation.
- `discover-source`: validate and register source-discovery chunks.
- `benchmark`: review and freeze the user-confirmed benchmark.
- `prepare-candidate`: normalize and register the delivered candidate.
- `audit-candidate`: validate and register locator and missing-access audits.
- `access-review`: register V10 benchmark-access review.
- `score`: register structure, calculate, and build the report/projection.
- `grade`: validate diagnostic item projections.
- `study`: bind, preflight, and assemble comparable evaluations.
- `bundle`: create or import checkpoints.
- `release-decision`: validate separately authorized human release decisions.

Treat the underlying modules as implementation details. Do not invoke legacy wrappers or low-level scripts as an alternative workflow.

## State and artifacts

`evaluation-state.json` is the single source of truth. It contains the stage statuses and artifact inventory. Do not create or maintain a second manifest.

Artifact SHA-256 values are stable content labels used to join related JSON records. They are not security attestations. State validation reports missing or changed local artifact bytes as warnings; it does not block resume merely because a previously recorded checksum differs.

That resume tolerance does not apply at study closeout. Before publishing, archiving, or cleaning a worktree, require every registered artifact to exist and match its recorded raw SHA-256. Treat coordination notes and delegated workset paths separately from the registered artifact inventory. Resolve any registered mismatch by restoring the recorded bytes or by an explicit correction that revalidates every dependent result; never silently rewrite a frozen artifact binding.

Keep source and candidate files restricted. Keep public reports free of source text, secrets, absolute paths, and storage-provider identifiers.

## Checkpoints and resume

Create checkpoints at useful milestones and before a likely conversation or network boundary. Checkpointing is a durability feature, not a mandatory stage gate.

A checkpoint contains the canonical state plus accessible registered artifacts. Portable checkpoints omit restricted files. Import validates archive path safety, member inventory, and the current state shape. After import, reconnect unavailable restricted inputs explicitly and continue from `v10_cli.py state next`.

Read [storage-and-checkpoints.md](references/storage-and-checkpoints.md) before checkpointing or resuming.

For authorized comparison of already candidate-visible evaluations, read [Retrospective study binding and comparison](references/study-comparison.md). Preserve both historical freezes and actual candidate visibility; a reviewed release and approved common policy/density lock are required before binding or assembling comparable outputs. This workflow does not select a release or authorize audit transfer.

For benchmark reconciliation, multi-candidate finalization, artifact preservation, and repository closeout, read [Benchmark reconciliation and study closeout](references/benchmark-reconciliation-and-closeout.md). A numeric comparative study is not complete while a required candidate remains indeterminate; inspect and resolve every defensible blocker before assembly, and escalate genuinely irreducible uncertainty for a reviewed method decision rather than silently coercing it.

## Parallel chats

Parallel work is divided by deterministic chunk ownership. Workers return complete current-schema JSON artifacts. The coordinator validates the selected files together and registers them in the single state.

For a multi-candidate study, the coordinator owns the shared execution kit and gives every candidate worker its exact manifest and hashes. A worker may author its candidate-specific approval and migrated state, but must not create a new common lock, policy template, density file, compatibility receipt, or runtime selection. Every handoff reports the canonical state path, runtime payload, lock file and semantic hashes, compatibility semantic, score, gates, validity/sufficiency, and final report/projection hashes. A mismatch stops the fan-out before additional scoring.

If the evaluator runtime, semantic policy, benchmark, density map, or consequence contract changes after fan-out, stop every candidate at the same boundary. Rebuild the shared kit once, migrate all candidates to it, and rerun the all-candidate preflight. Do not let candidates independently select the latest revision or mix results from before and after the change.

Branches, pull requests, and chat attachments may be used for transport or review, but GitHub receipts, blob proofs, merge evidence, recovery receipts, and matching checkpoint hashes are not prerequisites for canonical registration. Registration completes an audit stage only when every frozen chunk denominator is covered exactly once.

Candidate preparation is mechanical and benchmark-blind. Candidate input must match [candidate-layout-extraction.schema.json](references/schemas/candidate-layout-extraction.schema.json); convert it before invoking the skill if necessary. Then run `normalize`, disposition the optional non-empty issues report if one was created, run computed `validate-private`, and `register`. Clean preparation permanently registers only the normalized candidate, fidelity layout extraction, and currently required item inventory. It does not require a publication workflow.

After local registration, run `v10_cli.py page-chunks prepare-locator-chunks` with the canonical state and its registered normalized candidate, page map, chunk manifest, and frozen benchmark. The registered candidate-to-benchmark binding in `evaluation-state.json` is sufficient. Successful preparation writes and registers one frozen packet per manifest chunk, then completes `locator_chunk_preparation`. Routing exceptions write an unregistered diagnostic and leave state unchanged.

Read [candidate-preparation.md](references/candidate-preparation.md) and [parallel-candidate-audits.md](references/parallel-candidate-audits.md).

## V10 scoring

Use [V10.2 decision contract](references/consequence-policy-v10.2.md) and [V10 semantic execution contract](references/runtime-v10-semantic.md). Keep score deductions, dimension ceilings, quality gates, validity, assessment sufficiency, and human release decisions separate. V10.2 has no overall-score ceiling.

Inspect the exact source and full delivered candidate path before leaving an axis unresolved. When the source is available but the candidate path, locator, or reference is malformed, incomplete, polysemous, or under-specified, judge the candidate as delivered. If the candidate’s intended concept cannot be known, treat that as a severe candidate failure: do not invent intent or convert the defect into neutral uncertainty. Record known `no_fit`, `unsupported`, and `not_kept` outcomes where applicable, and apply every qualifying cap or gate without double counting.

Reserve uncertainty for source facts that genuinely remain unavailable or unresolved after inspection. Apply singleton-domain and known-nonkeep rules first. A comparative study requiring numeric results is not complete while a required candidate remains indeterminate.

Complete final stages with `v10_cli.py score register-structure`, `score`, and `build-report`. These commands validate exact registered artifacts, advance state atomically, and produce the V10 report and canonical projection. Do not complete typed stages with generic state mutation.

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

- [V10.2 decision contract](references/consequence-policy-v10.2.md)
- [V10 runtime](references/runtime-v10.md)
- [V10 semantic execution contract](references/runtime-v10-semantic.md)
- [Benchmark review](references/benchmark-review.md)
- [Benchmark reconciliation and study closeout](references/benchmark-reconciliation-and-closeout.md)
- [Study comparison](references/study-comparison.md)
- [Workflow](references/workflow.md)
- [Storage and checkpoints](references/storage-and-checkpoints.md)
- [Candidate preparation](references/candidate-preparation.md)
- [Parallel candidate audits](references/parallel-candidate-audits.md)
- [Page mapping and chunks](references/page-mapping-and-chunks.md)
