"""Exact selectivity envelope over jointly consistent frozen treatment/fit states."""
from decimal import Decimal
import scoring_core as core
from v10_semantic import resolved_possibilities


def selectivity_envelope(locators, source_units, *, non_attempt=False):
    """Monotone extrema over legacy-consistent states preserving known axes.

    Every applicable unknown treatment has the existing0/.5/1 credit. A permitted
    absent state also permits zero-credit/no-fit and substantive/no-fit states:
    replacing absence with that zero can only lower the mean/tighten its cap;
    replacing it with substantive can only raise the mean/loosen the cap.
    Known partial fit excludes absence, so its applicability is fixed. Among
    equal zero-credit choices, choose eligible fit for the lower cap and partial
    fit for the upper cap, if permitted. Source-unit spread is monotone too.
    Thus two jointly valid witnesses give exact extrema without7**N enumeration.
    Tests compare these witnesses with exhaustive legacy-calculator scenarios.
    """
    if any(r['source_scope_status'] != 'indexable' for r in locators):
        raise ValueError('Semantic selectivity envelope requires known indexable scope')
    options=[resolved_possibilities(row) for row in locators]
    if any(not states for states in options):raise ValueError('No jointly consistent selectivity scenario')
    credits=core.SELECTIVITY_CREDIT
    def applicable(row):return row['treatment_class'] in credits
    def eligible(row):return applicable(row) and credits[row['treatment_class']]==0 and row['complete_path_fit']!='material_partial_fit'
    def lower_key(row):
        # An optional absent state is dominated by its permitted eligible zero.
        return (credits[row['treatment_class']] if applicable(row) else Decimal(2),not eligible(row))
    def upper_key(row):
        return (credits[row['treatment_class']] if applicable(row) else Decimal(-1),not eligible(row))
    lower_rows=[min(states,key=lower_key) for states in options]
    upper_rows=[max(states,key=upper_key) for states in options]
    units=max(1,len(source_units))
    def scenario(rows):
        measured=[r for r in rows if applicable(r)];zeros=[r for r in measured if eligible(r)]
        zero_units={r['_source_unit_id'] for r in zeros if r.get('_source_unit_id')}
        maximum,triggered,band=core.selectivity_cap(core.rate(len(zeros),len(measured)),len(zeros),core.rate(len(zero_units),units))
        has_material=any(r['treatment_class'] in {'substantive','mixed'} for r in measured)
        zero_rule='candidate_not_meaningfully_attempted' if non_attempt else 'locator_output_without_supported_access' if rows and not has_material else None
        credit=sum((credits[r['treatment_class']] for r in measured),Decimal(0))
        base=Decimal(0) if zero_rule else Decimal(100)*credit/Decimal(len(measured)) if measured else Decimal(0)
        return {'percentage':min(base,maximum),'pre_cap_percentage':base,'applicable':len(measured),
                'credit':credit,'cap':{'cap_id':'selectivity.systemic_zero_credit' if triggered else None,
                'maximum_percentage':maximum,'band':band},'zero_rule':zero_rule,
                'zero_count':len(zeros),'zero_units':len(zero_units)}
    lower=scenario(lower_rows);upper=scenario(upper_rows)
    def cap_key(row):return (row['cap']['cap_id'],row['cap']['maximum_percentage'],row['zero_rule'])
    cap_invariant=cap_key(lower)==cap_key(upper)
    invariant=lower['percentage']==upper['percentage'] and cap_invariant
    a_lower=sum(all(applicable(r) for r in states) for states in options)
    a_upper=sum(any(applicable(r) for r in states) for states in options)
    return {'_lower_rows':lower_rows,'_upper_rows':upper_rows,'original':len(locators),'known_applicable':a_lower,'known_excluded':len(locators)-a_upper,
            'semantic_unresolved_applicability':a_upper-a_lower,'applicability_interval':{'lower':a_lower,'upper':a_upper},
            'lower':lower,'upper':upper,'cap_invariant':cap_invariant,
            'central_percentage':lower['percentage'] if invariant else None,
            'central_cap':lower['cap'] if invariant else None,'evaluated_extreme_scenarios':2}
