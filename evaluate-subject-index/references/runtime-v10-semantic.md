# V10 semantic execution contract

This review runtime implements the parent V10 decision plus the immutable
[semantic addendum v1](semantic-uncertainty-addendum-v1.md) and controlling
[v2 clarification](semantic-uncertainty-addendum-v2.md),
[v3 singleton rule](semantic-uncertainty-addendum-v3.md) and
[v4 known-nonkeep representation](semantic-uncertainty-addendum-v4.md). It is
part of the canonical `scripts/v10_cli.py` runtime. There is no separate baseline
or semantic entrypoint.

Always invoke candidate adoption and study commands through `scripts/v10_cli.py`.
Importing `v10_migration.policy_content` directly before runtime selection is an
internal-module misuse and deliberately yields the historical non-semantic V10
identity; it is not a supported candidate execution path.

The current execution safeguards conserve every prior major/critical finding
and every prior warranted-reference defect against live successor IDs or
evidence-backed resolution. They require a findability defect for failed first
lookup, coherent access for every multi-facet parent, and exact judgment of any
delivered reference whose inventory target is unresolved. A null legacy
`target_path_id` is migration metadata, not candidate-side half-credit evidence:
a confirmed clean destination is supported, a material usable-but-defective
route requires typed adverse evidence for partial support, and an unresolved
binding remains an assessment blocker or uncertainty. Confirmed optional
minor failures enter their dimension without severity escalation. Distributed
reliability prevalence counts every zero-rating locator. These are dimension and
audit-integrity consequences only; decision v3 still has no overall-score cap.

For structure-ledger validation, `partially_supported` retains half credit only
for a material but nonfatal candidate-side cross-reference defect. The exception
must have a confirmed usable destination, nontrivial severity and evidence, plus
either a typed `defective_but_identifiable_destination` resolution or a
structured `XRF` defect bound to that delivered `XREF-*`. A
`valid_destination` resolution without documented adverse candidate behavior is
`supported`; omit it from the exception-oriented ledger so the complete-scope
supported attestation applies. A missing or genuinely unresolved binding must
remain an assessment-sufficiency blocker or explicit uncertainty.

Mechanically normalized null targets may be resolved without rewriting candidate
preparation output or adding clean rows to the exception ledger. After the
missing-access audit and before structure registration, use
`scripts/v10_cli.py reference-review --state ... --input ...` with a
`subject-index-v10-reviewed-cross-reference-bindings-v1` receipt. The receipt
binds the exact normalized candidate, item inventory, and selected structure
bytes; its `binding_set_sha256` is the canonical hash of the ordered `bindings`
array. Each binding preserves the delivered reference type and target text and
names one or more existing delivered `PATH-*` destinations.

The receipt must cover exactly every null-target reference attested as supported.
It cannot include structure exceptions or references affected by destination
uncertainty, and duplicates, omissions, stale bytes, type/text mismatches, or
nonexistent paths are rejected. A valid receipt removes only the corresponding
assessment-sufficiency resolution blocker. It is carried in projection metadata
provenance and does not mutate candidate artifacts, exception judgments, score
inputs, dimension weights, calculations, or genuine partial/unsupported results.

## Adoption

Already frozen studies may carry an execution-compatibility adoption receipt.
New studies start directly in the canonical V10 runtime and do not perform this
historical adoption step. For a preserved study that requires receipt validation:

```sh
python scripts/v10_cli.py adopt \
  --state /evaluation/evaluation-state.json \
  --compatibility /review/execution-compatibility.json \
  --source-release /review/successor-release.json \
  --output-dir semantic-execution
```

The reviewed compatibility document follows
`schemas/v10-execution-compatibility.schema.json`. It binds the actual selected
source release and common lock, baseline 815, successor commit, exact runtime
payload, all five contract constituents, and approval provenance. The review
owner verifies the commit and source-release proof independently; the runtime
checks these exact bindings and the installed receipt when present. Hashes are
content identities, not signatures or independent authorization.

Adoption validates first, writes a preserved state snapshot and deterministic
requirement inventory provenance, then invalidates scoring and web-report
registrations. Existing files and candidate/source/study bindings remain intact.
It refuses repeated adoption or output collisions. Existing truthful v2 audits
can remain registered. New semantic rows require locator-audit-v3. Use normal
`audit-candidate register-audits --replace-complete-batch` for completed batch
replacement; it invalidates downstream audits and factual access receipts under
the existing workflow. Rebuild those before scoring.

