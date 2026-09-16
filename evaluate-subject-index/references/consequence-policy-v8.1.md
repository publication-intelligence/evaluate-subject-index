# Consequence policy — V8.1

This is a substantive methodology revision, not a correction to the meaning of a frozen V8 score. It supersedes earlier cap/gate language in the V8 references. The current identities are `subject-index-standard-policy-v8.1`, `subject-index-rubric-v8.1`, and `subject-index-dimension-calculation-v6`. Artifact schema versions and CLI filenames remain unchanged where their data contracts remain compatible. Current validators require the revised identities. The original V8 implementation and contracts remain in Git at `514bcca`; use that version to reproduce original evaluations.

## Four distinct consequences

1. **Ordinary deduction:** retain adverse judgments and diagnostic/rating consequences, even when no ceiling or publication gate qualifies. A low score is not itself a publication gate.
2. **Dimension ceiling:** a separate maximum supported by material consequences or a frozen aggregate threshold. A triggered ceiling can be non-binding.
3. **Publication gate:** a separately evidenced serious index-quality failure. Gate counts do not enter score arithmetic.
4. **Evaluation validity blocker:** insufficient or wrong audit evidence makes the evaluation indeterminate/invalid. It does not establish that the index is unpublishable.

Minor/cosmetic defects never individually cap or gate. Missing supplemental heading or warranted cross-reference routes remain yellow review findings and scored omissions. They do not individually cap/gate. `material_partial_fit` remains yellow, keeps its diagnostic `min(T,F)` grade and ordinary binary keep consequence, and cannot support a ceiling or publication gate. Do not promote partial fits into major heading/stance defects simply to bypass this exclusion. A separate independently evidenced major heading misrepresentation may qualify on its own evidence.

## Publication gates

All individual material gates require `major`/`critical`, a compatible severity basis, and `blocks`/`misleads`. Defect codes alone are insufficient.

- **Scope locator:** delivered fabricated/nonexistent/out-of-scope locator plus severe mismatch/no fit and a material consequence.
- **Compound:** CMP plus delivered severe mismatch/no fit and a material consequence. Partial support of a compound heading is insufficient.
- **Stance:** major/critical materially misleading stance or relationship evidence. Minor relationship friction is insufficient.
- **Central omission:** critical central omission, or major omission demonstrably destroying high-priority subject access. A subject, heading route, or expected treatment merely being absent is insufficient.
- **Substitutive see:** delivered `see` that materially blocks warranted substantive access; retain the source/target evidence explaining the substitution.
- **Cross-reference:** delivered broken reference with major/critical consequence, or the systemic threshold below. Missing warranted references are excluded.
- **Clutter:** systemic threshold below, never a single localized clutter defect.
- **Grounding:** major/critical delivered severe mismatch/no fit. Missed treatments, partial fits, and generic conceptual defects are excluded. Specific stance, compound, and invalid-destination gates own their evidence; do not duplicate those defects here.
- **Structure:** true candidate-output failure (empty, structurally incomplete, unparseable, or critical mechanical/representation corruption). Incomplete audit attestation alone is not candidate-output failure.

Third-level headings are review signals only. There is no depth publication gate.

### Frozen systemic gate threshold

Within one root cause and one item family/denominator, union stable affected IDs; never sum overlapping defect counts. Require all of:

- at least **10 distinct affected items**;
- at least **5%** of the applicable frozen item population;
- at least **two source or structural sections**, representing at least **25%** of that section population.

Source and structural spread are alternatives, not added together. Include count, denominator, rate, spread, root cause, and affected IDs in the outcome. Mixed partial-fit evidence cannot inflate a systemic locator count; split and substantiate qualifying defects before aggregation. This rule also provides the explicit systemic missing-access ceiling path. An aggregate of minor defects may qualify only through a frozen quantitative rule.

## Dimension ceilings

Keep the existing ceiling values and rate bands except for these revisions:

