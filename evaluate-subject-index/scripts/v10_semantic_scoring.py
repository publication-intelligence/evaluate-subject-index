"""Candidate-only semantic bounds evaluated with the preserved scoring formulas."""
from copy import deepcopy
from decimal import Decimal
import scoring_core as core
from v10_semantic import LABEL, resolved_possibilities
from v10_semantic_envelope import selectivity_envelope


def selectivity(ledgers,audit_mode,resolved):
    rows=ledgers['locators']
    applicable_rows=[r for r in rows if r['source_scope_status']=='indexable' and r['treatment_class']!='unavailable']
    neutral=selectivity_envelope(applicable_rows,ledgers['source_units'],non_attempt=ledgers['context']['candidate_attempt']['status']!='meaningful_attempt')
    scenarios=[]
    for side in ('lower','upper'):
        replacements={r['locator_id']:r for r in neutral.pop('_'+side+'_rows')}
        scenario=deepcopy(ledgers)
        scenario['locators']=[replacements.get(r['locator_id'],resolved_possibilities(r)[0] if 'axis_resolution' in r else deepcopy(r)) for r in rows]
        scenarios.append(resolved(scenario,audit_mode))
    low,high=scenarios;result=deepcopy(low)
    for side,scenario in zip(('lower','upper'),scenarios):
        neutral[side]['zero_rule']=scenario['denominators']['components'][0]['defined_zero_rule']
    lower=low['missing_data_bounds']['lower'];upper=high['missing_data_bounds']['upper']
    low_caps=lower['cap_evaluations'];high_caps=upper['cap_evaluations']
    def cap_key(caps):return [(r['cap_id'],r['triggered'],r['maximum_percentage']) for r in caps]
    invariant=lower['post_cap_percentage']==upper['post_cap_percentage'] and cap_key(low_caps)==cap_key(high_caps) and neutral['cap_invariant']
    result['missing_data_bounds']['lower']=deepcopy(lower);result['missing_data_bounds']['upper']=deepcopy(upper)
    result['missing_data_bounds']['stable_percentage']=lower['post_cap_percentage']==upper['post_cap_percentage']
    result['missing_data_bounds']['stable_cap_outcome']=cap_key(low_caps)==cap_key(high_caps) and neutral['cap_invariant']
    if not invariant:
        for field in ('base_percentage','pre_cap_percentage','post_cap_percentage','dimension_percentage','weighted_contribution','substantive_selectivity_percentage','substantive_points_out_of_10'):result[field]=None
        result['status']='not_scored_insufficient_evidence';result['cap_evaluations']=[];result['applied_cap']=None
        result['components'][0].update(percentage=None,normalized_value=None,raw_numerator=None,raw_denominator=None)
    unknown=[r for r in applicable_rows if r['treatment_class'] is None]
    known=[r for r in applicable_rows if r['treatment_class'] in core.SELECTIVITY_CREDIT]
    d=result['denominators']['components'][0]
    missing=len(ledgers['locator_not_measured'])
    interval={side:neutral['applicability_interval'][side]+missing for side in ('lower','upper')}
    fixed=interval['lower']==interval['upper']
    if unknown:
        # Scenarios cannot masquerade as measured rows or confirmed exclusions.
        exclusions={}
        for row in rows:
            if row in known or row in unknown:continue
            key='absent_owned_by_reliability' if row['treatment_class']=='absent' else 'scope_or_ambiguity_owned_elsewhere'
            exclusions[key]=exclusions.get(key,0)+1
        d.update(original=ledgers['locator_original'],applicable=interval['lower'] if fixed else None,
                 measured=len(known),semantic_unresolved=len(unknown),
                 semantic_unresolved_applicability=neutral['semantic_unresolved_applicability'],
                 applicability_interval=interval,excluded=ledgers['locator_original']-interval['upper'] if fixed else None,
                 measurement_coverage=core.decimal_text(core.rate(len(known),interval['upper'])) if fixed else None,
                 small_denominator_exception=False,exclusion_reasons=exclusions)
        d['defined_zero_rule']=low['denominators']['components'][0]['defined_zero_rule'] if neutral['cap_invariant'] else None
        d['provisionally_scoreable']=bool(d['defined_zero_rule']) or (fixed and core.rate(len(known),interval['upper'])>=Decimal('.95'))
        result['components'][0].update(raw_numerator=None,raw_denominator=None)
        if not d['provisionally_scoreable']:
            result.update(status='not_scored_insufficient_evidence',dimension_percentage=None,weighted_contribution=None)
    result['raw_status_counts']={key:sum(r['treatment_class']==key for r in known) for key in core.SELECTIVITY_CREDIT}
    result['raw_status_counts'].update(semantic_unresolved=len(unknown),uninspectable=d['uninspectable'],not_measured=missing)
    def serialize(value):
        if isinstance(value,Decimal):return core.decimal_text(value)
        if isinstance(value,dict):return {k:serialize(v) for k,v in value.items()}
        return value
    result['semantic_uncertainty']={'label':LABEL,'treatment_envelope':serialize(neutral),'central_is_invariant':invariant,'assessment_sufficiency_restored_by_numeric_invariance':False}
    return result
