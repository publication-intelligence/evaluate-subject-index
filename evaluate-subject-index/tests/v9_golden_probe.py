"""Emit deterministic boundary evidence under an explicitly selected runtime."""
import sys
from pathlib import Path
from decimal import Decimal
from copy import deepcopy
import json
from unittest import mock

scripts=Path(sys.argv[2]) if len(sys.argv)>2 else Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
if sys.argv[1] in {'v9','v10'}:
    import runtime_profile
    (runtime_profile.select_v10 if sys.argv[1]=='v10' else runtime_profile.select_v9)()
import scoring_core as core
import dimension_score_v8_cli as scoring
# These helpers only construct synthetic evidence; target runtime is imported first.
from test_v8_sensitivity_adversarial import reliability_ledgers, state
from test_wrong_destination_gates import evidence, outcomes

result={'density_bands':{},'selectivity_caps':{},'reliability':{},'selectivity':{},'gates':{},'rounding':{}}
for point in ('0','.000001','1.999999','2','2.000001','2.999999','3','3.000001','3.999999','4','4.000001','5.999999','6','6.000001','9.999999','10','10.000001','11.999999','12','12.000001','14.999999','15','15.000001','17.999999','18','18.000001','23.999999','24','24.000001'):
    result['density_bands'][point]=str(core.density_metric_rating(Decimal(point),Decimal(4),Decimal(6),Decimal(10),Decimal(12)))
for rate in ('0.049999','0.05','0.050001','0.149999','0.15','0.150001','0.299999','0.30','0.300001','0.499999','0.50','0.500001'):
    for count,unit in ((9,'0.25'),(10,'0.249999'),(10,'0.25')):
        result['selectivity_caps'][f'{rate}/{count}/{unit}']=core.selectivity_cap(Decimal(rate),count,Decimal(unit))
for name,judgment,treatment,fit in [('kept','supported','substantive','exact_fit'),('partial','partially_supported','mixed','material_partial_fit'),('no_fit','unsupported','absent','no_fit'),('weak','unsupported','passing_mention','exact_fit'),('unknown','uninspectable','unavailable','uninspectable')]:
    record=state(judgment,treatment,fit=fit,scope='unavailable' if name=='unknown' else 'indexable')
    ledgers=reliability_ledgers([record])
    result['reliability'][name]=scoring.calculate_reliability(ledgers,'full')
    if name!='no_fit':
        loc=ledgers['locators'][0];loc['path_id']='PATH-ONE'
        ledgers['structure']={'density':{'chapter_measurements':[{'chunk_id':'CHUNK-001','indexable_source_words':101,'locator_bearing_heading_paths':1,'locator_occurrences':1}]}}
        result['selectivity'][name]=core.calculate_selectivity(ledgers,'full')
# Existing 28-digit Decimal operation order is significant at the last place.
ledger=reliability_ledgers([state('supported','substantive',locator_id='LOC-A'),state('unsupported','passing_mention',locator_id='LOC-B'),state('unsupported','passing_mention',locator_id='LOC-C')])
for i,row in enumerate(ledger['locators']):row['path_id']=f'PATH-{i}'
ledger['structure']={'density':{'chapter_measurements':[{'chunk_id':'CHUNK-001','indexable_source_words':120,'locator_bearing_heading_paths':3,'locator_occurrences':3}]}}
result['selectivity']['operation_order']=core.calculate_selectivity(ledger,'full')
for fit,judgment,treatment in [('no_fit','unsupported','absent'),('material_partial_fit','partially_supported','mixed'),('exact_fit','unsupported','passing_mention')]:
    for resolution in ('no_valid_destination','valid_destination','defective_but_identifiable_destination',None):
        result['gates'][f'{fit}/{resolution}']=outcomes(evidence(fit=fit,judgment=judgment,treatment=treatment,resolution=resolution))
# Exercise the actual final aggregation at both sides of the half-up boundary.
for last in ('1.004999','1.005','1.005001'):
    dims=[{'dimension_id':name,'status':'scored','input_roles':['structure_audit'],'weighted_contribution':value,'cap_evaluations':[],'missing_data_bounds':{'lower':{'cap_evaluations':[]},'upper':{'cap_evaluations':[]}}} for name,value in zip(core.WEIGHTS,['1.004']*5+[last])]
    ledgers={'identity':{field:'a'*64 for field in core.CALCULATION_EVIDENCE_IDENTITY_FIELDS},'expected_subject_ids':[]}
    loaded={'config':{'evaluation_id':'EVAL-BOUNDARY','audit_mode':'full'},'input_artifacts':[{'role':'policy','path':'policy.json','sha256':'b'*64,'schema_version':'subject-index-evaluation-policy-v4'}],'structure':{'candidate_denominator':{},'full_scope_attestation':{},'locator_architecture':{},'uncertainties':[]}}
    fit_report={'invalid_or_contradictory_state':[],'unresolved_complete_path_fit':[],'compatibility_classifications':[],'group_counts':{},'unresolved_reason_counts':{}}
    from contextlib import ExitStack
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(scoring,'preflight_loaded',return_value=(ledgers,[])))
        stack.enter_context(mock.patch.object(scoring,'locator_fit_preflight',return_value=fit_report))
        for module,name,value in [(core,'calculate_coverage',dims[0]),(core,'calculate_selectivity',dims[1]),(core,'calculate_concept',dims[2]),(scoring,'calculate_reliability',dims[3]),(core,'calculate_findability',dims[4]),(core,'calculate_mechanics',dims[5])]:
            stack.enter_context(mock.patch.object(module,name,return_value=value))
        calculated=scoring.calculate_loaded(loaded)
    result['rounding'][last]={'overall_percentage':calculated['overall_percentage'],'final_rounding':calculated['final_rounding']}
# Representation changes are explicitly enumerated. No judgments, caps, bounds,
# gates, weights, percentages, contributions, or precision are discarded.
additions={'weighted_percentage_numerator','total_weighted_percentage_numerator','total_indexable_source_words','substantive_selectivity_percentage','density_points_out_of_5','substantive_points_out_of_10','density_fit_percentage'}
def equivalent(value):
    if isinstance(value,dict):return {k:equivalent(v) for k,v in value.items() if k not in additions}
    if isinstance(value,(list,tuple)):return [equivalent(v) for v in value]
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,str) and value.startswith(('subject-index-dimension-calculation-v8:','subject-index-dimension-calculation-v9:')):return value.replace('-v8:', '-v7:',1).replace('-v9:', '-v7:',1)
    return value
print(json.dumps(equivalent(result),sort_keys=True,indent=2))
