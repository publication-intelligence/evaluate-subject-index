"""Axis-preserving semantic uncertainty over the unchanged resolved utility rules."""
from copy import deepcopy
from decimal import Decimal
from itertools import product

LABEL = 'Semantically unresolved after inspection'
NONKEEP = 'not_kept_subtype_unresolved'
AXES = {'treatment':'treatment_class','complete_path_fit':'complete_path_fit','keep':'judgment'}


def resolved_possibilities(row):
    """Permitted historical states consistent with every actually known fact."""
    import locator_utility as utility
    treatment=[row['treatment_class']] if row['treatment_class'] is not None else sorted(utility.VALID_TREATMENT_CLASSES-{'unavailable'})
    fit=[row['complete_path_fit']] if row['complete_path_fit'] is not None else sorted(utility.FIT_SCORES)
    keep=[row['judgment']] if row['judgment'] not in {'semantic_unresolved',NONKEEP} else ['supported','partially_supported','unsupported']
    possible=[]
    for t,f,k in product(treatment,fit,keep):
        value=deepcopy(row);value.pop('axis_resolution',None);value.pop('keep_decision',None)
        value.update(treatment_class=t,complete_path_fit=f,judgment=k)
        if not utility.combined_state_errors(value):possible.append(value)
    return possible


def combined_errors(row,defects=()):
    import locator_utility as utility
    errors=[]
    resolution=row.get('axis_resolution')
    if not isinstance(resolution,dict):return ['missing:axis_resolution']
    if not {*AXES,'inspection_completed','reason_category','rationale'} <= set(resolution) or set(resolution)-{*AXES,'inspection_completed','reason_category','rationale','dependent_reference_ids','judgment_subtype'}:
        errors.append('invalid:axis_resolution_fields')
    aggregate=row.get('judgment')==NONKEEP
    if aggregate:
        if row.get('keep_decision')!='not_kept' or resolution.get('judgment_subtype')!='unresolved':errors.append('invalid:aggregate_nonkeep_representation')
    elif 'judgment_subtype' in resolution or 'keep_decision' in row:
        errors.append('invalid:aggregate_nonkeep_fields_without_aggregate')
    if resolution.get('inspection_completed') is not True:errors.append('invalid:inspection_not_completed')
    if resolution.get('reason_category') not in {'unresolved_referent','unresolved_relationship'}:errors.append('invalid:semantic_reason_category')
    if not isinstance(resolution.get('rationale'),str) or not resolution['rationale'].strip():errors.append('missing:semantic_rationale')
    if row.get('source_scope_status') not in {'indexable','excluded'}:errors.append('invalid:semantic_scope_must_be_known')
    if row.get('judgment')=='uninspectable' or row.get('treatment_class')=='unavailable':errors.append('invalid:physical_state_in_semantic_branch')
    for axis,field in AXES.items():
        unknown=row.get(field) == 'semantic_unresolved' if axis=='keep' else row.get(field) is None
        if resolution.get(axis) != ('unresolved' if unknown else 'known'):errors.append('inconsistent:axis_resolution_'+axis)
    if not any(resolution.get(a)=='unresolved' for a in AXES):errors.append('invalid:semantic_branch_requires_unknown_axis')
    errors.extend(utility._defect_errors(str(row.get('locator_id')),defects))
    if not errors:
        try:
            worlds=resolved_possibilities(row)
            if not worlds:errors.append('inconsistent:no_permitted_resolved_state')
            if aggregate and {r['judgment'] for r in worlds}!={'partially_supported','unsupported'}:
                errors.append('inconsistent:aggregate_requires_plural_nonkeep_only_subtypes')
            for axis,field in AXES.items():
                values={r['judgment']=='supported' if axis=='keep' else r[field] for r in worlds}
                if resolution[axis]=='unresolved' and len(values)<2:
                    errors.append('inconsistent:unresolved_axis_is_logically_resolved_'+axis)
        except (KeyError,TypeError):errors.append('invalid:missing_native_axis_fields')
    return sorted(set(errors))


