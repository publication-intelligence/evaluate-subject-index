# V10 semantic-uncertainty interpretation addendum v2

Addendum identity: `subject-index-evaluation-v10-semantic-uncertainty-addendum-v2`  
Status: approved bounded interpretation for implementation and coordinated review; not activated  
Parent decision contract SHA-256: `f812eae0d09b60a4c1e74b1b6b9e6dd5850e088f9f9bb583152e9559f6ee07a9`  
Incorporated v1 SHA-256: `e0f0e91a23274a94e292409b17df53d1b403bd0a52b26e6e7ae84809430c5f76`

This artifact incorporates v1 in full and supplies the following exact
clarifications. These clauses control wherever v1 wording could be read more
broadly. The parent decision contract and v1 bytes remain unchanged.

## 1. Numeric invariance and outcome precedence

Semantic uncertainty always creates assessment insufficiency, but it does not
override independent validity or quality-gate facts.

- If evaluation validity is `invalid`, authoritative evaluation remains
  `invalid`.
- Otherwise, semantic assessment insufficiency makes authoritative evaluation
  `indeterminate`; a collapsed numeric interval cannot make it authoritative.
- A confirmed candidate-quality gate makes method readiness `not_ready`, even
  when semantic uncertainty coexists.
- With no confirmed quality gate, invalid/indeterminate validity or semantic
  assessment insufficiency makes method readiness `indeterminate`.
- A numeric dimension or overall result may be emitted only under the existing
  invariant-bound and cap rules, with semantic provenance retained. Numeric
  invariance and evaluation authority remain separate facts.

This is the parent contract's existing precedence: confirmed gate for readiness,
validity for authority, then assessment sufficiency. Semantic uncertainty never
certifies sufficient gate assessment.

## 2. Preserve established axes and evidence

The semantic branch is axis-specific. `judgment=semantic_unresolved` is used
only when the keep decision is unresolved. If keep/non-keep is established,
retain the existing `supported`, `partially_supported`, or `unsupported` value
even when treatment or fit is unresolved. The same preservation rule applies to
every known treatment, fit, scope, and destination fact.

Only a premise that is unresolved is unavailable to a quality-gate predicate.
Do not suppress an independently complete predicate merely because a different,
irrelevant axis in the same row is unresolved. Conversely, a gate cannot rely
on an unresolved axis or on a fact whose truth depends on that axis. The exact
assessment blocker must therefore name the unresolved axes and suppress only
the locator/path/destination claims that depend on them.

For example, if non-keep, `no_fit`, scope, physical inspectability, evidence,
and every other required predicate fact are independently established, an
unrelated unresolved diagnostic classification does not erase those facts. If
the gate also requires a treatment, relationship, or destination proposition
that remains unresolved, the predicate is not established.

## 3. Jointly consistent uncertainty envelope

The state space used for reliability, diagnostic, selectivity, zero-rule, and
cap bounds is the intersection of:

1. all established axis values;
2. every existing cross-axis invariant; and
3. the unresolved axis's values already permitted by the frozen rubric.

Never enumerate a logically inconsistent state to widen a bound. In particular,
known `exact_fit` or `material_partial_fit` excludes `absent`, because the
existing contract requires `absent` to carry `no_fit`. If all jointly consistent
treatment states are selectivity-applicable, the applicability interval
collapses to definitely applicable even though treatment credit may remain an
interval. Known keep or treatment facts constrain possible fit states in the
same way.

This clarification changes no mapping, formula, weight, cap, threshold, or
rounding rule; it limits the uncertainty envelope to states the existing
contract actually permits.

## 4. Physical small-denominator exception

The existing single-`uninspectable` small-denominator exception remains limited
to physical uninspectability. `semantic_unresolved` has its own count and does
not increment, inherit, or broaden that exception or its threshold.

## 5. Identical retained-distinction canonicalization

V1 correctly authorizes deterministic canonicalization of wholly identical
parent-qualified retained distinctions only in the derived candidate-access
review inventory, while preserving frozen benchmark bytes and rejecting any
same-key conflict.

Precision correction: `e215033a789fbafa5ad2d3c31c6f0449d991780c7a79707aab3a162178f1b330`
is the canonical hash of the single duplicated whole retained-distinction
value. It is not an inventory hash. `2,732` is the separately reconstructed
count of distinct parent-qualified requirements. Implementation/adoption must
independently verify both facts and must not present their combination as one
hash assertion.

This canonicalization creates one unchanged, unweighted review obligation from
two identical occurrences. It changes no source bytes, meaning, weight,
benchmark opportunity population, or scoring denominator. Derived provenance
must retain the occurrence count and source positions/identities needed to
reconstruct the duplicate.

## 6. Execution binding

The corrected execution contract consists of the parent decision contract, v1,
and this v2 clarification, each bound by exact file hash. An implementation may
publish a canonical aggregate digest over those three identities and hashes,
but may not replace, edit, or relabel any constituent. New runtime, calculation,
comparison, fixture, installation, and consumer identities must bind this v2
contract and reject final815/corrected mixing.

All acceptance conditions and execution holds in v1 remain in force. Nothing in
this clarification authorizes candidate publication, website deployment, or
mutation of the sealed source release, benchmark-access amendment, common lock,
or candidate evidence.
