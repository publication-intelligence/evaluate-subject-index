# Benchmark reconciliation and study closeout

Use this workflow when reconciling reviewed benchmarks, running a multi-candidate study, or closing a study whose private workpapers must survive disposable worktrees.

## Freeze and reconcile before candidate evaluation

Freeze the source, page map, policy, chunks, runtime, and one benchmark release before candidate audit work begins. Track these identities separately: raw file SHA-256, schema self/content hash, semantic fingerprint, study lock, runtime revision and payload, and comparison compatibility identifier. Never substitute one for another.

When more than one reviewed benchmark exists, reconcile them against the source without candidate outputs or candidate scores. Treat neither release as the default winner. Build a semantic crosswalk, review additions, retirements, merges, splits, facets, reader tasks, and weights, and record every decision in a change ledger. “Best of both” means source-grounded synthesis followed by independent review; it never means unioning the releases mechanically.

Bind every candidate to the same frozen source, map, chunks, policy, benchmark, rubric, calculation profile, density lock, and compatible runtime. Preflight must reject mixed semantics before scoring.

Create those common inputs once as a shared execution kit. Its manifest records the exact relative path and raw SHA-256 of the release, draft, review, policy template, study lock, density evidence, runtime revision/payload, schema bundle, and compatibility receipt, plus their declared semantic identities. Copy the same bytes into each candidate evaluation. Only the candidate-specific retrospective approval and resulting state may differ. An independently regenerated lock or receipt is a different study input even when its human-readable settings appear equal.

After the first two migrations, run one multi-state preflight as an early fan-out check. Add every remaining candidate to that check before scoring begins. If a runtime or contract correction lands during the study, pause all candidates, issue one successor kit, migrate them together, and preflight the complete set again. Record the superseded kit; never let each candidate choose or rebuild its own successor identity.

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

Build the consumer handoff from the assembled comparison rather than copying candidate files by hand. Preserve the comparison order, import atomically, regenerate any deterministic compressed/materialized forms, update the consumer's declared hashes, and verify both artifact materialization and focused consumer tests. Website deployment is a separate authorized action.

## Preserve private workpapers and close the study

Before cleaning worktrees, audit every relevant checkout for untracked, ignored, and modified files. Preserve source-bearing packets, detailed ledgers, correction notes, checkpoints, and modified-file patches in a private content-addressed archive with a manifest and SHA-256 sidecar. Keep source text and restricted candidate evidence out of public repositories and public bundles.

Classify every dirty path before committing: canonical nonrestricted evidence required by the current state, private/source-bearing workpaper, reproducible scratch output, or obsolete duplicate. Commit required nonrestricted state dependencies to their owning repository. Archive private workpapers and tracked-file patches locally. Leave reproducible scratch and obsolete duplicates out of Git after recording their disposition. Inspect ignored files as well as ordinary `git status`, and scan staged objects for repository-host size limits before pushing.

Run a byte-integrity sweep over the canonical state's registered artifact inventory before closeout. Every registered path must exist and its raw SHA-256 must match the state record, including restricted artifacts that will only enter the private archive. Do not treat a missing delegated workset or an obsolete coordination path as a registered-artifact failure; report those separately. If a registered artifact is missing or changed, restore the recorded bytes when available. Otherwise preserve the state and available bytes, write an explicit audit addendum, and either issue a reviewed correction that revalidates downstream scoring and reporting or leave the study marked incomplete. Never update a frozen hash merely to make validation pass.

Use a finalization matrix with one row per repository: owning repository, branch/head, canonical state path, registered-artifact existence and hash result, coordination-path exceptions, private artifacts archived, score and gates, shared-kit hashes, validation result, pull request, and merge commit. A local commit, pushed branch, open pull request, and merged pull request are distinct states; verify the remote merge rather than inferring it from the local branch.

Record the branch, pull request, merge commit, final score, gates, readiness, artifact identities, and validation result for each candidate. Confirm that all intended commits reached the correct repository, that superseded branches or duplicate documents were closed or removed, and that the consumer was rebuilt from the merged candidate artifacts. Deployment remains a separate action.
