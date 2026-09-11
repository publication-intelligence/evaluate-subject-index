# Built-in standard policy — V8

Use the current V8 schemas and commands only.

## Locator judgments and treatment

Evaluate the complete heading path: its subject, scope, relationship, chronology, attribution, compound meaning, and stance. Rhetorical form does not determine treatment depth. A passage is meaningful treatment when it supplies independently useful information about the complete heading path, including when the information appears in a comparison, list, example, or attributed observation.

- `supported` means keep the delivered locator unchanged.
- `partially_supported` and `unsupported` mean do not keep it as delivered.
- `uninspectable` records neutral uncertainty.
- `not_measured` remains incomplete audit work and blocks a full calculation.

Use `attribution_only`, `citation_only`, or `incidental_example` only when the passage supplies no independently useful information about the complete heading path. Such contentless presence is weak and is not kept. Attribution does not by itself weaken an independently useful observation under an author-specific heading.

Calibration:

- Under `Paris > population and growth`, “Paris grew by perhaps 100,000 people...” is not weak merely because it occurs in a comparative list. Classify the actual depth as `substantive` or `mixed`.
- Under `Young, Arthur`, an attributed observation that gives independently useful information about Young is meaningful treatment.
- “For example, Young (1794),” with no useful information about Young remains `incidental_example` or `attribution_only` weak presence.
- Strong treatment does not cure a fit failure. A heading stating an established conclusion is nonexact when the source says only “may suggest.”

Use only structured current-audit fields for calculation. Evidence prose explains judgments but does not directly generate scores. Malformed, incomplete, identity-inconsistent, or contradictory states fail validation.

For every `heading_access_architecture` judgment with `minor_issues`, `major_issues`, or `fails`, record at least one structured causal finding. A finding identifies its causal kind, stable source IDs, all applicable reason codes, severity, evidence IDs, and a concise evidence-backed summary. Preserve overlapping findings. Record a primary finding only when a deterministic rule or explicit adjudication establishes one. Causal findings and their summaries are display provenance, never scoring inputs.

## Locator diagnostics and rating credit

Keep the two diagnostic axes:

\[
D_j=\min(T_j,F_j),\qquad G_j=100D_j
\]

Treatment scores are 1.00 for substantive, 0.70 for mixed, 0.25 for weak presence, and zero for absence or invalid destination. Fit scores are 1.00 exact, 0.70 partial, 0.35 minor mismatch, 0.15 major mismatch, and zero for no fit.

Rating credit is separate and binary: `supported` receives 1; `partially_supported` and `unsupported` receive 0. `uninspectable` and `not_measured` receive no central credit and retain their existing uncertainty or incomplete-audit handling. Thus `supported + mixed + exact_fit` has diagnostic grade 70 and rating credit 1; do not relabel it substantive.

Page-reference Reliability uses keep precision, `supported / assessable`, and unchanged expected-treatment recall in the existing F1, cap, gate, uncertainty, weighting, and rounding pipeline. This is V8's direct arithmetic change. Editorial Selectivity remains a separate dimension with unchanged arithmetic and treatment-credit mapping. Its input treatment classes are policy-governed, however, so a different V8 classification may change its result without changing its formula.

## Locator strings and ranges

A delivered singleton or continuous range is one displayed locator. A range can own many atomic page assignments.

- Use displayed locators for locator-string and subdivision review.
- Use inclusive span for long-range review.
- Use atomic assignments for support auditing, precision, recall, and routing.

More than six displayed locators or a range longer than ten pages triggers review. The threshold alone is not a defect. A scored architecture problem requires structured evidence that the entry combines conceptually distinguishable treatments, a useful alternative organization exists, and the current form materially harms retrieval.

## Checkpoints and identity

Checkpoint archives are recovery snapshots. Resume requires safe structure and current V8 state. Existing frozen evaluations are not reinterpreted under V8; create and freeze a new V8 policy and evaluation. Artifact hashes are content labels that detect input mix-ups.
