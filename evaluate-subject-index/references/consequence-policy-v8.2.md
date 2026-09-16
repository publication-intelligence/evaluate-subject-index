# Consequence policy — V8.2

V8.2 changes publication gates for confirmed completely wrong delivered destinations. Its identities are `subject-index-standard-policy-v8.2`, `subject-index-rubric-v8.2`, and `subject-index-dimension-calculation-v7`. The six dimension formulas, ordinary deductions, diagnostic grades, dimension ceilings, and quantitative thresholds for other patterns remain those of [V8.1](consequence-policy-v8.1.md). Artifact schema identities and CLI filenames remain unchanged where their shapes are retained. Current validators reject V8.1 scoring identities; reproduce V8.1 with merged revision `1e513806e58028b53c3e5d64dbe54b060e9aab56`. Never reinterpret a frozen V8.1 policy as V8.2.

## Confirmed wrong delivered locators

`GATE-WRONG-LOCATOR` triggers for even one finalized delivered locator with all of:

- `judgment: unsupported` and `complete_path_fit: no_fit`;
- inspectable `source_scope_status: indexable` or `excluded`, and a treatment class other than `unavailable`;
- high/medium confidence, source-linked evidence IDs, and an authored fit rationale;
- no unresolved uncertainty affecting that locator or its complete path, and no wrong-source-span finding.

The gate reads validated locator audit rows bound to the selected calculation's delivered locator IDs. It does not require a separately authored defect, major severity, a minimum count/rate, or spread. An excluded delivered destination qualifies when the audit confirms no eligible complete-heading support; an unavailable or ambiguous source does not establish that finding.

`no_fit` is zero fit. `absent` treatment already requires `no_fit` in the existing semantic contract. `material_partial_fit`, `material_mismatch`, and `severe_mismatch` retain nonzero fit (0.70, 0.35, 0.15 respectively) and do not qualify by themselves. A passing mention, attribution, citation, or incidental example with a fitting heading remains weak treatment, not a completely wrong destination. A generic `unsupported` label therefore never suffices. Existing independently qualified material-consequence gates still apply to serious mismatches; no gate change upgrades their severity or changes their score/cap consequences.

## Confirmed broken delivered cross-references

`GATE-BROKEN-REFERENCE` triggers for one delivered `see` or `see also` exception with `judgment: unsupported` and confirmed `target_resolution.status: no_valid_destination`. Severity and separate defect records are irrelevant to this rule.

Native V6 `cross_reference_judgments` optionally carry a typed `target_resolution` object:

```json
{
  "status": "no_valid_destination",
  "reference_type": "see also",
  "target_display": "the exact delivered target",
  "resolved_path_ids": [],
  "evidence_ids": ["EVID-TARGET-CHECK"],
  "rationale": "Public-safe explanation grounded in the complete frozen candidate."
}
```

Use these statuses precisely:

| Status | Meaning and required destination evidence |
| --- | --- |
| `valid_destination` | The delivered reference reaches an existing valid destination; list its delivered path IDs. |
| `defective_but_identifiable_destination` | A demonstrably existing, intelligible target has a defect such as a corrupted heading spelling; list its delivered path IDs. This is partial correctness, not absence or uncertainty. |
| `no_valid_destination` | Confirmed absent target, dead end, or cycle/self-reference with no usable destination. There are no resolved destination path IDs. A chain that reaches a valid destination is not automatically wholly wrong. |
| `uncertain` | Available evidence does not establish whether a valid/intelligible destination exists. This is an assessment gap, not a candidate-quality gate. |

Every resolution object requires the exact delivered `reference_type` and `target_display`, `resolved_path_ids`, nonempty source-linked `evidence_ids`, and a nonblank rationale. Confirmed valid/identifiable targets require at least one path ID. Confirmed absent destinations require none and cannot coexist with a partially supported or uninspectable judgment. Resolution type/target and destination path IDs are checked against the registered candidate inventory. An unbound exception cannot establish a gate.

