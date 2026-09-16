# Parallel candidate audits

Locator and missing-access audits can be divided among chats by frozen chunk ownership. Parallelism changes transport, not judgment rules or the state machine.

## Locator audits

First create the frozen packets from registered local artifacts:

```bash
python scripts/page_chunk_cli.py prepare-locator-chunks \
  --state evaluation-state.json \
  --normalized-candidate candidate/candidate-index.json \
  --page-map page-map.json \
  --chunk-manifest chunk-manifest.json \
  --benchmark source-benchmark.json
```

This command must complete `locator_chunk_preparation`; an unresolved or ownerless locator produces an unregistered routing diagnostic and blocks worker registration.

Each chat receives the current checkpoint or equivalent evaluation files plus one locator packet. It returns one `locator-audit-v2` artifact covering every and only the packet's assignments.

Every locator row must state `complete_path_fit` as one of `exact_fit`, `material_partial_fit`, `material_mismatch`, `severe_mismatch`, `no_fit`, or `uninspectable`. It is a native judgment field and is never reconstructed from prose.

Worker output does not need to repeat global source, policy, page-map, manifest,
candidate-file, inventory-file, or audit-set hashes. If older V8 artifacts retain
those values in `provenance`, they are informational only; registration validates
the packet, candidate, evaluation, stable IDs, and exact owned denominator.

Validate without mutation:

```bash
python scripts/parallel_candidate_audit_cli.py validate-audits \
  --audit-kind locator \
  --audit locator-audit.CHUNK-001.json \
  --locator-packet locator-packet.CHUNK-001.json \
  ...frozen-input-arguments...
```

Use `register-audits` with the same inputs to copy validated files to the canonical candidate audit directory and update the single state. Partial batches leave `locator_audit` in progress. Full frozen-chunk coverage completes it.

To correct an already registered audit batch, rerun `register-audits` with
`--replace-complete-batch`. This explicit mode requires exactly one valid audit
and, for locator audits, exactly one valid packet for every frozen chunk. It
validates the entire selected set before replacing canonical audit files, marks
the selected audit stage complete, and resets every later stage while removing
its artifact registrations. Later output files remain on disk but are no longer
current.

## Missing-access audits

Missing-access work starts only after locator auditing is complete. Each worker uses the frozen benchmark, normalized candidate and inventory, and complete registered locator-audit set. Source PDFs are not routine inputs.

Pass `--audit-kind missing_access`, the audit files being registered, and one `--locator-audit` for every frozen chunk. Completion requires exact coverage of owned subjects, reader tasks, and treatments.

The coordinator derives each missing-access workset from the canonical inputs and
computes global audit-set identities from the files selected for calculation.
Workers do not predict or copy either global audit-set hash.

Supply complete frozen parent subject and reader-task records, including any
`required_access_facets`, nested questions and subject bindings, `access_scope_rule`,
and `retained_source_distinctions`. Include all referenced subject records even
when another chunk owns their judgments. Workset IDs and locator packets alone
do not contain these requirements. Review the full frozen scope before assigning
the existing parent coverage or task result; unweighted facets are requirements
within that judgment, not additional scored subjects, tasks, or denominators.

An optional private factual review receipt can document human-review QA. Bind it
to the exact benchmark, candidate and audit file hashes; identify each reviewed
facet by parent kind, parent ID and facet ID, and identify the reviewed scope rules
and retained distinctions within their parent records. Record the actual evidence
IDs, tested candidate paths, parent judgment and unresolved questions. Distinguish
reviewed requirements from satisfied requirements. Do not manufacture a receipt
from an expected-ID list or infer substantive review from schema validation.
Study coordination may require this receipt, but it is not a new runtime schema,
registration gate, automatic semantic pass, or scored unit. Existing validation
checks parent and treatment accounting; it does not prove that every nested
requirement was substantively reviewed. Keep private rationale and source text
out of public projections.

## Recovery and collaboration

Create checkpoints at useful batch boundaries, especially before handing work to another chat or when network interruption is likely. A checkpoint is a resumable snapshot; it is not a proof object and no previous checkpoint checksum is required.

Workers may return files through attachments, shared storage, branches, or pull requests. Canonical registration requires valid current artifacts and exact chunk denominators. It does not require GitHub API snapshots, PR receipts, blob hashes, merge evidence, publication bindings, or recovery receipts.

## Safety

- Validate all selected files before mutating state.
- Do not assign a document page or judgment ID to multiple chunks.
- Do not publish restricted source or candidate material.
- Do not overwrite a different already-registered audit without the explicit complete-batch replacement mode.
- Keep checkpointing separate from registration so checkpoint failure cannot roll back accepted work.
