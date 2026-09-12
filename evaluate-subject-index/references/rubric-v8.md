# Subject Index Evaluation technical rubric — V8

## Current identities

- rubric: `subject-index-rubric-v8`
- standard policy: `subject-index-standard-policy-v8`
- evaluation policy: `subject-index-evaluation-policy-v4`
- calculation input: `subject-index-dimension-calculation-input-v2`
- calculation profile: `subject-index-dimension-calculation-v5`
- calculation artifact: `subject-index-dimension-calculations-v6`
- result: `subject-index-evaluation-result-v11`
- item policy: `subject-index-item-grading-v4`
- explanation contract: `locator-explanations-v2`
- item artifact: `subject-index-item-assessments-v6`
- projection metadata: `subject-index-v8-projection-metadata-v1`
- web report: `subject-index-web-report-v9`
- locator-fit preflight: `subject-index-v8-locator-fit-preflight-v1`
- locator audit: `locator-audit-v2`

Runtime commands accept the current identities only. A V8 calculation input must bind the self-hashed V8 policy whose hash matches audit provenance. Old state, calculation, result, item, and report artifacts are not rescored or migrated.

## What changed in V8

V8 makes two distinct kinds of change:

- **Arithmetic:** Page-reference Reliability replaces weighted locator-utility precision with binary keep precision. All six dimensions remain percentage-native at full precision: genuine caps are percentage ceilings, weighted contributions are not rounded, and only the summed overall percentage is rounded to the nearest hundredth.
- **Judgment policy:** V8 clarifies how source evidence is classified, including comparative facts, attributed observations, contentless mentions, and complete-path stance. These are not formula changes. They may nevertheless change a locator's treatment class or keep decision in a new V8 audit, which can change any downstream input or result that uses that judgment. In particular, a treatment-class change may affect Editorial Selectivity even though its formula and treatment-credit mapping are unchanged.

An unchanged formula therefore does not guarantee an unchanged result when its underlying V8 judgments differ. Frozen V7 evaluations remain unchanged and are not reinterpreted.

## Treatment and complete-path fit

Treatment measures independently useful information about the complete heading path. Rhetorical form is not a ceiling: comparative-list facts and attributed observations may be `substantive` or `mixed`. `attribution_only`, `citation_only`, and `incidental_example` mean weak presence only when the passage supplies no independently useful information about the full path.

Calibration cases:

- `Paris > population and growth`: “Paris grew by perhaps 100,000 people...” is not weak merely because it is one item in a comparison.
- `Young, Arthur`: useful attributed information about Young is meaningful treatment.
- “For example, Young (1794),” without informative content is weak presence.
- Substantive treatment plus a major stance mismatch, such as established wording for a source that says only “may suggest,” remains nonexact and is not kept.

Evaluate full scope, relationship, chronology, compound meaning, attribution, and stance independently of treatment depth.

| Treatment diagnostic | Score |
| --- | ---: |
| substantive | 1.00 |
| mixed | 0.70 |
| contentless passing mention, attribution, citation, or example | 0.25 |
| absent or invalid destination | 0.00 |
| uninspectable | neutral 0–1 bound |

| Complete-path-fit diagnostic | Score |
| --- | ---: |
| exact | 1.00 |
| material partial | 0.70 |
| minor mismatch | 0.35 |
| major mismatch | 0.15 |
| no fit | 0.00 |
| uninspectable | neutral 0–1 bound |

For each assessable locator:

\[
D_j=\min(T_j,F_j),\qquad G_j=100D_j
\]

`D_j` and `G_j` are diagnostic only. Explanation prose is not an arithmetic input.

## Binary keep credit and Page-reference Reliability

`supported` is the authoritative “keep unchanged” decision and receives rating credit 1. `partially_supported` and `unsupported` are not kept as delivered and receive 0. `uninspectable` remains neutral uncertainty; `not_measured` retains incomplete-audit behavior.

For assessable locators:

\[
P_K=\frac{N_{supported}}{N_{assessable}}
\]

Expected-treatment recall remains:

\[
R_T=\frac{N_{found}}{N_{found}+N_{missed}}
\]

The Page-reference Reliability base percentage is:

\[
F_1=\frac{2P_KR_T}{P_K+R_T},\qquad \text{base percentage}=100F_1
\]

Existing cap triggers, gates, uncertainty bounds, and weights apply unchanged. Caps are expressed as percentage ceilings (for example, the former 2/5 ceiling is 40%). A `supported + mixed + exact_fit` locator therefore reports diagnostic grade 70 and rating credit 1.

For dimension percentage \(D_i\) and weight \(w_i\), the contribution is \(D_iw_i/100\). Retain the exact decimal through every dimension and contribution, sum the six contributions, and apply `ROUND_HALF_UP` to `0.01` only to that final sum. Half-point dimension rounding and per-contribution cent rounding are not part of V8.

## Structure quantities

| Quantity | Use |
| --- | --- |
| `displayed_locator_count` | scanning and subdivision review |
| inclusive range span | long-continuous-range review |
| `atomic_assignment_count` | locator auditing, precision, recall, and routing |

More than six displayed locators or a range longer than ten pages triggers review; it does not itself create a defect. Structure scoring and all non-reliability dimension formulas remain unchanged. Their results may still differ when a new V8 audit supplies different policy-governed judgments as inputs.

## Provenance

Calculation rows retain diagnostic categories and scores, binary rating credit, rule IDs, disposition, and uncertainty. Item projections display the diagnostic grade and factor breakdown while `dimension_reliability_credit` carries binary rating credit. Hashes join frozen records and prevent accidental cross-policy rescoring.
