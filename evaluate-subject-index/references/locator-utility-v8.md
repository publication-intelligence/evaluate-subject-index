# Locator utility — V8

## Two axes

Page treatment measures how much independently useful information about the complete heading path is present at the destination. Complete-path fit measures whether the full path accurately identifies that treatment. Rhetorical form does not determine depth: comparative facts and useful attributed observations may be substantive or mixed; contentless attributions, citations, and examples remain weak. Derive both axes from current structured audit fields and use the lower value only as diagnostic credit.

| Axis category | Credit |
| --- | ---: |
| substantive / exact | 1.00 |
| mixed / material partial | 0.70 |
| weak presence | 0.25 treatment ceiling |
| minor fit mismatch | 0.35 fit ceiling |
| major fit mismatch | 0.15 fit ceiling |
| absent, invalid destination, or no fit | 0.00 |

Uninspectable evidence produces a neutral uncertainty bound. A required `not_measured` record prevents a full score.

## Validation

Current structured fields must agree on judgment, treatment, scope, error codes, severity, path identity, and applicable defects. A bare consequence code such as `LOC_POS` cannot establish a semantic fit cause. Unknown, incomplete, identity-inconsistent, or contradictory states fail validation. Prose is explanatory only.

## Reporting

Each locator reports treatment category and score, fit category and score, `diagnostic_credit`, diagnostic grade, binary `rating_credit`, rule IDs, disposition, and rating-credit uncertainty endpoints. `supported` means keep unchanged and receives rating credit 1. `partially_supported` and `unsupported` receive 0. Page-reference Reliability uses keep precision (`supported / assessable`), not the diagnostic minimum.
