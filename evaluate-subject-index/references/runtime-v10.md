# V10 evaluation runtime

V10 is the only operational evaluation runtime. The active boundary is the
[V10.1 decision contract](consequence-policy-v10.1.md), identity
`subject-index-evaluation-v10-decision-v2`, SHA-256
`058399c34c0a6997965b39fb5906bde3634c2cdd74d3192bdfd6b4e55452512f`.
The earlier [V10 decision v1](consequence-policy-v10.md) remains historical.
Use `scripts/v10_cli.py TOOL ...` for new source discovery, policy creation,
benchmark review, candidate audit, scoring, reporting, and study comparison.
New evaluations start directly with V10-native state and policy. Historical
schema readers exist only to validate already frozen evidence; they are not an
alternative workflow.

## Versioned artifacts

| Artifact | V10 identity |
| --- | --- |
| Policy / rubric | subject-index-standard-policy-v10 / subject-index-rubric-v10 |
| Calculation profile | subject-index-dimension-calculation-v9 |
| Policy / state | subject-index-evaluation-policy-v7 / subject-index-evaluation-state-v9 |
| Calculation input / calculation | subject-index-dimension-calculation-input-v5 / subject-index-dimension-calculations-v9 |
| Items / result | subject-index-item-assessments-v10 / subject-index-evaluation-result-v15 |
| Report | subject-index-web-report-v13 |
| Projection / collections | ohfr-v10-canonical-web-projection-v2 / ohfr-v10-web-collection-v2 |
| Study lock / typed binding | subject-index-study-benchmark-lock-v3 / retrospective-study-binding-v3.schema.json |

Artifact version suffixes are sequential schema versions, not rubric names.
V10 inherits V9's exact decimal strings, percentages, operation order, weights,
formulas, dimension caps, density bands and rounding. V10.1 adds deterministic
overall ceilings after ordinary dimension arithmetic. No five-point aliases are accepted.
Diagnostic representation overlays remain separate from benchmark access amendments;
they cannot create an adjusted score or erase a quality gate.

## Immutable source proof and explicit access delta

`study policy-template --from-source-policy` applies only the enumerated V10
policy identities, exact core register and adopted consequence-policy contract.
All other source-policy fields, including extensions, remain fingerprinted.
The unchanged V9 semantic-equality migration is never widened.

The older schema identifier `subject-index-benchmark-access-overlay-v10` and
lock fields such as `benchmark_access.overlay` and `overlay_sha256` remain stable
technical identifiers. Human-facing text calls this a benchmark-access amendment;
“representation-correction overlay” refers only to candidate display corrections.

Lock v3 retains `release` as the exact original reviewed freeze and adds:

- `source_benchmark_semantic_sha256`: preserved base content;
- `benchmark_semantic_sha256`: effective V10 content;
- `benchmark_access.overlay` and `.review`: relative paths plus exact file hashes;
- `benchmark_access.overlay_sha256`, `.effective_benchmark_semantic_sha256`, and
  `.frozen_at`.

The benchmark-access amendment records the preserved source scope, source methodology/policy proof,
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
a parent. Amendment delta IDs remain globally unique.

Populations record each subject ID/priority, task ID/unit weight, deterministically
derived expected treatment, and weighted access obligation. Their before/after
reconciliation is exact; reductions greater than 15% require reviewed explanation. Source
pages, measured words, scope and page map remain fixed. Source scope changes,
new discovery or unsupported evidence require the ordinary earlier-stage path.

Initial migration invalidates every candidate audit and score registration. It
never copies old benchmark-dependent ledgers. The coordinated four-candidate
successor migration requires fresh benchmark-dependent review. Any later reuse
of locator audits needs separately documented validation and authorization;
this CLI provides no automatic audit-transfer shortcut.

