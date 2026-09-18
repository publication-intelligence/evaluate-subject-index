"""V8.2 zero-fit and destination-resolution gates use direct audited evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dimension_score_v8_cli as cli
import policy_cli
import scoring_core as core
from schema_validation import schema_errors
import web_projection
import test_v8_completion as completion
from test_critical_gates import defect


def evidence(*, fit='no_fit', judgment='unsupported', treatment='absent', resolution='no_valid_destination'):
    locator = {'locator_id':'LOC-ONE','path_id':'PATH-ONE','complete_heading_path':['A'],
        'document_page':1,'source_page_label':'1','source_scope_status':'indexable',
        'treatment_class':treatment,'complete_path_fit':fit,'judgment':judgment,
        'evidence_summary':'Private source inspection.','fit_rationale':'The complete heading has no support.',
        'evidence_ids':['EVID-LOC'],'confidence':'high','error_codes':['LOC_POS'],'severity':'minor'}
    reference = {'reference_id':'XREF-ONE','judgment':'unsupported','summary':'Frozen target audit.',
        'severity':'minor','confidence':'high','evidence_ids':['EVID-XREF']}
    if resolution is not None:
        reference['target_resolution'] = {'status':resolution,'reference_type':'see also','target_display':'B',
            'resolved_path_ids': ['PATH-TARGET'] if resolution in {'valid_destination','defective_but_identifiable_destination'} else [],
            'evidence_ids':['EVID-TARGET'],'rationale':'Confirmed from the complete delivered index.'}
    structure = {'defects':[],'uncertainties':[], 'cross_reference_judgments':[reference],
        'candidate_denominator':{'cross_reference_ids':['XREF-ONE'],'nodes':[]},
        'full_scope_attestation':{'complete':True}}
    calculation = {'dimensions':[{'dimension_id':'page_reference_reliability','reliability_provenance':{
        'original_locator_denominator':1,'uninspectable_locator_count':0,
        'locator_utility_assignments':[{'locator_id':'LOC-ONE','fit_category':fit,'locator_severity':'minor'}],
        'locator_path_bindings':{'LOC-ONE':'PATH-ONE'}}}]}
    inventory = {'paths':[{'path_id':'PATH-ONE'},{'path_id':'PATH-TARGET'}],
        'cross_references':[{'reference_id':'XREF-ONE','reference_type':'see also','target_display':'B'}]}
    return structure, calculation, [{'judgments':[locator]}], inventory


def outcomes(data):
    structure, calculation, documents, inventory = data
    proof = cli._destination_gate_evidence(structure, calculation, documents, inventory)
    policy = {'critical_gates':[{'gate_id':id,'description':description} for id,description in policy_cli.CRITICAL_GATES]}
    gates = cli._critical_gate_outcomes(policy, structure, calculation, destination_evidence=proof)
    return {row['gate_id']:row for row in gates}, proof[2]


class WrongDestinationTests(unittest.TestCase):
    def test_registered_score_and_public_bundle_keep_arithmetic_separate(self):
        from structure_audit import id_set_hash
        fixture = completion.CurrentV8CompletionTests(); fixture.setUp()
        try:
            fixture.add_cross_reference_record_for_existing_heading()
            structure = json.loads(fixture.structure_path.read_text())
            structure['candidate_denominator'].update(cross_reference_ids=['XREF-001'], cross_reference_count=1,
                cross_reference_id_set_sha256=id_set_hash(['XREF-001']))
            structure['metrics']['cross_references'] = 1
            structure['scoring_context']['cross_reference_applicability'] = {
                'status':'applicable', 'basis_code':'delivered_references', 'delivered_reference_count':1,
                'warranted_reference_obligation_count':0, 'warranted_reference_obligation_ids':[], 'reference_defect_ids':[]}
            row = evidence()[0]['cross_reference_judgments'][0]
            row.update(reference_id='XREF-001')
            row['target_resolution']['target_display'] = 'Missing target'
            structure['cross_reference_judgments'] = [{k:v for k,v in row.items() if k != 'target_resolution'}]
            fixture.write('structure-audit.v5.json',structure)
            registered = fixture.run_cli('register-structure','--state',str(fixture.state_path),'--input',str(fixture.structure_path))
            self.assertEqual(0, registered.returncode, registered.stdout)
            state = json.loads(fixture.state_path.read_text())
            for kind in ('candidate_index','item_inventory','structure_audit'):
                record = next(r for r in state['artifacts'] if r['artifact_type']==kind)
                path = fixture.root/record['path']; document=json.loads(path.read_text())
                if kind=='candidate_index':
                    reference=document['records'][-1]['cross_references'][0]
                    reference.update(target='Missing target',target_path_id=None)
                elif kind=='item_inventory':
                    document['cross_references'][0].update(target_display='Missing target',target_path_id=None)
                else:
                    document['cross_reference_judgments']=[row]
                fixture.write(record['path'],document)
                record['sha256']=completion.file_hash(path)
                record['artifact_id']=completion.state_cli.artifact_id(record['path'],record['sha256'])
                if kind=='candidate_index': state['candidate']['normalized_sha256']=record['sha256']
            fixture.state_path.write_text(json.dumps(state))
            loaded, inventory, *_ = cli._calculation_loaded_from_state(state,fixture.state_path,fixture.root/'input.json')
            calculation = cli.calculate_loaded(loaded)
            without_proof=deepcopy(loaded)
            del without_proof['structure']['cross_reference_judgments'][0]['target_resolution']
            self.assertEqual(calculation,cli.calculate_loaded(without_proof))
            proof=cli._destination_gate_evidence(loaded['structure'],calculation,loaded['locator_documents'],inventory)
            missing=cli._destination_gate_evidence(without_proof['structure'],calculation,loaded['locator_documents'],inventory)
            self.assertEqual('sufficient',proof[2]['status'])
            self.assertEqual('indeterminate',missing[2]['status'])
            for command in ('score','build-report'):
                result=fixture.run_cli(command,'--state',str(fixture.state_path))
                self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            result=json.loads((fixture.root/'scoring/evaluation-result.v12.json').read_text())
            gate=next(g for g in result['critical_gates'] if g['gate_id']=='GATE-BROKEN-REFERENCE')
            self.assertTrue(gate['triggered'])
            state=json.loads(fixture.state_path.read_text())
            projection_record=next(r for r in state['artifacts'] if r.get('schema_version')=='ohfr-v8-canonical-web-projection-v1')
            projection=json.loads((fixture.root/projection_record['path']).read_text())
            self.assertEqual('not_publication_ready',projection['score_views']['views'][0]['readiness']['status'])
        finally:
            fixture.tearDown()

    def test_single_wrong_locator_and_broken_see_or_see_also_gate_without_defects(self):
        for kind in ('see','see also'):
            data = evidence()
            data[0]['cross_reference_judgments'][0]['target_resolution']['reference_type'] = kind
            data[3]['cross_references'][0]['reference_type'] = kind
            gates, assessment = outcomes(data)
            self.assertEqual('sufficient', assessment['status'])
            for gate_id, identity in [('GATE-WRONG-LOCATOR','LOC-ONE'),('GATE-BROKEN-REFERENCE','XREF-ONE')]:
                gate = gates[gate_id]
                self.assertTrue(gate['triggered'])
                self.assertEqual([], gate['defect_ids'])
                self.assertEqual([identity], gate['affected_evidence_ids'])
                self.assertTrue(gate['direct_destination_evidence'][0]['evidence_ids'])
                self.assertIn('one item is sufficient', gate['threshold_reason'])
                self.assertNotIn('Private source inspection', json.dumps(gate))

    def test_partial_mismatch_weak_treatment_and_generic_unsupported_are_not_zero_fit(self):
        for fit, judgment, treatment in [('material_partial_fit','partially_supported','mixed'),
            ('material_mismatch','unsupported','substantive'), ('severe_mismatch','unsupported','passing_mention'),
            ('exact_fit','unsupported','passing_mention')]:
            data = evidence(fit=fit, judgment=judgment, treatment=treatment, resolution='valid_destination')
            gates, _ = outcomes(data)
            self.assertFalse(gates['GATE-WRONG-LOCATOR']['triggered'], fit)
            self.assertFalse(gates['GATE-BROKEN-REFERENCE']['triggered'])

    def test_defective_but_identifiable_target_keeps_partial_correctness(self):
        data = evidence(fit='exact_fit', judgment='supported', treatment='substantive', resolution='defective_but_identifiable_destination')
        data[0]['cross_reference_judgments'][0]['judgment'] = 'partially_supported'
        gates, assessment = outcomes(data)
        self.assertEqual('sufficient', assessment['status'])
        self.assertFalse(any(g['triggered'] for g in gates.values()))
        result = {'critical_gates':list(gates.values()),'gate_assessment':assessment}
        self.assertEqual('publication_ready',web_projection.publication_readiness(result)['status'])

    def test_missing_or_uncertain_reference_resolution_blocks_affirmative_readiness(self):
        for resolution in (None,'uncertain'):
            for judgment in ('partially_supported','unsupported','uninspectable','not_measured'):
                data = evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution=resolution)
                data[0]['cross_reference_judgments'][0]['judgment'] = judgment
                gates, assessment = outcomes(data)
                self.assertFalse(any(g['triggered'] for g in gates.values()))
                self.assertEqual('indeterminate', assessment['status'])
                self.assertEqual(['XREF-ONE'],assessment['blockers'][0]['affected_item_ids'])
                result = {'critical_gates':list(gates.values()),'gate_assessment':assessment}
                self.assertEqual('indeterminate',web_projection.publication_readiness(result)['status'])

    def test_uncertain_uninspectable_wrong_source_and_incomplete_evidence_do_not_gate(self):
        for change in ('low','uninspectable','uncertainty','wrong_source','missing_evidence'):
            data = evidence(resolution='valid_destination')
            row = data[2][0]['judgments'][0]
            if change == 'low': row['confidence'] = 'low'
            if change == 'uninspectable': row.update(judgment='uninspectable',complete_path_fit='uninspectable',treatment_class='unavailable',source_scope_status='unavailable')
            if change == 'uncertainty': data[0]['uncertainties']=[{'uncertainty_id':'UNC-ONE','affected_item_ids':['LOC-ONE'],'summary':'Unresolved support.'}]
            if change == 'wrong_source': data[0]['defects']=[defect('DEFECT-SPAN','scope_failure','LOC-ONE')]
            if change == 'missing_evidence': row['evidence_ids']=[]
            gates, assessment = outcomes(data)
            self.assertFalse(any(g['triggered'] for g in gates.values()),change)
            self.assertEqual('indeterminate',assessment['status'])

    def test_missing_supplemental_route_is_not_a_delivered_broken_reference(self):
        data=evidence(fit='material_partial_fit',judgment='partially_supported',treatment='mixed')
        data[0]['cross_reference_judgments']=[]
        data[3]['cross_references'][0]['target_path_id']='PATH-TARGET'
        data[0]['defects']=[defect('DEFECT-MISSING','misleading_access_route','TASK-ONE')]
        gates, assessment=outcomes(data)
        self.assertFalse(any(g['triggered'] for g in gates.values()))
        self.assertEqual('sufficient',assessment['status'])

    def test_unresolved_inventory_target_cannot_hide_behind_full_scope_attestation(self):
        data=evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='valid_destination')
        data[0]['cross_reference_judgments']=[]
        data[3]['cross_references'][0]['target_path_id']=None
        gates,assessment=outcomes(data)
        self.assertFalse(gates['GATE-BROKEN-REFERENCE']['triggered'])
        self.assertEqual('indeterminate',assessment['status'])
        self.assertEqual(['XREF-ONE'],assessment['blockers'][0]['affected_item_ids'])

    def test_registered_reviewed_binding_clears_only_its_exact_supported_references(self):
        data=evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='valid_destination')
        data[0]['cross_reference_judgments']=[]
        data[3]['cross_references'][0]['target_path_id']=None
        reviewed={'bindings':{'XREF-ONE':{
            'reference_id':'XREF-ONE','status':'valid_destination','reference_type':'see also',
            'target_display':'B','resolved_path_ids':['PATH-TARGET'],
            'evidence_ids':['EVID-TARGET'],'rationale':'Reviewed.'}}}
        proof=cli._destination_gate_evidence(*data,reviewed_reference_bindings=reviewed)
        self.assertEqual('sufficient',proof[2]['status'])

        data[0]['candidate_denominator']['cross_reference_ids'].append('XREF-TWO')
        data[3]['cross_references'].append({'reference_id':'XREF-TWO','reference_type':'see',
            'target_display':'C','target_path_id':None})
        proof=cli._destination_gate_evidence(*data,reviewed_reference_bindings=reviewed)
        self.assertEqual('indeterminate',proof[2]['status'])
        self.assertEqual(['XREF-TWO'],proof[2]['blockers'][0]['affected_item_ids'])

    def test_reviewed_binding_does_not_suppress_genuine_partial_or_unsupported_rows(self):
        for judgment in ('partially_supported','unsupported'):
            data=evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='no_valid_destination' if judgment=='unsupported' else 'valid_destination')
            data[0]['cross_reference_judgments'][0]['judgment']=judgment
            reviewed={'bindings':{'XREF-ONE':{}}}
            proof=cli._destination_gate_evidence(*data,reviewed_reference_bindings=reviewed)
            if judgment == 'unsupported':
                self.assertEqual(['XREF-ONE'],[row['reference_id'] for row in proof[1]])
            else:
                self.assertEqual([],proof[1])
            self.assertEqual('sufficient',proof[2]['status'])

    def test_no_duplicate_gate_for_same_direct_failure_with_separate_major_defect(self):
        data=evidence()
        data[0]['defects']=[defect('DEFECT-LOC','generic','LOC-ONE',code='LOC_POS'),defect('DEFECT-XREF','unsupported_reference','XREF-ONE')]
        data[1]['dimensions'][0]['reliability_provenance']['locator_utility_assignments'][0]['locator_severity']='major'
        gates,_=outcomes(data)
        self.assertEqual({'GATE-WRONG-LOCATOR','GATE-BROKEN-REFERENCE'},{k for k,g in gates.items() if g['triggered']})

    def test_mixed_defect_retains_other_material_failure_without_duplicate_ids(self):
        data=evidence(resolution='valid_destination')
        material=defect('DEFECT-MIXED','generic','LOC-ONE',code='LOC_POS')
        material['affected_item_ids'].append('LOC-TWO')
        data[0]['defects']=[material]
        data[1]['dimensions'][0]['reliability_provenance']['locator_utility_assignments'].append(
            {'locator_id':'LOC-TWO','fit_category':'severe_mismatch','locator_severity':'major'})
        second=deepcopy(data[2][0]['judgments'][0])
        second.update(locator_id='LOC-TWO',complete_path_fit='severe_mismatch',treatment_class='substantive')
        data[2][0]['judgments'].append(second)
        gates,_=outcomes(data)
        self.assertEqual(['LOC-ONE'],gates['GATE-WRONG-LOCATOR']['affected_evidence_ids'])
        self.assertTrue(gates['GATE-GROUNDING']['triggered'])
        self.assertEqual(['LOC-TWO'],gates['GATE-GROUNDING']['affected_evidence_ids'])
        self.assertEqual(['LOC-TWO'],[r['locator_id'] for r in gates['GATE-GROUNDING']['qualifying_locator_evidence']])

    def test_resolution_must_match_delivered_reference_and_paths(self):
        for change in ('target','type','path'):
            data=evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='valid_destination')
            resolution=data[0]['cross_reference_judgments'][0]['target_resolution']
            if change=='target': resolution['target_display']='Invented'
            if change=='type': resolution['reference_type']='see'
            if change=='path': resolution['resolved_path_ids']=['PATH-MISSING']
            _,assessment=outcomes(data)
            self.assertEqual('indeterminate',assessment['status'])

    def test_v81_policy_and_calculation_identity_are_not_reinterpreted(self):
        from test_v8_provenance import PolicyIdentityTests
        policy=policy_cli.build_policy(PolicyIdentityTests().policy_input())
        policy['policy_profile']['id']='subject-index-standard-policy-v8.1'
        policy['policy_sha256']=policy_cli.canonical_hash(policy,'policy_sha256')
        with self.assertRaises(core.CalculationError): cli.validate_v8_policy(policy)
        policy=policy_cli.build_policy(PolicyIdentityTests().policy_input())
        policy['critical_gates']=[g for g in policy['critical_gates'] if g['gate_id'] != 'GATE-WRONG-LOCATOR']
        policy['policy_sha256']=policy_cli.canonical_hash(policy,'policy_sha256')
        with self.assertRaises(core.CalculationError): cli.validate_v8_policy(policy)
        self.assertEqual('subject-index-rubric-v8.2',cli.RUBRIC_VERSION)
        self.assertEqual('subject-index-dimension-calculation-v7',cli.CALCULATION_PROFILE)

    def test_native_schema_accepts_resolution_and_rejects_empty_proof(self):
        fixture=completion.CurrentV8CompletionTests(); fixture.setUp()
        try:
            structure=json.loads(fixture.structure_path.read_text())
            # This fixture is an older wrapper until register-structure upgrades it.
            completed=fixture.run_cli('register-structure','--state',str(fixture.state_path),'--input',str(fixture.structure_path))
            self.assertEqual(0,completed.returncode,completed.stdout)
            state=json.loads(fixture.state_path.read_text())
            record=next(r for r in state['artifacts'] if r['stage']=='structure_audit')
            structure=json.loads((fixture.root/record['path']).read_text())
            structure['cross_reference_judgments']=evidence()[0]['cross_reference_judgments']
            self.assertEqual([],schema_errors(structure,'structure-audit-v6.schema.json'))
            structure['cross_reference_judgments'][0]['target_resolution']['evidence_ids']=[]
            self.assertTrue(schema_errors(structure,'structure-audit-v6.schema.json'))
        finally: fixture.tearDown()
