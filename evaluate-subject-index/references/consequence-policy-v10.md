# Subject-index evaluation V10 decision contract

Contract version: `subject-index-evaluation-v10-decision-v1`  
Status: activated for the OHFR V10 retrospective study; later studies require their own lock and authorization  
Decision date: 2026-09-16  
Decision task: `01a09903-ee81-7122-8cfc-b2c2c7217114`  
Adoption turn: `01a0ad2a-18e6-7991-8285-5f779a93e295`

This record freezes the user-approved V10 methodology scope so runtime,
benchmark, validator, and website work do not have to infer it from task
summaries. The original adoption authorized implementation and review only. The
OHFR V10 retrospective study was later activated through its reviewed runtime,
benchmark, study lock, candidate migrations, and comparison integration.
Deployment remains separate and was not performed as part of that activation.

## Exact adoption statement

> `GATE-UNINSPECTABLE`, .`GATE-SOURCE-SPAN` --- We don't expect these to normally happen, right? Anyway, I agree that they should block an authoritative evaluation claim but cannot be quality of the index.
>
> I'm honestly pretty uncertain about any of the new V10 profile gates. I think we should leave those out because that's judging more the Format then the actual index itself. I think we should be agnostic of the form, add, and delivery, etc. So that's where we should depart from 0.2.
>
> I think we can green light everything we've determined for v10.

The two named validity conditions are expected to be exceptional in a valid
full workflow. Inspectability, source identity, source span, and page-map checks
should normally prevent or resolve them before an authoritative calculation.

## Version and migration boundary

- V10 uses new policy, rubric, calculation, artifact, projection, lock, and
  migration identities. V9 identities must not be widened or reinterpreted.
- V10 inherits the reviewed V9 percentage-native arithmetic and representation
  contract without changing the six formulas, weights, cap values, quantitative
  thresholds, uncertainty arithmetic, density bands, or final rounding.
- V8, V8.1, V8.2, and V9 historical artifacts retain their original meaning.
- The frozen V8.2 source state, policy, draft, review, benchmark, hashes, and
  candidate-blind provenance remain immutable source proof.
- V10 requires an explicit semantic migration and a separately frozen V10
  benchmark-access overlay. It may not relabel source proof or silently rewrite
  the preserved benchmark.

The reviewed V9 foundation is Evaluate Subject Index PR 53 at commit
`597e40068805b1d3e1dfc1d125ab3c6ec59366af`.

## Consequence classes

V10 keeps these outcomes independent:

1. ordinary score deduction;
2. dimension ceiling, whether binding or non-binding;
3. core candidate-quality gate;
4. evaluation-validity or assessment-sufficiency blocker; and
5. separately recorded human release decision or authorized deviation.

A low score is not a gate. Missing or uncertain evidence is not proof of bad
index quality. A human deviation never erases or changes the machine outcome.

## Core candidate-quality gate register

### `GATE-WRONG-LOCATOR`

One finalized delivered locator triggers this gate only when all are true:

- `judgment=unsupported`;
- `complete_path_fit=no_fit`;
- source scope is `indexable` or `excluded`;
- treatment is not `unavailable`;
- confidence is high or medium;
- source-linked evidence and a nonblank fit rationale exist;
- no unresolved uncertainty applies to that locator or every destination under
  its path; and
- no wrong-source-span finding prevents the judgment.

No severity, count, rate, spread, or separate defect record is required.
Partial fit, mismatch with nonzero fit, unavailable evidence, ambiguous scope,
and low-confidence evidence do not qualify.

### `GATE-BROKEN-REFERENCE`

One delivered `see` or `see also` exception triggers this gate only when its
judgment is `unsupported` and a typed, evidence-linked resolution confirms
`no_valid_destination` for the exact delivered type and target. Valid,
defective-but-identifiable, uncertain, and unbound destinations do not qualify.
Uncertain or missing resolution is an assessment blocker.

### `GATE-SCOPE-LOCATOR`

A delivered fabricated, nonexistent, or out-of-scope locator qualifies only
with major or critical severity, a blocking or misleading retrieval
consequence, and delivered `severe_mismatch` or `no_fit` evidence. Do not emit
it when the same atomic no-fit failure is owned solely by
`GATE-WRONG-LOCATOR`.

### `GATE-SYSTEMIC-UNSUPPORTED`

Within one root cause and one locator item-family denominator, union distinct
affected IDs and require all of:

- at least 10 qualifying delivered items;
- at least 5% of the applicable frozen denominator;
- at least two source or structural sections; and
- affected sections representing at least 25% of that section population.

