"""Cross-field checks for V10; V9 validators retain their historical meaning."""
from copy import deepcopy
from v10_migration import GATE_IDS


def contract_errors(document):
    errors = candidate_defect_errors(document)
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
    return errors