def assign(row,defects=()):
    import locator_utility as utility
    errors=combined_errors(row,defects)
    if errors:raise ValueError(';'.join(errors))
    states=resolved_possibilities(row)
    utilities=[utility.assign_locator_utility(value,defects) for value in states]
    known=row['axis_resolution']
    t=utilities[0].treatment_score if known['treatment']=='known' else None
    f=utilities[0].fit_score if known['complete_path_fit']=='known' else None
    k=utilities[0].rating_credit if known['keep']=='known' else None
    diagnostic=min(t,f) if t is not None and f is not None else None
    bounds={}
    for key,attribute in [('treatment','treatment_score'),('complete_path_fit','fit_score'),('diagnostic','diagnostic_credit'),('keep','rating_credit')]:
        values=[getattr(value,attribute) for value in utilities]
        bounds[key]={'lower':utility.decimal_text(min(values)),'upper':utility.decimal_text(max(values))}
    # The unresolved keep branch is always neutral0..1 by the adopted ruling.
    # Known keep facts retain their exact credit despite another unknown axis.
    if k is None:bounds['keep']={'lower':'0','upper':'1'}
    result=deepcopy(utilities[0])
    from dataclasses import replace
    return replace(result,judgment=row['judgment'],treatment_class=row['treatment_class'],
        inspectability=utility.inspectability_state(row['source_scope_status'],row['treatment_class']),treatment_category=utilities[0].treatment_category if t is not None else 'semantic_unresolved',
        treatment_score=t,fit_category=row['complete_path_fit'] if f is not None else 'semantic_unresolved',fit_score=f,
        treatment_rule_id=utilities[0].treatment_rule_id if t is not None else 'T-SEMANTIC-UNRESOLVED-BOUND',
        fit_rule_id=utilities[0].fit_rule_id if f is not None else 'F-SEMANTIC-UNRESOLVED-BOUND',
        mapping_rule_id='V10-AXIS-PRESERVING-SEMANTIC-UNCERTAINTY',fit_classification_source='native_axis_resolution',
        diagnostic_credit=diagnostic,diagnostic_grade=None if diagnostic is None else float(diagnostic*100),
        rating_credit=k,rating_rule_id=utilities[0].rating_rule_id if k is not None else 'R-SEMANTIC-UNRESOLVED-BOUND',
        disposition='semantic_unresolved',disposition_reason=LABEL,
        uncertainty_lower=Decimal(bounds['keep']['lower']),uncertainty_upper=Decimal(bounds['keep']['upper']),
        semantic_axis_resolution=deepcopy(row['axis_resolution']),axis_uncertainty_bounds=bounds)


def apply_axis_diagnostics(result,assignments,semantic_rows,semantic_keep):
    """Preserve factual axis observations and bound only the unknown axes."""
    import scoring_core as core
    provenance=result['reliability_provenance']
    provenance['semantic_unresolved_locator_count']=len(semantic_rows)
    provenance['semantic_unresolved_keep_count']=len(semantic_keep)
    provenance['axis_measurement_counts']={}
    pairs=[('treatment','treatment_score','mean_treatment_score','treatment_score_uncertainty','page_treatment_axis_diagnostic'),
           ('complete_path_fit','fit_score','mean_fit_score','fit_score_uncertainty','complete_path_fit_axis_diagnostic'),
           ('diagnostic','diagnostic_credit','mean_diagnostic_credit','diagnostic_credit_uncertainty','diagnostic_locator_credit_mean')]
    for axis,field,mean_key,bounds_key,component_id in pairs:
        known=[r for r in assignments if r[field] is not None]
        numerator=sum((Decimal(r[field]) for r in known),Decimal(0))
        central=numerator/len(known) if known else None
        lower=upper=Decimal(0)
        for r in assignments:
            if r[field] is not None:lo=hi=Decimal(r[field])
            else:
                interval=r.get('axis_uncertainty_bounds',{}).get(axis,{'lower':'0','upper':'1'})
                lo=Decimal(interval['lower']);hi=Decimal(interval['upper'])
            lower+=lo;upper+=hi
        total=len(assignments)
        prefix={'treatment':'treatment_score','complete_path_fit':'fit_score','diagnostic':'diagnostic_credit'}[axis]
        provenance[prefix+'_numerator']=core.decimal_text(numerator)
        provenance[prefix+'_denominator']=len(known)
        provenance[mean_key]=core.decimal_text(central)
        provenance[bounds_key]={'central':core.decimal_text(central),'lower':core.decimal_text(lower/total if total else Decimal(0)),'upper':core.decimal_text(upper/total if total else Decimal(0))}
        provenance['axis_measurement_counts'][axis]={'original':total,'measured':len(known),'semantic_unresolved':sum(r.get('disposition')=='semantic_unresolved' and r[field] is None for r in assignments),'uninspectable':sum(r['disposition']=='bounded' for r in assignments),'not_measured':sum(r['disposition']=='not_measured' for r in assignments)}
        for component in result['components']:
            if component['component_id']==component_id:
                component.update(raw_numerator=core.decimal_text(numerator),raw_denominator=str(len(known)),normalized_value=core.decimal_text(central))
    result['semantic_uncertainty']={'label':LABEL,'locator_count':len(semantic_rows),'keep_unresolved_count':len(semantic_keep),'assessment_sufficiency_restored_by_numeric_invariance':False}

    if semantic_keep and provenance['assessable_locator_denominator']==0:
        provenance['keep_precision']=None
        provenance['reliability_f1']=None
        provenance['keep_precision_uncertainty']['central']=None
        for component in result['components']:
            if component['component_id'] in {'keep_precision','reliability_f1'}:
                component['normalized_value']=None
                if component['component_id']=='reliability_f1':component.update(raw_numerator=None,raw_denominator=None)
        if result['dimension_percentage'] is None:
            for key in ('base_percentage','pre_cap_percentage','post_cap_percentage'):result[key]=None
            provenance['pre_cap_percentage']=None