Only `severe_mismatch` and `no_fit` evidence qualifies. Partial fits cannot
inflate the group. A group overlapping direct-owned atomic destinations is not
emitted, and residual spread must not be inferred by subtraction.

### `GATE-CENTRAL-OMISSION`

Trigger only for a critical central omission or a major central omission that
demonstrably destroys high-priority access to an essential or major benchmark
subject. A subject, treatment, heading route, synonym, or reader task merely
being absent is insufficient.

### `GATE-STANCE`

Trigger only for a major or critical stance reversal or misleading relationship
that materially misleads meaning or retrieval. Minor wording friction, audience
terminology preference, and defect codes without consequence evidence are
insufficient.

### `GATE-COMPOUND`

Trigger only for a major or critical compound-heading failure that blocks or
misleads and is supported by delivered `severe_mismatch` or `no_fit` evidence
for the complete combined concept. Separate-component or partial support alone
remains an ordinary deduction.

### `GATE-SEE-SUBSTITUTION`

Trigger only when a delivered substitutive `see`, at major or critical
consequence, materially blocks warranted substantive access. Missing
supplemental routes and ordinary nonpreferred-term friction do not qualify.

### `GATE-CROSS-REFERENCE`

Trigger only for a delivered circular, needlessly chained, or unsupported
reference with a major or critical blocking or misleading consequence, or a
cross-reference pattern satisfying the systemic 10-item, 5%, two-section, 25%
spread rule. Missing warranted-but-undelivered references are excluded.
`GATE-BROKEN-REFERENCE` owns a confirmed absent destination when the legacy
gate would rely solely on the same evidence.

### `GATE-CLUTTER`

Within one clutter root cause and applicable population, require at least 10
distinct items, at least 5%, at least two sections, and at least 25% section
spread. A localized clutter finding never gates.

### `GATE-GROUNDING`

This is a fallback for a delivered major or critical `severe_mismatch` or
`no_fit` locator that materially blocks or misleads and is not more specifically
owned by wrong-locator, scope, stance, or compound. Missed treatments, partial
fits, generic conceptual findings, and uncertain evidence are excluded.

### `GATE-STRUCTURE`

Trigger only for a true candidate-output failure: an empty, structurally
incomplete, or unparseable candidate, or critical representation or mechanical
corruption of the delivered index. Incomplete audit attestation,
uninspectability, wrong source span, and other evaluation gaps do not establish
this gate.

## Duplicate-evidence ownership

For the same atomic evidence, ownership order is:

1. direct destination: `GATE-WRONG-LOCATOR` or `GATE-BROKEN-REFERENCE`;
2. specific semantic: `GATE-STANCE`, `GATE-COMPOUND`,
   `GATE-SEE-SUBSTITUTION`, or non-atomic `GATE-CROSS-REFERENCE`;
3. `GATE-SCOPE-LOCATOR`;
4. fallback `GATE-GROUNDING`; and
5. systemic aggregation over independently qualifying, non-direct-owned groups.

Central omission, clutter, and true structure failures own their distinct item
families. Distinct findings remain separately reportable, but one atomic failure
must not be counted twice.

## Reclassified former gates

- `GATE-UNINSPECTABLE` becomes `VALIDITY-UNINSPECTABLE`. It triggers when
  required in-scope evidence cannot be judged or exceeds the frozen full-audit
  tolerance. It blocks an authoritative evaluation claim and says nothing about
  index quality.
- `GATE-SOURCE-SPAN` becomes `VALIDITY-SOURCE-SPAN`. It triggers when source
  identity or evaluated span is wrong or mismatched. It blocks an authoritative
  evaluation claim and says nothing about index quality.
- `GATE-DEPTH` is retired. Depth remains an architecture review signal and
  ordinary finding. A depth-related condition gates only when independently
  evidenced as a qualifying existing core failure.
- Missing, low-confidence, uncertain, or unbound destination evidence remains
  assessment-sufficiency or validity information, never candidate-quality proof.

## Explicit departure from IndexPDF Subject Indexing Standard 0.2

V10 is agnostic about output form and delivery. It adds no format, layout,
digital-link, semantic-format, keyboard, accessibility, privacy, data-governance,
AI-process, protected-material, or other profile gates. Those subjects do not
enter the six scores, caps, core gates, readiness, or public evaluation claims.
Implementations must not add placeholder profile-gate fields or infer these
claims in the website.

## Candidate-blind benchmark-access overlay

The approved benchmark-sensitive slice is limited to:

