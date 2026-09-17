"""Cross-field checks for V10; V9 validators retain their historical meaning."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from v10_migration import GATE_IDS


def contract_errors(document):
    errors = candidate_defect_errors(document)
    if 'overall_score_ceiling' in document:
        ceiling=document['overall_score_ceiling'];triggered=[r for r in ceiling['cap_evaluations'] if r['triggered']]
        expected=min(triggered,key=lambda r:Decimal(r['maximum_percentage'])) if triggered else None
        if ceiling['applied_cap'] != (None if expected is None else {k:expected[k] for k in ('cap_id','maximum_percentage')}):
            errors.append('Applied overall ceiling is not the lowest triggered ceiling')
        pre=None if ceiling['pre_cap_overall_percentage'] is None else Decimal(ceiling['pre_cap_overall_percentage'])
        post=None if ceiling['post_cap_overall_percentage'] is None else Decimal(ceiling['post_cap_overall_percentage'])
        expected_post=None if pre is None else min(pre,Decimal(expected['maximum_percentage'])) if expected else pre
        if post!=expected_post:errors.append('Post-cap overall percentage does not reconstruct')
        if document.get('overall_percentage') is not None and post is not None and Decimal(str(document['overall_percentage']))!=post.quantize(Decimal('.01'),rounding=ROUND_HALF_UP):
            errors.append('Displayed overall percentage differs from exact post-cap score')
    if document.get('schema_version') == 'subject-index-evaluation-policy-v6':
        if tuple(row['gate_id'] for row in document['critical_gates']) != GATE_IDS:
            errors.append('V10 requires exactly its twelve ordered core quality gates')
    if 'evaluation_validity' in document:
        validity=document['evaluation_validity']
        expected_status='invalid' if any(row['outcome']=='invalid' for row in validity['blockers']) else 'indeterminate' if validity['blockers'] else 'valid'
        if validity['status'] != expected_status: errors.append('Evaluation validity contradicts typed blockers')
    if 'gate_assessment' in document:
        assessment=document['gate_assessment']
        if assessment['status'] != ('indeterminate' if assessment['blockers'] else 'sufficient'):
            errors.append('Gate assessment status contradicts its blockers')
    schema = document.get('schema_version')
    schema = {'subject-index-evaluation-result-v15':'subject-index-evaluation-result-v14','subject-index-web-report-v13':'subject-index-web-report-v12','ohfr-v10-canonical-web-projection-v2':'ohfr-v10-canonical-web-projection-v1'}.get(schema,schema)
    if schema in {'subject-index-evaluation-result-v14','subject-index-web-report-v12','ohfr-v10-canonical-web-projection-v1'}:
        from v10_consequences import outcome_fields
        source = document
        if schema == 'subject-index-web-report-v12':
            source = {**document, 'critical_gates': document['gate_status']['critical_gates']}
        if schema == 'ohfr-v10-canonical-web-projection-v1':
            source = {**document, 'critical_gates': document['score_views']['views'][0]['critical_gates']}
        if tuple(row['gate_id'] for row in source['critical_gates']) != GATE_IDS:
            errors.append('V10 core gate register is incomplete or contains an excluded gate')
        expected = outcome_fields(source)
        for key in expected:
            if document[key] != expected[key]: errors.append(f'{key} contradicts independent machine outcomes')
        if schema == 'ohfr-v10-canonical-web-projection-v1':
            if document['score_views']['views'][0]['readiness'] != expected['method_readiness']:
                errors.append('Score-view readiness contradicts V10 readiness')
            from v9_contract import contract_errors as percentage_errors
            proxy = deepcopy(document);proxy['schema_version'] = 'ohfr-v9-canonical-web-projection-v1'
            errors.extend(percentage_errors(proxy,allow_semantic=document.get('schema_version')=='ohfr-v10-canonical-web-projection-v2'))
    return errors


def candidate_defect_errors(document):
    errors=[]
    def visit(value):
        if isinstance(value,dict):
            if value.get('defect_kind') == 'scope_failure':
                errors.append('VALIDITY-SOURCE-SPAN: source binding failure cannot be recorded as a V10 candidate defect')
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(document)
    for defect in document.get('defects',[]) if isinstance(document,dict) else []:
        if (defect.get('severity') in {'major','critical'} and defect.get('code') in {'HED','SUB'}
                and defect.get('dimension_owner') == 'findability_navigation'
                and defect.get('retrieval_consequence') in {'blocks','misleads'}
                and not any(str(item).startswith('PATH-') for item in defect.get('affected_item_ids',[]))):
            errors.append(f"{defect.get('defect_id')}: independently evidenced destructive heading architecture must bind a delivered PATH")
    if isinstance(document,dict) and document.get('node_judgments') is not None:
        defects=document.get('defects',[])
        owners={'conceptual_stance_fidelity':'conceptual_stance_fidelity',
                'heading_access_architecture':'findability_navigation',
                'mechanics_consistency':'mechanics_consistency'}
        for node in document['node_judgments']:
            for component,owner in owners.items():
                status=node.get('component_judgments',{}).get(component,{}).get('status')
                if status in {'major_issues','fails'} and not any(
                    row.get('dimension_owner')==owner and node['node_id'] in row.get('affected_item_ids',[])
                    and row.get('severity') in {'major','critical'} for row in defects):
                    errors.append(f"{node['node_id']}: {component} {status} requires a corresponding major/critical defect record")
    return errors
