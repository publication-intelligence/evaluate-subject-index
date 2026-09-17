"""Deterministic V10.1 overall-score ceilings over already scored evidence."""
from collections import defaultdict
from decimal import Decimal

import scoring_core as core


SYSTEMIC_THRESHOLDS = ((Decimal("0.05"), Decimal(75)),
                       (Decimal("0.15"), Decimal(60)),
                       (Decimal("0.30"), Decimal(40)))


def _record(cap_id, maximum, triggered, thresholds, observed, evidence_ids, equation):
    return {
        "cap_id": cap_id,
        "maximum_percentage": core.decimal_text(maximum),
        "triggered": triggered,
        "thresholds": thresholds,
        "observed": observed,
        "evidence_ids": sorted(set(evidence_ids)),
        "equation": equation,
    }


def _systemic_populations(defects):
    groups = defaultdict(list)
    for defect in defects:
        family = next((item.split("-", 1)[0] for item in defect["affected_item_ids"]), "OTHER")
        groups[(defect["root_cause_family"], family, defect["applicable_count"])].append(defect)
    for (root, family, denominator), rows in sorted(groups.items()):
        affected = sorted({item for row in rows for item in row["affected_item_ids"]})
        source = sorted({item for row in rows for item in row["affected_source_sections"]})
        structural = sorted({item for row in rows for item in row["affected_structural_sections"]})
        section_count = max(len(source), len(structural))
        section_denominator = max([row["source_section_denominator"] for row in rows] +
                                  [row["structural_section_denominator"] for row in rows])
        yield {
            "root_cause_family": root,
            "item_family": family,
            "affected_count": len(affected),
            "applicable_count": denominator,
            "rate": core.rate(len(affected), denominator),
            "section_count": section_count,
            "section_denominator": section_denominator,
            "section_rate": core.rate(section_count, section_denominator),
            "affected_source_sections": source,
            "affected_structural_sections": structural,
            "evidence_ids": sorted({row["defect_id"] for row in rows} | set(affected)),
        }


def _dominant_routes(ledgers, structure, source_span):
    by_path = defaultdict(list)
    for locator in ledgers["locators"]:
        by_path[locator.get("path_id")].append(locator)
    total_locators = len(ledgers["locators"])
    source_pages = source_span[1] - source_span[0] + 1
    defects = structure["defects"]
    for path_id, locators in sorted(by_path.items()):
        pages = [row["document_page"] for row in locators if isinstance(row.get("document_page"), int)]
        page_span = max(pages) - min(pages) + 1 if pages else 0
        related = [row for row in defects if path_id in row["affected_item_ids"] and
                   row["severity"] in {"major", "critical"}]
        concept = [row for row in related if row["dimension_owner"] == "conceptual_stance_fidelity"]
        navigation = [row for row in related if row["dimension_owner"] == "findability_navigation"]
        unsupported = [row for row in locators if row.get("judgment") == "unsupported" or
                       row.get("complete_path_fit") in {"severe_mismatch", "no_fit"}]
        unsupported_rate = core.rate(len(unsupported), len(locators))
        route_share = core.rate(len(locators), total_locators)
        qualifies = (len(locators) >= 25 and source_pages > 0 and
                     core.rate(page_span, source_pages) >= Decimal("0.25") and concept and navigation)
        yield {
            "path_id": path_id,
            "heading_path": locators[0].get("complete_heading_path", []),
            "locator_count": len(locators),
            "source_page_span": page_span,
            "source_page_denominator": source_pages,
            "source_page_span_rate": core.rate(page_span, source_pages),
            "unsupported_locator_count": len(unsupported),
            "unsupported_locator_rate": unsupported_rate,
            "candidate_locator_denominator": total_locators,
            "candidate_locator_share": route_share,
            "major_portion_unreliable": route_share >= Decimal("0.30"),
            "qualifies": bool(qualifies),
            "evidence_ids": sorted({path_id, *[r["locator_id"] for r in locators],
                                    *[r["defect_id"] for r in related]}),
        }