Migration from a completed V10 evaluation requires a new execution-compatibility
adoption. Preserve the previous state and structure bytes. If the candidate hash
is unchanged and the prior structure contains major or critical findings, pass a
reviewed `subject-index-prior-defect-reconciliation-v10-v1` artifact to `adopt`
with `--defect-reconciliation`. Rebuild the access amendment with the four-family
denominator ledger, rerun affected missing-access and structure judgments, then
rescore and rebuild reports; existing scores are not relabeled.

Coherent first-lookup access, prior-finding dispositions, destructive node-to-path
bindings, stance/relationship findings, and dominant-route concept support require
human re-adjudication. After those facts are frozen, ceiling application and public
projection are mechanical.

## Required factual candidate review

V10 enforces a separate private factual receipt through
`v10_cli.py access-review --state STATE --input RECEIPT`. Register it after
missing-access audits and before structure registration. The receipt binds the
exact proposed structure bytes; subsequent scoring requires that file to be the
registered structure audit. This is a V10 study requirement, not a change to the
generic V8/V9 missing-access audit schemas.

The exact review set includes every parent-qualified facet, scope rule and
retained distinction, plus every non-retirement amendment delta. Term aliases,
acceptable access, task questions and newly added parents therefore require
review even when there are no nested facets. Each record binds requirement
content, concrete candidate paths, known evidence IDs, relevant structure
findings, reviewer identity and the resulting registered parent judgment. The
receipt also binds the candidate, effective benchmark, amendment, study lock,
and complete registered missing-access audit file set.

Review completion (`reviewed` or `unresolved`) is separate from factual outcome
(`satisfied`, `partially_satisfied`, `not_satisfied`, `uninspectable`). The reviewer
names the existing parent judgment fields actually assessed: subject coverage,
stance preservation or first-lookup success, or reader-task result. A confirmed
partial/unsatisfied outcome cannot be paired with a fully positive value in
those declared fields. This check never turns a failed alternative route into
coverage loss automatically. All-satisfied does not force a positive parent
judgment; no facet count, minimum or sum determines a score. Claimed fidelity or
navigation findings require relevant bound structure evidence.

Missing/stale/foreign/duplicate requirements and inconsistent bindings block
structure registration/scoring. Unresolved/uninspectable review produces
`GATE-ASSESSMENT-ACCESS-REVIEW` with explicit parent/path/node/linked-defect scope;
that uncertain evidence cannot support quality gates. It does not invent a
negative parent judgment. Recorded expert judgments remain inputs to the
unchanged formulas. Resolve or revise a frozen receipt through ordinary audit
invalidation and a new review, preserving the old evidence.

The result's study identity contains per-candidate `candidate_access_review`:
`receipt_file_sha256` (or null when no requirements exist), `status`, and
`requirement_count`. Its hash also participates in scoring artifact input
bindings. Receipt hashes differ across candidates and are not a common-benchmark
comparison criterion. Authoritative V10 scoring/reporting always validates the
bound receipt; no-requirement benchmarks retain existing numerical behavior.

## Independent outcomes and public contract

The twelve quality gates use structured registered evidence and deterministic
ownership: direct destinations, specific semantics, scope, grounding fallback,
then qualifying systemic groups. For SCOPE, COMPOUND and GROUNDING, the
major/critical requirement applies to the defect consequence; delivered severe
mismatch/no-fit evidence has no additional locator-severity threshold. This
V10-only helper does not change score or cap arithmetic. Direct-owned or uncertain items cannot be
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

Synthetic tests cover a nonempty facet amendment through migration, scoring,
report/projection and portable checkpoint; added weighted parents and exact
populations; altered review/source/scope/evidence/facets; strict validity shapes;
direct and systemic gate boundaries; ownership; and immutable human decisions.
The numerical boundary probe compares 78 V9/V10 arithmetic cases independently
of deliberately versioned gate consequences. V8/V9 regressions remain required.
Outcome-matrix fixtures are contract unit examples, not claims that an invalid
source evaluation passed the native pipeline.
