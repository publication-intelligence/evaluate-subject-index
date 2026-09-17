# Explicit V10 evaluation runtime

V10 is implemented for review only. The adopted boundary is the byte-preserved
[decision contract](consequence-policy-v10.md), SHA-256
`f812eae0d09b60a4c1e74b1b6b9e6dd5850e088f9f9bb583152e9559f6ee07a9`.
Do not activate the runtime, select a real lock, freeze an actual access overlay,
migrate/evaluate candidates, or deploy a consumer until coordinated review.

Use `scripts/v10_cli.py TOOL ...`; ordinary entrypoints remain V8.2 and
`v9_cli.py` retains V9 behavior. Runtime selection occurs before workflow imports.
Fresh source discovery still uses the source-only V8.2 workflow. V10's initial
study migration accepts an existing V8 candidate state and preserves its exact
prior bytes. It does not relabel V9 state or old candidate audits.

## Versioned artifacts

| Artifact | V10 identity |
| --- | --- |
| Policy / rubric | subject-index-standard-policy-v10 / subject-index-rubric-v10 |
| Calculation profile | subject-index-dimension-calculation-v9 |
| Policy / state | subject-index-evaluation-policy-v6 / subject-index-evaluation-state-v8 |
| Calculation input / calculation | subject-index-dimension-calculation-input-v4 / subject-index-dimension-calculations-v8 |
| Items / result | subject-index-item-assessments-v9 / subject-index-evaluation-result-v14 |
| Report | subject-index-web-report-v12 |
| Projection / collections | ohfr-v10-canonical-web-projection-v1 / ohfr-v10-web-collection-v1 |
| Study lock / typed binding | subject-index-study-benchmark-lock-v3 / retrospective-study-binding-v3.schema.json |

Artifact version suffixes are sequential schema versions, not rubric names.
V10 inherits V9's exact decimal strings, percentages, operation order, weights,
formulas, caps, density bands and rounding. No five-point aliases are accepted.
Diagnostic representation overlays remain separate from benchmark access overlays;
they cannot create an adjusted score or erase a quality gate.

## Immutable source proof and explicit access delta

`study policy-template --from-source-policy` applies only the enumerated V10
policy identities, exact core register and adopted consequence-policy contract.
All other source-policy fields, including extensions, remain fingerprinted.
The unchanged V9 semantic-equality migration is never widened.

Lock v3 retains `release` as the exact V8.2 base freeze and adds:

- `source_benchmark_semantic_sha256`: preserved base content;
- `benchmark_semantic_sha256`: effective V10 content;
- `benchmark_access.overlay` and `.review`: relative paths plus exact file hashes;
- `benchmark_access.overlay_sha256`, `.effective_benchmark_semantic_sha256`, and
  `.frozen_at`.

The overlay records the preserved source scope, source methodology/policy proof,
base benchmark bytes and independent base review. The author and independent
reviewer both attest candidate blindness. Review binds exact proposal bytes,
every delta ID and before/after population accounting; freeze follows review.
`v10_access.validate_access(lock, base, lock_directory)` verifies this chain and
returns an effective in-memory benchmark without modifying source proof.

Deltas add, update or retire subjects/reader tasks. Every delta names its stable
parent ID, approved clause IDs, reason and preserved evidence. Existing-parent
facets remain unweighted. Updated parents retain their priority and all fields
outside the narrow access-language whitelist. New weighted parents require a
recorded distinct obligation that cannot faithfully be represented as a facet.
Replacement evidence must be declared by that delta and match preserved rows
exactly. Source pages must be backed by those declared rows. Subject facets are
unweighted; task facets name only their parent's required subjects. Facet identity is parent-qualified: historical task facets may retain different
parts of one original task under different parents. IDs cannot repeat within
a parent. Overlay delta IDs remain globally unique.

Populations record each subject ID/priority and each task ID/unit weight. Source
pages, measured words, scope and page map remain fixed. Source scope changes,
new discovery or unsupported evidence require the ordinary earlier-stage path.

Initial migration invalidates every candidate audit and score registration. It
never copies old benchmark-dependent ledgers. The coordinated four-candidate
successor migration requires fresh benchmark-dependent review. Any later reuse
of locator audits needs separately documented validation and authorization;
this CLI provides no automatic audit-transfer shortcut.

## Independent outcomes and public contract

The twelve quality gates use structured registered evidence and deterministic
ownership: direct destinations, specific semantics, scope, grounding fallback,
then qualifying systemic groups. Direct-owned or uncertain items cannot be
subtracted from a group to infer residual spread. No format, delivery,
accessibility or data-profile gates exist. Depth is review-only.

For `GATE-STRUCTURE`, `unparseable` means the delivered index content itself is
nonfunctional after form-neutral normalization/manual confirmation.
`structurally_incomplete` likewise describes the delivered index, not an
incomplete extraction or audit. Unsupported file formats, missing parser support,
OCR failure, inaccessible layout evidence and incomplete inspection are validity
or assessment conditions. The preparation tools never turn those failures into
a candidate-attempt judgment. Record such uncertainty explicitly; do not label
it an empty, incomplete or unparseable delivered index.

`VALIDITY-SOURCE-SPAN` describes mismatched evaluated source identity/span/page
map, never a candidate defect. Registered-input and study preflight reject such
mismatches before authoritative scoring. Candidate scope defects can still
support a quality gate while evaluation validity is valid. Inspectability and
attestation blockers are also separate from quality outcomes.

Result v14, report v12 and the public projection expose:

- `evaluation_validity`: typed status/blockers, never used as a quality gate;
- `gate_assessment`: sufficient or indeterminate, with typed blockers;
- `method_readiness`: `not_ready` if any confirmed core gate, otherwise
  `indeterminate` if validity/assessment is blocked, otherwise `ready`;
- `authoritative_evaluation`: `authoritative`, `indeterminate` or `invalid`;
- `human_release_decision`: `{ "status": "not_recorded" }` in native outputs.

A subsequent human decision is a separately supplied artifact. Validate or copy
it with `v10_cli.py release-decision --result RESULT --decision DECISION
[--output NEW_FILE]`. It binds exact result bytes and the machine-facts hash,
names its author, time and authorization, and acknowledges all triggered gates.
Ordinary approval requires method-ready; `approved_with_deviation` is separate
and leaves every machine outcome intact. Native bundles do not auto-discover or
embed this companion. Consumers display it separately only when supplied and
validated; they must not replace the native readiness field.

## Verification

Synthetic tests cover a nonempty facet overlay through migration, scoring,
report/projection and portable checkpoint; added weighted parents and exact
populations; altered review/source/scope/evidence/facets; strict validity shapes;
direct and systemic gate boundaries; ownership; and immutable human decisions.
The numerical boundary probe compares 78 V9/V10 arithmetic cases independently
of deliberately versioned gate consequences. V8/V9 regressions remain required.
Outcome-matrix fixtures are contract unit examples, not claims that an invalid
source evaluation passed the native pipeline.