- `IPDF-GOV-02`: audience and likely lookup tasks, only as benchmark reader
  tasks and access language;
- `IPDF-ANA-06`: representation of materially treated people, communities, and
  perspectives without erasure, gratuitous labeling, or manufactured balance;
- `IPDF-VOC-01`: source-faithful, audience-intelligible terminology preserving
  attribution, negation, uncertainty, temporality, and contested status; and
- `IPDF-VOC-02`: evidence-supported synonyms, variants, abbreviations, former
  names, and likely-user terms as direct postings or valid equivalence routes.

Implement these as a separately identified V10 benchmark-access overlay bound
to the preserved source, page map, scope, benchmark, policy proof, and review
evidence. The overlay must be candidate-blind, source-grounded, independently
reviewed, frozen, hash-bound, and expressed as stable added or updated subjects,
reader tasks, terminology expectations, and route obligations. It must never
silently rewrite the preserved benchmark.

Reuse source discovery and locator audits unless a specific approved change
requires targeted complete-path review. Rerun affected missing-access,
navigation, fidelity, and architecture judgments, then recompute scores, caps,
gates, and reports. Document every reused and rerun stage. A change to source
scope, page map, inclusion policy, or a subject unsupported by preserved
evidence requires ordinary earlier-stage invalidation rather than this overlay.

The overlay maps only into existing dimensions:

- representation erasure to Meaningful Coverage;
- gratuitous labeling, manufactured balance, or lost semantic qualifiers to
  Conceptual/Stance Fidelity;
- audience tasks and equivalence routes to Findability/Navigation; and
- an existing gate only when its complete predicate above is satisfied.

It creates no dimension, weight, formula, cap value, or gate threshold. A
missing warranted route is not a broken delivered reference.

### Denominator treatment

“Unchanged discovery denominator” means the frozen source-discovery basis:
eligible source pages, measured words, source scope, and page map. The overlay
does not reopen or enlarge that source population.

The V10 benchmark opportunity population may change only through an explicit
overlay delta. Apply the smallest adequate representation:

- attach terminology, variants, equivalence routes, representation details,
  and reader-task details to an existing benchmark parent as unweighted facets
  when that parent already represents the access obligation; and
- add a weighted parent subject or task only when preserved source evidence
  establishes a genuinely distinct access obligation that cannot be represented
  faithfully as an existing parent's facet.

Every added, updated, or retired benchmark unit must record its stable identity,
source evidence, reason, parent or weight treatment, and the before-and-after
scoring population. This is a versioned V10 benchmark change, not a mutation of
the preserved V8.2 benchmark. It changes no weighting rule or score formula;
it changes only the explicitly reviewed set of opportunities to which those
unchanged rules apply.

## Readiness and release semantics

Candidate-quality gates, evaluation validity, gate-assessment sufficiency, and
human release decisions must be exposed separately.

- A confirmed core gate makes method readiness `not_ready`, even if other
  assessment gaps coexist.
- With no established core gate, a validity or assessment blocker makes the
  authoritative result `indeterminate`.
- Only a valid and sufficient evaluation with no core gate is method-ready.
- Human approval or `approved_with_deviation` is separate and cannot mutate
  score, ceiling, gate, validity, or assessment facts.

### Candidate-intrinsic ambiguity clarification

Semantic uncertainty is reserved for facts that remain genuinely unresolved
after complete inspection. It does not protect an ambiguous candidate route from
evaluation. When the source is inspectable but the delivered path, locator, or
reference is malformed, semantically incomplete, polysemous, or under-specified,
judge the delivered route as delivered and do not invent its intended concept.
If a reasonable reader cannot identify one supported complete concept at the
cited passage, the fit is known `no_fit`, the judgment is `unsupported`, and the
locator is `not_kept`. A lesser fit is allowed only when the cited passage visibly
supports a bounded part of the complete path. Dependent access, task, reference,
and architecture judgments follow the actual usability of that delivered route.
This clarification changes no benchmark, denominator, weight, formula, cap, or
gate threshold; it prevents candidate defects from being mislabeled as missing
evidence.

## Original execution hold and activation record

The original hold prohibited execution until runtime, validator, source/overlay
proof, fixtures, and consumer were reviewed together. That review completed for
the OHFR study through Evaluate Subject Index PRs 58 and 59, OHFR benchmark PR 17,
the four candidate migration pull requests, and Publication Intelligence website
PR 5. Those receipts activate only the bound OHFR study identities. They do not
authorize another study or a website deployment.
