# V8 locator diagnostics and binary keep-credit analysis

This analysis uses synthetic mixtures and exact `Decimal` arithmetic. It is not fitted to a candidate. Diagnostic fit values remain 1.00, 0.70, 0.35, 0.15, and 0.

The synthetic cases isolate the arithmetic change by holding structured locator judgments constant. V8 also changes judgment policy: its clarified evidence rules may produce different treatment classifications or keep decisions in a new audit. Those changed inputs can affect downstream results independently of the arithmetic change tested here.

## Diagnostic sensitivity

The diagnostic minimum preserves visibility into treatment and fit quality without affecting binary rating credit.

| Treatment and fit | Diagnostic credit | Rating credit when supported | Rating credit when not kept |
| --- | ---: | ---: | ---: |
| Substantive 1.00 + exact 1.00 | 1.00 | 1 | 0 |
| Mixed 0.70 + exact 1.00 | 0.70 | 1 | 0 |
| Weak 0.25 + exact 1.00 | 0.25 | not valid as `supported` | 0 |
| Substantive 1.00 + major mismatch 0.15 | 0.15 | not valid as `supported` | 0 |

The minimum remains an independent diagnostic ceiling. It is not weighted into Page-reference Reliability.

## Binary keep-precision cases

| Synthetic case | V8 outcome | Independent safeguard |
| --- | --- | --- |
| Two supported locators, one substantive and one mixed, with perfect recall | keep precision 1; mean diagnostic credit 0.85; reliability rating 5.0 | Mixed treatment remains visible in the item diagnostic |
| 10 kept locators and 90 non-kept weak mentions | keep precision 0.10; reliability rating 1.0 after unchanged rounding/caps | Weak presence remains zero for Editorial Selectivity and remains gate/cap evidence where applicable |
| Keep precision 0.90 but expected-treatment recall 0.25 | F1 0.391304…; rating 2.0 | Unchanged recall and high-value-recall caps prevent precision from hiding omissions |
| 99 kept locators plus one fabricated destination | keep precision 0.99; critical cap yields rating 2.0 | Fabrication gate and cap remain independent |
| One minor wrong relationship and one major wrong stance on substantive pages | diagnostic credits 0.35 and 0.15; both rating credits 0 | Complete-path and stance rules remain strict |

## Uncertainty and completeness

An uninspectable locator contributes no central rating credit and retains a neutral 0–1 keep-credit bound. A required `not_measured` locator remains incomplete work and is rejected in full mode. Defined-zero behavior for a source with expected treatments but no locator assignments is unchanged.

## Structure and other dimensions

Six displayed locators and a ten-page range do not trigger review; seven and eleven do. Trigger status never changes an architecture grade without structured semantic findings.

At the arithmetic level, V8 directly changes only the Page-reference Reliability precision input and related diagnostic/reporting identities. Recall, caps, gates, uncertainty handling, structure calculations, Editorial Selectivity, and all other dimension formulas remain unchanged. At the judgment-policy level, however, V8 may classify source evidence differently. A resulting treatment-class or keep-decision change may flow into Page-reference Reliability, Editorial Selectivity, or another downstream result that consumes that judgment. An unchanged formula is therefore not a guarantee of an unchanged V8 result.