The normalizer's `target_path_id: null` means unresolved normalization metadata, not a confirmed broken destination: it is not used as proof. A target like a recognizable but corrupted delivered heading can receive `defective_but_identifiable_destination` while retaining `partially_supported` and its ordinary deduction. A missing supplemental reference route is not a delivered cross-reference and cannot trigger this gate.

## Assessment sufficiency, evidence, and counting

`gate_assessment` travels through projection metadata, evaluation result, and web report. Its status is `sufficient` or `indeterminate`, with exact blocker IDs, affected item IDs, and reasons. Any non-supported delivered reference exception without confirmed typed resolution makes readiness indeterminate, including legacy exception rows with no resolution object. Existing supported pass attestations remain reusable. Low-confidence, uninspectable, or explicitly uncertain locator/reference evidence cannot become a candidate-quality gate. Missing/mismatched direct evidence and wrong-source findings are disclosed as assessment gaps. Ordinary calculation remains separate: missing destination proof does not invent a numeric deduction or ceiling.

Canonical public readiness uses the evaluation-validity outcome first, then any confirmed publication gate, then assessment sufficiency. It cannot affirm `publication_ready` with a missing/indeterminate gate assessment. A known quality gate can still establish `not_publication_ready` while other assessment gaps remain disclosed. These gaps do not create candidate defects.

Each direct gate records stable affected IDs, selected audit axes/target state, supporting evidence IDs, and a fixed trigger rationale. It does not publish private source evidence summaries. A direct gate owns its atomic destination failure: a legacy gate supported solely by the same destination failure is suppressed. Distinct material findings involving other items remain independently reportable, with directly owned IDs excluded from their affected-ID and qualifying-locator lists. A systemic group overlapping a directly owned destination failure is not emitted again: the direct gate already establishes non-readiness, and residual spread cannot be inferred by subtracting counts. Other nonoverlapping systemic patterns remain independently reportable. Never sum overlapping gate evidence as a count of distinct failures; use the union of stable affected IDs. Clutter and other systemic thresholds are unchanged.

## Retrospective policy provenance contract

Use the [schema-defined retrospective provenance contract](consequence-policy-v8.1.md#retrospective-policy-provenance-contract). Fresh policy freezes remain candidate-blind. For a combined migration, preserve the original candidate-blind policy and the latest V8.1 baseline; provide explicit authorization and a change ledger. The builder accepts the original V8/V8.1/current policy and a V8.1/current `--base-policy`, retains the base's scoring settings and existing gates, then adds the V8.2 direct gates and new policy identity. For a provenance-only cleanup already on V8.2, it retains all scoring settings/gates unchanged.

```bash
python /path/to/installed/evaluate-subject-index/scripts/policy_cli.py build \
  --input migration/policy-build-input.json \
  --original-policy evaluation/archive/v8-original/source/evaluation-policy.v4.json \
  --base-policy evaluation/archive/v8.1-before-v8.2/source/evaluation-policy.v4.json \
  --output migration/evaluation-policy.v4.json
```

Record the actual V8.2 migration timestamp and candidate visibility; preserve original policy/freeze and release/review evidence separately. Reuse discovery, benchmark content/review, source mapping, candidate normalization, locator audits, and missing-access audits. Do not claim a fresh independent review or approval. Populate typed cross-reference resolution only from the already frozen evidence supporting the exception; if that evidence is insufficient, retain an explicit unresolved blocker. Preserve the original judgment and severity, including partial correctness; never turn a partial fit into zero fit to force a gate. Document this targeted structured-evidence encoding in the ledger instead of claiming the supplemented structure audit is byte-identical.

Rebind the necessary policy/rubric/calculation identities and hashes, update canonical registration, and rebuild affected calculation/result/report/public bundles. Prove invariance against that evaluation's own latest V8.1 baseline for all ordinary deductions, six dimension scores, overall score, triggered/binding ceilings, and frozen judgments. Explain gate/readiness changes solely by the new rules and confirmed audit evidence; investigate any score/cap drift. Preserve prior bytes and reconcile ignored evidence/archive files in the durable saved-project checkout separately from Git. Migration is not complete while required destination exceptions remain silently unassessed.
