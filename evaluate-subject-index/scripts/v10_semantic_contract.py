"""Cross-field validation for additive semantic artifacts only."""
from decimal import Decimal
from v10_semantic import LABEL,NONKEEP,combined_errors


def contract_errors(document):
    errors=[]
    semantic_seen=False
    def visit(value,path='root'):
        nonlocal semantic_seen
        if isinstance(value,list):
            for i,row in enumerate(value):visit(row,f'{path}.{i}')
        elif isinstance(value,dict):
            for key,row in value.items():visit(row,f'{path}.{key}')
            if value.get('semantic_uncertainty'):semantic_seen=True
            if isinstance(value.get('locator_utility'),dict) and value.get('judgment')!=value['locator_utility']['judgment']:
                errors.append(f'{path}: item judgment differs from utility evidence')
            resolution=value.get('axis_resolution')
            if (value.get('disposition')=='semantic_unresolved' or value.get('judgment') in {'semantic_unresolved',NONKEEP}) and not resolution and 'locator_utility' not in value:
                errors.append(f'{path}: missing semantic resolution')
            if resolution and 'judgment' in value:
                if 'rating_credit' not in value:
                    errors.extend(f'{path}: {e}' for e in combined_errors(value))
                else:
                    raw={key:value[key] for key in ('locator_id','judgment','treatment_class','source_scope_status','error_codes','axis_resolution')}
                    raw.update(complete_path_fit=None if resolution['complete_path_fit']=='unresolved' else value['fit_category'],severity=value['locator_severity'])
                    if value['judgment']==NONKEEP:raw['keep_decision']=value.get('keep_decision')
                    errors.extend(f'{path}: {e}' for e in combined_errors(raw))
                    for axis,field in [('treatment','treatment_score'),('complete_path_fit','fit_score'),('keep','rating_credit')]:
                        if (value[field] is None)!=(resolution[axis]=='unresolved'):
                            errors.append(f'{path}: {axis} credit contradicts resolution')
                    expected_keep=None if value['judgment']=='semantic_unresolved' else '1' if value['judgment']=='supported' else '0'
                    if value['rating_credit']!=expected_keep:errors.append(f'{path}: known keep credit changed')
                    if value['disposition']!='semantic_unresolved' or value['disposition_reason']!=LABEL:
                        errors.append(f'{path}: semantic disposition mislabeled')
                    if value['judgment']==NONKEEP and (value.get('keep_decision')!='not_kept' or resolution.get('judgment_subtype')!='unresolved'):
                        errors.append(f'{path}: aggregate known nonkeep is incomplete')
                    t,f=value['treatment_score'],value['fit_score']
                    expected_diagnostic=None if t is None or f is None else min(Decimal(t),Decimal(f))
                    actual=None if value['diagnostic_credit'] is None else Decimal(value['diagnostic_credit'])
                    if expected_diagnostic!=actual:errors.append(f'{path}: diagnostic minimum does not reconstruct')
                    for axis,bound in value['axis_uncertainty_bounds'].items():
                        lo,hi=Decimal(bound['lower']),Decimal(bound['upper'])
                        if not Decimal(0)<=lo<=hi<=Decimal(1):errors.append(f'{path}: invalid {axis} interval')
                    expected_bounds={'lower':'0','upper':'1'} if expected_keep is None else {'lower':expected_keep,'upper':expected_keep}
                    if value['rating_credit_uncertainty_bounds']!=expected_bounds or value['axis_uncertainty_bounds']['keep']!=expected_bounds:
                        errors.append(f'{path}: keep bounds contradict established facts')
            if 'semantic_unresolved' in value and {'original','applicable','measured','uninspectable','not_measured'} <= value.keys():
                upper=value['measured']+value['uninspectable']+value['not_measured']+value['semantic_unresolved']
                interval=value.get('applicability_interval',{'lower':upper,'upper':upper})
                if interval['upper']!=upper or interval['lower']!=upper-value.get('semantic_unresolved_applicability',0):
                    errors.append(f'{path}: semantic applicability does not reconstruct')
                fixed=interval['lower']==upper
                if value['applicable']!=(upper if fixed else None) or value['excluded']!=(value['original']-upper if fixed else None):
                    errors.append(f'{path}: unresolved applicability treated as a central bucket')
                if sum(value['exclusion_reasons'].values())!=value['original']-upper:
                    errors.append(f'{path}: factual exclusions do not reconstruct')
                if value['semantic_unresolved'] and value['small_denominator_exception']:
                    errors.append(f'{path}: semantic rows cannot use physical small-denominator exception')
            if 'dimension_id' in value and 'cap_evaluations' in value and not value['cap_evaluations'] and not value.get('semantic_uncertainty'):
                errors.append(f'{path}: missing cap evaluations without semantic uncertainty')
    try:visit(document)
    except (KeyError,TypeError,ValueError,ArithmeticError) as exc:errors.append(f'Invalid semantic contract: {exc}')
    if semantic_seen and "gate_assessment" in document:
        assessment=document["gate_assessment"]
        if assessment["status"]!="indeterminate" or not any(r.get("semantic_unknown_axes") for r in assessment["blockers"]):
            errors.append("Semantic uncertainty cannot restore sufficient gate assessment")
    return errors
if __name__ == "__main__":
    __import__("runtime_profile").require_public_cli()
