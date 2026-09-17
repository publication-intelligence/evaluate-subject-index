# Benchmark reconciliation and study closeout

Use this workflow when reconciling reviewed benchmarks, running a multi-candidate study, or closing a study whose private workpapers must survive disposable worktrees.

## Freeze and reconcile before candidate evaluation

Freeze the source, page map, policy, chunks, runtime, and one benchmark release before candidate audit work begins. Track these identities separately: raw file SHA-256, schema self/content hash, semantic fingerprint, study lock, runtime revision and payload, and comparison compatibility identifier. Never substitute one for another.

When more than one reviewed benchmark exists, reconcile them against the source without candidate outputs or candidate scores. Treat neither release as the default winner. Build a semantic crosswalk, review additions, retirements, merges, splits, facets, reader tasks, and weights, and record every decision in a change ledger. “Best of both” means source-grounded synthesis followed by independent review; it never means unioning the releases mechanically.

Bind every candidate to the same frozen source, map, chunks, policy, benchmark, rubric, calculation profile, density lock, and compatible runtime. Preflight must reject mixed semantics before scoring.

For retrospective migrations, preserve the historical freezes and the actual `candidate_seen` history. Never reset visibility or describe migrated work as a fresh blind review.

## Resolve uncertainty before a final comparative study

Before declaring a candidate complete, inventory every score, gate, validity, access-review, and architecture blocker. Inspect the exact source and full delivered candidate path. Preserve genuinely unknown source facts and never fill them by guesswork.

Candidate ambiguity is different from missing evidence. When the complete source was inspected and the delivered path, locator, or reference is malformed, semantically incomplete, polysemous, or under-specified, do not invent the candidate’s intended concept. Judge the delivered route as delivered. If a reasonable reader cannot identify one supported complete concept at the cited passage, record a known candidate retrieval failure (`no_fit`, `unsupported`, and `not_kept` where those axes apply). Use a lesser fit only when the passage visibly supports a bounded part of the complete path. Resolve dependent access, task, reference, and architecture outcomes from the usability of the delivered route rather than relabeling the candidate defect as semantic uncertainty.

Apply singleton-domain and known-nonkeep rules before leaving an axis unresolved. A domain forced to one value is known. When every permitted subtype is nonkeep, preserve subtype uncertainty while recording keep as known nonkeep.

Do not coerce genuinely unavailable or source-ambiguous evidence. If the study objective requires ranked numeric results, stop comparison assembly and escalate the remaining irreducible cases for a reviewed methodology decision. Do not publish a partly ranked study as final.

## Assemble and verify the comparison

Assemble the comparison only after every required member passes its final study contract. Validate each lineage and public bundle once, write output atomically, and avoid repeated full validation inside per-file loops.

Public consumers must represent nullable or indeterminate results correctly, but that fallback does not satisfy an explicitly numeric study objective. Confirm projection and report hashes using their declared content/self-hash rules; those values may intentionally differ from raw file hashes.

Keep evaluator methodology in the evaluator repository, frozen benchmark artifacts in the benchmark repository, candidate-specific evidence and results in candidate repositories, and adapters plus public comparison bundles in the website repository.

## Preserve private workpapers and close the study

Before cleaning worktrees, audit every relevant checkout for untracked, ignored, and modified files. Preserve source-bearing packets, detailed ledgers, correction notes, checkpoints, and modified-file patches in a private content-addressed archive with a manifest and SHA-256 sidecar. Keep source text and restricted candidate evidence out of public repositories and public bundles.

Record the branch, pull request, merge commit, final score, gates, readiness, artifact identities, and validation result for each candidate. Confirm that all intended commits reached the correct repository, that superseded branches or duplicate documents were closed or removed, and that the consumer was rebuilt from the merged candidate artifacts. Deployment remains a separate action.
