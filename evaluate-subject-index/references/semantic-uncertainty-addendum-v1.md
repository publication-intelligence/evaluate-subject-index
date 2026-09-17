# V10 semantic-uncertainty interpretation addendum

Addendum identity: `subject-index-evaluation-v10-semantic-uncertainty-addendum-v1`  
Status: approved bounded interpretation for implementation and coordinated review; not activated  
Parent contract: `subject-index-evaluation-v10-decision-v1`  
Parent contract SHA-256: `f812eae0d09b60a4c1e74b1b6b9e6dd5850e088f9f9bb583152e9559f6ee07a9`

This additive interpretation does not edit or replace the parent contract. It
does not authorize candidate-specific conventions, source or benchmark changes,
new scores, weights, formulas, caps, thresholds, gates, or scope. It resolves an
implementation gap in the inherited neutral-uncertainty contract: physically
inspected, scope-known evidence can remain semantically unresolved without being
misstated as unavailable, unsupported, supported, or not measured.

## 1. Contract interpretation

The parent contract already requires missing or uncertain evidence to remain
assessment-sufficiency information rather than candidate-quality proof and
preserves the inherited neutral uncertainty arithmetic. A versioned semantic
uncertainty representation is therefore an implementation correction within
V10, not a new substantive scoring decision. No further user decision is
required if implementation remains within this addendum.

## 2. Axis-preserving native record

Create a V10-only successor locator-audit schema and execution-contract identity.
Leave `locator-audit-v2` and every V8, V9, and final815 artifact unchanged.

A locator record enters the semantic-uncertainty branch when source inspection
is complete and physical scope is known but at least one of these axes remains
unresolved:

- treatment;
- complete-heading-path fit; or
- keep decision.

The record must preserve every known axis exactly. Its axis-resolution object
must name each unresolved axis and require completed inspection, a bounded
reason category including at least `unresolved_referent` and
`unresolved_relationship`, evidence IDs, and authored rationale.

Use the existing factual value for a resolved axis and a typed unresolved/null
value only for an axis explicitly named unresolved. In particular:

- `judgment=semantic_unresolved` is permitted only when the keep decision is
  unresolved;
- when the keep decision is established, retain `supported`,
  `partially_supported`, or `unsupported` even if treatment or fit remains
  unresolved; and
- an unknown diagnostic axis must never erase an established keep/non-keep
  fact.

Known source scope remains factual. An indexable inspected passage may not be
relabeled unavailable or ambiguous to obtain neutral treatment. `Unavailable`
and the existing `uninspectable` judgment remain reserved for actual physical
uninspectability. Semantic uncertainty itself supplies no error code, severity,
defect, or quality gate; independently established findings may coexist.

## 3. Completeness, assessment, validity, and readiness

A semantic-uncertainty row accounts for its exact expected locator in full-audit
completion, but is not measured on its unresolved axes. Denominators and count
tables must carry `semantic_unresolved` separately from `uninspectable` and
`not_measured` while preserving the original population.

Every semantic-uncertainty row automatically creates the existing
`GATE-ASSESSMENT-LOCATOR-UNCERTAIN` blocker, scoped to the exact locator, path,
and only those destinations explicitly dependent on the unresolved premise.
The blocker cannot suppress unrelated confirmed gate evidence.

Semantic uncertainty does not contribute to `VALIDITY-UNINSPECTABLE` and does
not use its tolerance. The existing single-uninspectable small-denominator
exception remains physical-uninspectability-only; this addendum does not expand
that exception or any other threshold.

Numeric invariance and evaluation authority are distinct:

- neutral bounds may occasionally collapse to the same numeric result and cap;
- such an invariant numeric result may be emitted under the existing calculation
  status rules, clearly retaining its semantic-uncertainty provenance; but
- unresolved semantic evidence always leaves gate assessment insufficient and
  the authoritative-evaluation status `indeterminate`;
- method readiness is `not_ready` when an independently confirmed core gate
  exists, otherwise `indeterminate`; and
- no invariant number can certify sufficient assessment or authoritative
  evaluation.

This preserves the parent contract's exact outcome precedence.

## 4. Reliability and diagnostic arithmetic

An unresolved axis receives neither central credit nor a zero observation.
Preserve the original denominator and apply the existing neutral lower/upper
arithmetic to that axis:

- unresolved keep: rating credit is null with bounds zero through one;
- unresolved fit: fit credit is null with bounds across the existing fit-credit
  states, constrained by any established facts; and