For a preserved V8.2 state that does not yet carry the four-family study lock,
the supported public sequence is `v10_cli.py study migrate-benchmark ...`
followed immediately by `v10_cli.py adopt ...`. The migrated V9 state is a
deliberate compatibility-pending transition: migration validates its complete
lock and policy binding, but scoring, auditing, checkpointing, and ordinary
study preflight remain unavailable until adoption binds decision v3.

## Native evidence

`axis_resolution` declares treatment, complete_path_fit and keep as known or
unresolved, completed inspection, a bounded reason and authored rationale.
Preserve every known axis. Null treatment/fit or `judgment=semantic_unresolved`
requires a genuinely unresolved corresponding axis. A domain forced to one value
by established facts is resolved; do not mark it unknown. Unresolved keep must
admit both kept and non-kept existing states. Native evidence and exact packet
membership remain required. Semantic uncertainty is separate from physical
uninspectability and not-measured work.

Known axes retain their original mappings and populations. Unknown treatment
uses an exact jointly consistent envelope through the preserved selectivity
calculator and caps; no central substantive percentage/cap is asserted unless
all permitted worlds agree. Reliability uses the unchanged keep/recall formula
and constrained cap witnesses. An invariant number never removes the assessment
blocker. Known independent quality gates and invalidity retain precedence.
Public rows use “Semantically unresolved after inspection”; authored semantic
rationale remains in private evidence.

Candidate-intrinsic ambiguity is not an unknown source fact. After complete
source inspection, a malformed, incomplete, polysemous, or under-specified
delivered path is judged as delivered. When a reasonable reader cannot identify
one supported complete concept at the cited passage, record known `no_fit`,
`unsupported`, and `not_kept` axes with a candidate-defect rationale; do not
invent the intended referent. Use a lesser fit only where the passage visibly
supports a bounded part of the complete path. Resolve dependent access, task,
reference, and architecture judgments from the actual usability of that route.
See the controlling clarification in
[consequence-policy-v10.md](consequence-policy-v10.md#candidate-intrinsic-ambiguity-clarification).

Inspected parent access uses `missing-access-audit-v2` when coverage, stance
preservation, realistic first-lookup success, or a dependent reader-task result
cannot be resolved from the inspected locator evidence. Each parent axis is
declared independently as known or unresolved. Only an unresolved axis is null;
known axes retain their observed values. These rows contribute neutral bounded
evidence, remain distinct from physical uninspectability, and make the affected
assessment gate indeterminate.

The same rule applies to a completed locator-architecture trigger review when
one or more subdivision prerequisites remain semantically unresolved. The
review uses `review_status=semantic_unresolved`, preserves every known boolean,
binds evidence for each null prerequisite, and records a neutral terminal-node
architecture judgment. It completes a full audit while keeping the affected
assessment indeterminate; it is not physical uninspectability or a no-defect
finding.

Identical retained distinctions are canonicalized only in the derived review
inventory, under the same parent/key and equal whole canonical value. Source
positions and multiplicity remain recorded. Conflicting duplicates and duplicate
facets are rejected. Source arrays, weights and opportunity populations do not
change.

## Output and comparison contract

[semantic-schema-versions.json](semantic-schema-versions.json) lists additive
schema identities. Calculations v9, items v10, results v15, reports v13 and V10
projection/collection v2 carry the correction. Public bundle filenames retain
layout v1; their schema identities and manifests bind v2 contents. Policy, source,
state and lock identities remain unchanged. Corrected calculations and comparison
identities bind the reviewed execution contract; baseline/corrected mixing or
different compatibility bindings is rejected.

Use `score score --state ... --output-dir ...` and `score build-report --state ...`
through the semantic CLI. Complete inspected audits can produce a report with
null numerical results and indeterminate assessment. A report's existence is not
release approval. Historical schemas reject the new branch.

Before cutover, jointly review the exact runtime, native synthetic fixtures,
consumer, compatibility document, installation payload and receipt. Do not use
synthetic compatibility approvals as actual release authority.

Known binary non-keep with unresolved legacy subtype uses
`judgment=not_kept_subtype_unresolved`, `keep_decision=not_kept`,
`axis_resolution.keep=known`, and `axis_resolution.judgment_subtype=unresolved`.
Use it only when all permitted worlds are non-keep and both partial and
unsupported subtypes remain possible. It keeps exact rating credit zero and
never increments unknown-keep counts. The blocker names fit/subtype, not keep.
