# Independent benchmark review

The source benchmark has three distinct states: synthesized draft, independently reviewed benchmark, and final frozen benchmark. Never describe a synthesis draft as frozen.

## Required sequence

1. `synthesize-source-benchmark` reconciles every validated chunk into `source-benchmark.draft.vN.json` while the candidate remains unseen.
2. Review opens the draft in a fresh, candidate-blind context, reconnects the exact source by SHA-256, uses a deterministic `source-benchmark-review-inventory.json` as a temporary queue, and records an item-complete editorial ledger in `source-benchmark-review.vN.json`.
3. `benchmark_review_cli.py freeze` validates the exact registered draft, recomputed inventory, review ledger, and approved final benchmark, then atomically registers the review and final benchmark while completing both state stages.

Candidate evaluation and canonical registration cannot begin until all three stages are complete. An isolated worker may mechanically prepare a candidate after the frozen source-level identities exist, but no candidate material may enter this review context or influence benchmark review. Read [candidate-preparation.md](candidate-preparation.md).

## Full and pilot review

Full evaluation is the default. A full review must cover every subject, relationship, and reader task by stable ID; revisit every cross-chapter subject; disposition every unresolved relationship; and independently inspect every fallback-generated reader task. It must also perform a fresh source-first omission pass, confirm candidate blindness, and resolve all blocking structural defects. The review ledger must enumerate the exact IDs reviewed, not merely report counts.

Pilot review may use a declared sample, but it cannot approve a final freeze or support full-evaluation or public completeness claims. Its ledger must set `public_claims_allowed` to `false`.

## Editorial questions

Review subjects for substantive treatment, meaning and stance, priority, boundaries, aliases, acceptable access, chapter provenance, evidence sufficiency, and duplication. Review relationships for direction, type, and resolvability. Review reader tasks for scholarly usefulness, answerability, subject linkage, and faithful access language. Search independently for omitted central arguments, processes, institutions, groups, places, events, historiographical distinctions, causes, consequences, and conclusions.

The deterministic screen identifies duplicate and near-duplicate labels, cross-chapter concepts, unresolved relationships, fallback tasks, missing task coverage, invalid targets, missing required fields, and unusual distributions. These are review queues and warnings, never automatic editorial decisions or subject-count quotas. Density does not determine benchmark size or priority.

## Independence and revision

For full review, use a fresh context that has not seen any candidate index. The reviewer may inspect the source, policy, chunk artifacts, and draft. Record the exact source hash reconnected and attest that the candidate remained unseen.

Every semantic change belongs in `approved_changes`, using the affected stable entity ID, action, and exact changed top-level fields for updates. Merges and splits are represented by their stable-ID additions, removals, and updates. `retain_draft` requires an empty change ledger and preserves the draft content and version. `approve_revised` requires an exact, nonempty change ledger and an incremented version. `revise_before_freeze` and `blocked` prohibit freezing.

The draft reference carries one selected-artifact SHA-256. The screen inventory is recomputed during freeze and is not registered in canonical state. The final benchmark retains its recomputable `benchmark_sha256` identity.

Use:

```bash
python scripts/benchmark_review_cli.py screen \
  --draft source/source-benchmark.draft.v1.json \
  --output validation/source-benchmark-review-inventory.json

python scripts/benchmark_review_cli.py validate-review \
  --draft source/source-benchmark.draft.v1.json \
  --inventory validation/source-benchmark-review-inventory.json \
  --review validation/source-benchmark-review.v1.json

python scripts/benchmark_review_cli.py freeze \
  --state evaluation-state.json \
  --draft source/source-benchmark.draft.v1.json \
  --inventory validation/source-benchmark-review-inventory.json \
  --review validation/source-benchmark-review.v1.json \
  --final source/source-benchmark.v1.json
```

Do not complete `benchmark_review` or `benchmark_freeze` with `state_cli.py set-stage`; the typed freeze command is the canonical transition. Any validation failure leaves state and the supplied artifacts unchanged.