- unresolved treatment: treatment and combined diagnostic credit are null with
  bounds across existing treatment states, constrained by any established
  facts.

Known axes continue contributing to their own axis calculations. If keep is
known non-keep, its existing zero keep credit remains factual even when a
diagnostic axis is unknown. A resolved-only central diagnostic may be displayed
as such; it must not be described as assigning the unresolved row a central
zero or one.

Unknown rows cannot qualify as adverse gate evidence. Lower and upper cap
outcomes use only the existing cap predicates and thresholds, evaluated over
the permitted existing states.

## 5. Editorial-selectivity applicability

### Known treatment

Treatment is independent factual evidence and remains usable when fit or keep
is unresolved.

- An existing selectivity-applicable treatment class remains in the substantive
  selectivity denominator with its existing exact credit.
- A known `absent` treatment remains excluded under the existing
  `absent_owned_by_reliability` rule.
- `unavailable` remains the physical-uninspectability route and is not a
  semantic-uncertainty substitute.

### Unknown treatment

Selectivity applicability itself is unresolved. Retain the locator in the
original locator population and publish an applicability interval; do not put
it into one central applicable or excluded bucket.

Calculate the lower and upper post-cap selectivity results as the exact envelope
over the treatment states already permitted by the frozen rubric:

- applicable states use the existing credit mapping and systemic-zero cap
  calculation;
- the `absent` state uses the existing reliability-owned exclusion;
- the lower result is the minimum post-cap result across those states;
- the upper result is the maximum post-cap result across those states; and
- no central substantive-selectivity percentage or central cap assertion is
  established unless every permitted state yields the same result and cap.

Do not establish `locator_output_without_supported_access` merely because the
known rows lack substantive or mixed treatment. Evaluate that existing rule in
each permitted state and include its effect in the envelope. This is neutral
application of existing rules, not a new denominator, credit, cap, or formula.

## 6. Versioning and preservation

Version every schema or artifact whose accepted or emitted shape or denominator
semantics changes. Preserve exact resolved-case arithmetic and outputs. Bind the
new execution-contract identity and this addendum's file hash into new
calculation/comparison identities so final815 and corrected outputs cannot mix.

Preserve the sealed source release, zero-delta benchmark-access amendment,
candidate bytes, common source/benchmark semantics, and historical final815
installation receipt. If the common lock pins execution identities, create an
explicit successor execution-compatibility binding or a new lock version with
predecessor linkage; never rewrite frozen history. Apply one reviewed correction
uniformly to all four candidates.

## 7. Identical retained-distinction canonicalization

The frozen source currently contains one duplicated parent-qualified retained
distinction whose two values are wholly identical. Derived candidate-access
requirement construction may canonicalize records sharing the same parent,
requirement kind, stable identity, and complete canonical value to one review
obligation. This is preservation-compatible because retained distinctions are
unweighted nested requirements, not separate score units.

The implementation must:

- preserve the frozen benchmark bytes;
- record deterministic multiplicity/provenance for the derived inventory;
- produce one obligation only when the complete canonical values are identical;
- continue rejecting duplicate keys whose values differ in any way; and
- leave weights, meaning, benchmark opportunity populations, and scoring
  denominators unchanged.

For the reviewed inventory, this rule yields 2,732 distinct parent-qualified
requirements; the supplied inventory hash is
`e215033a789fbafa5ad2d3c31c6f0449d991780c7a79707aab3a162178f1b330`.
That count and hash must be independently reconstructed before adoption.

## 8. Minimum acceptance evidence

Use synthetic examples only. Verification must cover:

- indexable, inspected semantic uncertainty;
- known treatment with unresolved fit or keep;
- known non-keep with another unresolved axis;
- unknown-treatment applicability envelopes, including zero-rule and cap
  instability;
- exact-set full completion and separate semantic counts;
- physical uninspectability and its small-denominator exception unchanged;
- no physical validity failure from semantic uncertainty;
- exact assessment blockers and unrelated confirmed-gate coexistence;
- no fabricated quality gate;
- old-profile rejection and final815/V8/V9 invariance;
- public wording `Semantically unresolved after inspection`;
- identical duplicate canonicalization and conflicting-duplicate rejection; and
- exact source/amendment/lock preservation plus corrected/final815 comparison
  rejection.

Affected native rows remain pending until the successor runtime, schemas,
fixtures, consumer, execution-compatibility binding, installation payload, and
receipt are reviewed together. Nothing in this addendum authorizes publication
or deployment.