def evaluate(policy, ledgers, structure, pre_cap_score, locator_documents=()):
    """Return a complete audit trail and the lowest applicable overall ceiling."""
    caps = []
    defects = structure["defects"]
    major = [row for row in defects if row["severity"] in {"major", "critical"} and
             (row["defect_kind"] in {"central_omission", "stance_reversal", "misleading_relationship"}
              or (row["retrieval_consequence"] in {"blocks", "misleads"} and
                  row["dimension_owner"] == "findability_navigation"))]
    caps.append(_record(
        "overall.major_destructive_consequence", Decimal(80), bool(major),
        {"severity": ["major", "critical"], "consequences": ["major_destructive_route", "central_omission", "stance_reversal"]},
        {"qualifying_defect_count": len(major)},
        [item for row in major for item in [row["defect_id"], *row["affected_item_ids"]]],
        "triggered = qualifying_defect_count >= 1; ceiling = 80",
    ))

    groups = list(_systemic_populations(defects))
    if locator_documents:
        all_rows=[row for document in locator_documents for row in document['judgments']]
        failed=[row for row in all_rows if row.get('judgment') in {'partially_supported','unsupported','not_kept_subtype_unresolved'}]
        sections=sorted({document['chunk_id'] for document in locator_documents
                         if any(row.get('judgment') in {'partially_supported','unsupported','not_kept_subtype_unresolved'} for row in document['judgments'])})
        groups.append({'root_cause_family':'ALL-ZERO-CREDIT-LOCATORS','item_family':'LOC',
                       'affected_count':len(failed),'applicable_count':len(all_rows),
                       'rate':core.rate(len(failed),len(all_rows)),'section_count':len(sections),
                       'section_denominator':len(locator_documents),'section_rate':core.rate(len(sections),len(locator_documents)),
                       'affected_source_sections':sections,'affected_structural_sections':[],
                       'evidence_ids':sorted(row['locator_id'] for row in failed)})
    for threshold, maximum in SYSTEMIC_THRESHOLDS:
        qualifying = [row for row in groups if row["affected_count"] >= 10 and
                      row["rate"] >= threshold and row["section_count"] >= 2 and
                      row["section_rate"] >= Decimal("0.25")]
        caps.append(_record(
            f"overall.systemic_at_least_{core.decimal_text(threshold)}", maximum, bool(qualifying),
            {"minimum_count": 10, "minimum_rate": core.decimal_text(threshold),
             "minimum_sections": 2, "minimum_section_rate": "0.25"},
            {"populations": [{**row, "rate": core.decimal_text(row["rate"]),
                              "section_rate": core.decimal_text(row["section_rate"])} for row in groups]},
            [item for row in qualifying for item in row["evidence_ids"]],
            f"triggered = count >= 10 and count / applicable_count >= {core.decimal_text(threshold)} and sections >= 2 and sections / section_denominator >= 0.25; ceiling = {core.decimal_text(maximum)}",
        ))

    routes = list(_dominant_routes(ledgers, structure, policy["source_scope"]["document_page_span"]))
    dominant = [row for row in routes if row["qualifies"]]
    caps.append(_record(
        "overall.dominant_malformed_route", Decimal(60), bool(dominant),
        {"minimum_locators": 25, "minimum_source_span_rate": "0.25",
         "required_distinct_harms": ["conceptual_stance_fidelity", "findability_navigation"]},
        {"routes": [{**row, "source_page_span_rate": core.decimal_text(row["source_page_span_rate"]),
                     "unsupported_locator_rate": core.decimal_text(row["unsupported_locator_rate"]),
                     "candidate_locator_share": core.decimal_text(row["candidate_locator_share"])} for row in routes]},
        [item for row in dominant for item in row["evidence_ids"]],
        "triggered = locator_count >= 25 and source_page_span / source_page_denominator >= 0.25 and conceptual_harm and navigation_harm; ceiling = 60",
    ))
    dominant_critical = [row for row in dominant if row["unsupported_locator_rate"] >= Decimal("0.30") or row["major_portion_unreliable"]]
    caps.append(_record(
        "overall.dominant_malformed_route_unreliable", Decimal(40), bool(dominant_critical),
        {"minimum_unsupported_locator_rate": "0.30", "alternative": "route_locator_share >= 0.30"},
        {"qualifying_path_ids": [row["path_id"] for row in dominant_critical]},
        [item for row in dominant_critical for item in row["evidence_ids"]],
        "triggered = dominant_malformed_route and (unsupported_locator_count / route_locator_count >= 0.30 or route_locator_count / candidate_locator_denominator >= 0.30); ceiling = 40",
    ))

    attempt = structure.get("scoring_context", {}).get("candidate_attempt", {})
    unusable = attempt.get("status") in {"empty", "structurally_incomplete", "unparseable", "functionally_unusable"}
    caps.append(_record(
        "overall.functionally_unusable", Decimal(20), unusable,
        {"candidate_attempt_status": ["empty", "structurally_incomplete", "unparseable", "functionally_unusable"]},
        {"candidate_attempt_status": attempt.get("status")}, attempt.get("evidence_ids", []),
        "triggered = candidate_attempt_status in frozen unusable statuses; ceiling = 20",
    ))

    applied = min((row for row in caps if row["triggered"]),
                  key=lambda row: Decimal(row["maximum_percentage"]), default=None)
    pre = None if pre_cap_score is None else Decimal(str(pre_cap_score))
    post = None if pre is None else min(pre, Decimal(applied["maximum_percentage"])) if applied else pre
    return {
        "pre_cap_overall_percentage": core.decimal_text(pre),
        "cap_evaluations": caps,
        "applied_cap": None if applied is None else {"cap_id": applied["cap_id"], "maximum_percentage": applied["maximum_percentage"]},
        "post_cap_overall_percentage": core.decimal_text(post),
        "equation": "post_cap_overall_percentage = min(pre_cap_overall_percentage, lowest_triggered_maximum_percentage); ordinary dimension deductions are retained",
    }
