# Candidate preparation

Candidate preparation consumes a format-neutral layout artifact and converts it into current evaluation artifacts without judging index quality or consulting benchmark subjects.

## Input contract

The input is JSON conforming to [`candidate-layout-extraction-v1`](schemas/candidate-layout-extraction.schema.json), accompanied by the exact candidate file whose SHA-256 appears as `candidate_sha256`. The schema is the public boundary: acquisition and format-specific extraction happen before this skill begins. Adapter IDs are provenance, not a closed list, so a new converter does not require a skill change.

The V1 layout contract keeps its `pdf`-named fields for stable interchange. For a non-PDF input, set `pdf_metadata.is_pdf` to `false` and use one-based logical pages for `candidate_pdf_page`. Preserve the original bytes and place uncertainty in `limitations` or line-level `extraction_warnings`.

If supplied input does not match the contract, use this conversion prompt with the schema and the original candidate:

```text
Convert the supplied subject index mechanically into candidate-layout-extraction-v1 JSON that validates against the supplied schema. Preserve every displayed index line, its reading order, hierarchy/indentation, locators, cross-references, continuations, and original spelling and punctuation. Do not repair, summarize, deduplicate, classify, or judge the index. Hash the exact candidate bytes for candidate_sha256, assign stable unique IDs, record extraction uncertainty in the provided warning fields, and return only the complete JSON object. If faithful conversion is impossible, stop and identify the missing evidence instead of inventing content.
```

## Workflow

1. Confirm that the candidate file and layout artifact match the input contract.
2. `normalize` preserves every delivered hierarchy level and displayed locator form, including locator payloads separated from headings by whitespace, and expands locator assignments through the frozen page map. It writes the normalized candidate, the layout extraction needed for faithful-reproduction validation, and the item inventory required by the current downstream scoring/structure interfaces.
3. If normalization finds uncertainty or malformed input, it also writes one non-empty `candidate-normalization-issues-v1` report. Review every issue by changing `status` from `needs_review` to `confirmed_as_delivered` or `not_applicable` and add a `disposition` rationale. No report is written for a clean pass.
4. `validate-private` computes the full fidelity gate from those artifacts: exact candidate bytes, frozen identities, deterministic normalization, stable semantic IDs, page/region/line ownership, complete line and locator denominators, deterministic inventory, issue disposition, and candidate blindness. It writes no success artifact.
5. `register` repeats that validation, registers only the three required artifacts plus the issue report when present, records the normalized candidate path and file hash and the genuinely required downstream inventory and benchmark paths in state, and advances `candidate_normalization` in `evaluation-state.json`.
6. `page_chunk_cli.py prepare-locator-chunks` validates that registered binding and prepares the complete locator-packet batch directly from local artifacts.

The current contract uses `candidate-layout-extraction-v1`, `candidate-index-v2`, optional `candidate-normalization-issues-v1`, `subject-index-item-inventory-v2`, and evaluation state V6. The inventory remains canonical only because current scoring and structure commands consume it directly; it may be removed after those interfaces reconstruct it on demand. Superseded preparation formats are not accepted.

## Separation from judgment

Preparation may identify extraction uncertainty, malformed layout, and unresolved locators in the optional issues report. It must not repair the delivered hierarchy, classify source support, identify omissions, judge structure, or calculate scores. The benchmark is used at registration only to bind the completed preparation to the frozen evaluation, not as extraction evidence. That state binding replaces redundant candidate-reference and repository-lock artifacts; do not create a second manifest or compatibility artifact.

## Parallel and remote work

Preparation can happen in another chat or checkout. Return the validated preparation directory and register it locally. A branch or pull request is optional review infrastructure; GitHub evidence, worker receipts, recovery ZIPs, and merge proofs are not part of the canonical contract.

Use checkpoints before or after preparation when they are helpful for recovery. Resume does not depend on reproducing the previous checkpoint hash.