- Findability's 90% localized-major ceiling requires a materially destructive/misleading delivered route or demonstrably destroyed high-priority access. A NODE attachment alone does not prove a delivered harmful route; substitutive `see` is specifically recognized. Supplemental route omissions by themselves are excluded.
- Findability's systemic-access ceiling is 80% at the systemic gate threshold above, including systemic missing routes. Critical qualified navigation retains 40%; major destroyed high-priority access retains 70%.
- Delivered major/critical severe-mismatch/no-fit locators have an explicit 80% Reliability ceiling. Critical fabricated/nonexistent/out-of-scope locators retain 40%. Both require structured consequence evidence and qualifying delivered locator records. Partial fits cannot trigger either path.
- Missed expected treatments reduce recall and F1 but no longer trigger the pooled high-value-treatment-recall ceiling. Essential subject omissions retain their separate Coverage consequences; essential means a benchmark-defined indispensable access need, not every missed treatment.
- Distributed Reliability patterns exclude partial fits and require at least three unsupported severe/no-fit delivered locators, plus the existing 1% item and 25% source-unit entry thresholds and rate bands.
- Concept/Findability architecture prevalence requires at least ten adverse nodes in addition to the existing rate bands. Findability task-failure and unsupported-reference rate ceilings require at least ten affected items in addition to their existing 10%/25%/50% bands. This prevents a tiny denominator from turning localized friction into a systemic cap.
- Aggregate minor/cosmetic Mechanics ceilings require at least three distinct adverse nodes plus the existing 5%/20% rate bands. Major recurrent/systematic Mechanics rules retain their separate frozen thresholds. Selectivity retains its ten-item, 5%, 25%-source-spread threshold and bands, excluding partial-fit locator evidence.

Never suppress ordinary component deductions when a ceiling is excluded. Preserve source-linked causal findings as display provenance, never numeric inputs. If frozen node judgments misclassify ordinary partial support or supplemental omissions as major meaning/access destruction, review those specific judgments against their source evidence; do not infer new severity from a defect code.

## Validity and presentation

Excessive uninspectability (default more than 1%, or the frozen alternative tolerance), wrong evaluated source span, and incomplete audit attestation produce indeterminate/invalid audit outcomes. Calculation preflight records blockers and cannot produce an authoritative score from them. A validity blocker does not trigger an index publication gate. A genuine candidate-output failure remains quality evidence even when the audit cannot finish.

Display **Applied cap** only when the ceiling actually lowers the score. Otherwise display **Non-binding triggered ceiling**. Selectivity ceilings act on its substantive subscore before the 10+5 combination; never present them as a direct minimum against the combined dimension percentage.

Every displayed ceiling/gate exposes the exact rule, affected evidence IDs, counts/rates where applicable, severity basis, retrieval consequence, and why the consequence crosses the threshold. Calculation `cap_evaluations[].observed` and gate `consequence_evidence`, `qualifying_locator_evidence`, `systemic_groups`, and `threshold_reason` carry this provenance; presentation tooltips expose the complete selected cap evaluation. `applied_cap` is a compatibility field naming the selected triggered ceiling; use pre/post values to determine whether it is binding.

## Targeted migration of a finished V8 evaluation

Migration requires explicit authorization and a new frozen policy and methodology/calculation identity. Preserve original V8 policy, calculation, result, and report bytes in version control or an archival directory. Do not rewrite them in place as though their old identities had always meant V8.1.

1. Inspect canonical state, policy, benchmark release evidence, source/candidate identities, all affected audit rows, and the calculation's exact input hashes. Record a before/after change ledger with original hashes, new identities, unchanged evidence reused, affected stable IDs, reasons, and validation results.
2. Freeze a V8.1 policy for the exact same source scope, audience, density profile, and audit mode. Rebind only policy/methodology metadata needed for the authorized migration. Explicitly record that candidate-blind discovery/review, benchmark content, source mapping, and candidate normalization were reused, not rerun. Preserve the original benchmark release and its original policy provenance; do not claim a new independent review. A mechanical policy-binding/hash cascade is not a new substantive audit.
3. Review only affected locator, missing-access, and structure judgments/defects. Preserve ordinary partial-fit and omission deductions. Retain unrelated evidence and assessments. Where a claimed gate lacks delivered locator identity, severity/consequence, exact denominator, or spread provenance, record the precise gap; withhold that unsupported escalation and limit the update. Do not regenerate unrelated audits to fill gaps.
4. Rebuild affected calculation/report artifacts from the targeted ledgers with current commands. Rebind current state artifact records and hashes coherently, retaining original artifacts and a migration record. Validate policy/state, audit semantics, calculation input hashes, score arithmetic, item provenance, and the complete public projection. Do not fake completion stages or benchmark approvals. Use the registered `score`/`build-report` flow where possible; if provenance cannot be migrated safely, deliver a bounded change report instead.
5. Compare original/revised ordinary scores, triggered versus binding ceilings, gate IDs, validity, and evidence IDs. Document every targeted substantive and mechanical change. Expected study outcomes are hypotheses to test against frozen evidence, never instructions to force a gate count.
