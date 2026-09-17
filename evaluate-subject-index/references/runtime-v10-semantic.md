# Explicit V10 semantic correction

This review runtime implements the parent V10 decision plus the immutable
[semantic addendum v1](semantic-uncertainty-addendum-v1.md) and controlling
[v2 clarification](semantic-uncertainty-addendum-v2.md),
[v3 singleton rule](semantic-uncertainty-addendum-v3.md) and
[v4 known-nonkeep representation](semantic-uncertainty-addendum-v4.md). It is selected through
`scripts/v10_semantic_cli.py`; `v10_cli.py` retains the reviewed 815 behavior.
Installation, adoption and publication remain separate decisions.

## Adoption

First migrate a complete preserved V8 predecessor through the ordinary baseline
V10 source migration and selected source release. Preserve all prior artifacts.
Do not run source migration through the semantic CLI or reinitialize a V10 state.
The correction adopts an already migrated V10 evaluation:

```sh
python scripts/v10_semantic_cli.py adopt \
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
