# Customer methodology — V8

The evaluation compares a finished subject index with its source using a benchmark prepared without seeing the candidate index. It reports six dimensions, evidence-backed findings, item-level explanations, and an overall result.

## Evaluation sequence

1. Map and chunk the source.
2. Freeze the evaluation policy and source benchmark.
3. Prepare the candidate index into normalized paths and atomic locator assignments.
4. Audit locator support, missing access, structure, cross-references, and density.
5. Calculate current V8 dimensions and render the report.

Parallel chats may process independent frozen chunks. Their output becomes canonical only after local validation and registration in `evaluation-state.json`.

## What changed in V8

V8 changes Page-reference Reliability arithmetic by replacing weighted locator precision with a binary question: should each locator be kept unchanged? This directly changes the precision input to that dimension; its recall measure and F1 calculation remain the same. Each dimension is calculated as a full-precision percentage. Genuine rubric caps are applied as percentage ceilings, each percentage is multiplied by its weight without rounding, and only the sum of the six contributions is rounded to the nearest hundredth.

V8 also clarifies several evidence-judgment rules, such as how comparative facts, attributed observations, contentless mentions, and differences in stance are classified. Those policy clarifications do not change a scoring formula, but they may change a locator's treatment classification or keep decision in a new V8 audit. When they do, any dimension that uses the changed judgment may produce a different result. For example, Editorial Selectivity retains its existing formula and credit mapping but may receive different treatment-class inputs.

For that reason, “formula unchanged” does not mean that a new V8 evaluation must reproduce a V7 result. Existing frozen V7 evaluations are not changed or reinterpreted.

## Reliability method

Each locator receives two diagnostic assessments: how much independently useful information is present and how well the complete index path fits it. Comparative or attributed wording does not reduce treatment by itself. The lower diagnostic score produces the displayed locator grade.

Rating credit is separate: a locator marked `supported` is kept unchanged and receives full credit; any assessable locator not kept as delivered receives zero. Expected-treatment recall is combined with this binary keep precision using the unchanged F1 calculation. Dimension results are not converted to ratings out of five, and neither dimensions nor weighted contributions are rounded.

Free-text rationale explains structured decisions but never supplies a score. Uninspectable material is represented through explicit uncertainty rather than guessed.

## Structure method

A continuous page range counts as one displayed locator for scanning and subdivision review, while its pages remain separate atomic assignments for support auditing. More than six displayed locators or a range longer than ten pages triggers review, not an automatic penalty. A defect requires evidence that the structure materially harms retrieval and that a meaningful conceptual alternative exists.

## Reproducibility

The state file records the active configuration and artifact inventory. Hashes link related records and catch accidental mix-ups; they are not security attestations. Checkpoints are optional recovery snapshots and do not have to match an earlier archive checksum to resume.

This repository supports the current V8 workflow only. Existing frozen evaluations must be newly instantiated and frozen to use V8.
