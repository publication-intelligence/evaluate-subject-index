# Judgment policy — V8

Make judgments from source evidence and the complete heading path. Do not infer a category or score from rationale prose.

## Locator decisions

- `supported`: keep the locator unchanged. It may have `substantive` or `mixed` treatment, but must fit the complete heading path closely enough to remain as delivered.
- `partially_supported`: relevant treatment exists, but the locator must not be kept as delivered because its treatment or complete-path fit is materially incomplete.
- `unsupported`: do not keep the locator as delivered.
- `uninspectable`: the destination cannot be evaluated; preserve neutral uncertainty.

Judge treatment by independently useful information about the full heading path, not by sentence form. Comparative lists can contain substantive facts. Attributed observations can be meaningful for an author heading. Reserve `attribution_only`, `citation_only`, and `incidental_example` for passages that provide no independently useful information about the full path.

Calibration:

- `Paris > population and growth`: “Paris grew by perhaps 100,000 people...” is `substantive` or `mixed` according to depth, even inside a comparison.
- `Young, Arthur`: an attributed observation is meaningful when it independently informs the reader about Young.
- “For example, Young (1794),” without further information remains weak presence and is not kept.
- A source saying a fact “may suggest” does not exactly fit a heading that asserts the conclusion as established. Preserve the stance mismatch even when page treatment is substantive.

Record treatment class, `complete_path_fit`, scope, error codes, severity, evidence IDs, and fit rationale consistently. `complete_path_fit` must be `exact_fit`, `material_partial_fit`, `material_mismatch`, `severe_mismatch`, `no_fit`, or `uninspectable`; do not derive it later from prose. Never weaken scope, relationship, chronology, attribution, compound-heading, or stance checks.

## Diagnostic grade and rating credit

The treatment and fit scores remain diagnostic. The diagnostic credit is their minimum, and the displayed locator grade is 100 times that minimum. Rating credit instead follows the keep decision: `supported=1`; `partially_supported=0`; `unsupported=0`; `uninspectable` and `not_measured` have no central rating credit.

## Missing access and structure

Judge every expected benchmark treatment assigned to the chunk. Record found, missed, excluded, or uninspectable status. Full mode requires complete, non-overlapping denominator coverage.

Numerical locator-string and range thresholds trigger review only. A defect requires structured evidence of conceptual distinctions, a useful alternative organization, and material retrieval harm.

## Independence

Benchmark construction remains candidate-blind. Worker artifacts are accepted through local validation and registration; Git history and checkpoint hashes are not evaluation evidence.
