# Structure audit — V8

Native V8 structure audits use `structure-audit-v5` directly. The artifact is an exception ledger, not one stored pass row per heading.

## Exact scope

`candidate_denominator` lists every stable node identity, cross-reference ID, and locator-bearing path ID, with exact counts and deterministic ID-set hashes. Each set hash is SHA-256 over canonical JSON shaped as `{"ids":[...sorted IDs...]}`. `full_scope_attestation` states what omission means:

- Full mode requires complete review of all three denominators. Unlisted nodes are passes and unlisted cross-references are supported. The explicit pilot-pass arrays are empty.
- Pilot mode is incomplete by definition. Only explicitly listed pilot passes and exception rows are measured; every other denominator identity remains `not_measured` and contributes to uncertainty bounds.

`node_judgments` and `cross_reference_judgments` contain exceptions only. An all-pass node row or supported cross-reference row is redundant and invalid. The ledger separately preserves structured defects, strengths, uncertainties, density measurements, and scoring context.

## Locator architecture

For each triggered complete path, retain three distinct quantities:

- `displayed_locator_count`: one per delivered singleton or continuous range;
- inclusive span for each continuous range; and
- `atomic_assignment_count`: expanded page assignments used for support auditing.

Each displayed locator owns its exact ordered atomic locator IDs. Their flattened order must equal the path's atomic ownership list exactly once. Singleton rows own one assignment and no range fields; range rows bind a range ID, document-page endpoints, inclusive span, and all expanded assignments.

Review is triggered by more than six displayed locators or a continuous range longer than ten pages. Exactly six and ten do not trigger. Every triggered path has one `triggered_reviews` row.

A numeric trigger is never an automatic defect. `defect_confirmed` requires all four semantic findings, evidence, and a bound `HED` or `SUB` findability defect. `reviewed_no_defect` requires evidence and at least one unmet semantic prerequisite. Full mode forbids unresolved triggers; pilot mode preserves them as heading-access uncertainty.

`metrics.total_paths` is the denominator for path-scoped structure defects. It must cover every locator-bearing path and cannot exceed `total_nodes`. Locator-only density checks continue to use `page_bearing_paths`.
