"""Uncertainty targets a proposition, not every item sharing its context path."""
from copy import deepcopy
import json
import unittest
from test_wrong_destination_gates import evidence, outcomes
import test_v8_completion as completion
import dimension_score_v8_cli as cli
from schema_validation import schema_errors
from structure_audit import StructureAuditError, validate_uncertainty_gate_scopes


def uncertainty(identity='UNC-ONE', affected=None):
    return {'uncertainty_id':identity,'affected_item_ids':affected or ['LOC-ONE','PATH-ONE'],
            'summary':'Preserved source-grounded uncertainty.','evidence_ids':['EVID-UNC'],
            'kind':'untrusted_legacy_description','status':'uncertain'}


def scope(kind, targets, identity='UNC-ONE'):
    return {'uncertainty_id':identity,'scope':kind,'target_ids':targets,
            'evidence_ids':['EVID-UNC'],'rationale':'Scope justified by the preserved evidence.'}


def two_locators():
    data=evidence(resolution='valid_destination')
    second=deepcopy(data[2][0]['judgments'][0]);second['locator_id']='LOC-TWO'
    data[2][0]['judgments'].append(second)
    data[1]['dimensions'][0]['reliability_provenance']['locator_utility_assignments'].append(
        {'locator_id':'LOC-TWO','fit_category':'no_fit','locator_severity':'minor'})
    return data


class UncertaintyGateScopeTests(unittest.TestCase):
    def test_atomic_locator_scope_does_not_expand_to_sibling_destinations(self):
        data=two_locators();original=uncertainty()
        data[0]['uncertainties']=[original]
        before=deepcopy(original)
        data[0]['uncertainty_gate_scopes']=[scope('locator_support',['LOC-ONE'])]
        gates,assessment=outcomes(data)
        self.assertEqual(['LOC-TWO'],gates['GATE-WRONG-LOCATOR']['affected_evidence_ids'])
        self.assertEqual([['LOC-ONE']],[b['affected_item_ids'] for b in assessment['blockers']])
        self.assertEqual(before,original)

    def test_benchmark_access_scope_does_not_override_locator_support(self):
        data=two_locators()
        data[0]['uncertainties']=[uncertainty(affected=['SUBJ-ONE','PATH-ONE'])]
        data[0]['uncertainty_gate_scopes']=[scope('benchmark_access',['SUBJ-ONE','PATH-ONE'])]
        gates,assessment=outcomes(data)
        self.assertEqual(['LOC-ONE','LOC-TWO'],gates['GATE-WRONG-LOCATOR']['affected_evidence_ids'])
        self.assertEqual('sufficient',assessment['status'])

    def test_explicit_path_wide_support_uncertainty_blocks_each_destination(self):
        data=two_locators()
        data[0]['uncertainties']=[uncertainty(affected=['PATH-ONE'])]
        data[0]['uncertainty_gate_scopes']=[scope('path_locator_support',['PATH-ONE'])]
        gates,assessment=outcomes(data)
        self.assertFalse(gates['GATE-WRONG-LOCATOR']['triggered'])
        self.assertEqual({'LOC-ONE','LOC-TWO'},{x for b in assessment['blockers'] for x in b['affected_item_ids']})

    def test_mixed_scopes_on_one_context_path_remain_separate(self):
        data=two_locators()
        data[0]['uncertainties']=[uncertainty(),uncertainty('UNC-ACCESS',['SUBJ-ONE','PATH-ONE'])]
        data[0]['uncertainty_gate_scopes']=[scope('locator_support',['LOC-ONE']),scope('benchmark_access',['SUBJ-ONE'],'UNC-ACCESS')]
        gates,assessment=outcomes(data)
        self.assertEqual(['LOC-TWO'],gates['GATE-WRONG-LOCATOR']['affected_evidence_ids'])
        self.assertEqual(1,len(assessment['blockers']))

    def test_unknown_or_missing_scope_is_an_explicit_gap_not_a_kind_guess(self):
        for supplement in ([],[scope('unknown',['LOC-ONE','PATH-ONE'])]):
            data=two_locators();data[0]['uncertainties']=[uncertainty()]
            data[0]['uncertainties'][0]['kind']='benchmark_access_boundary'
            data[0]['uncertainty_gate_scopes']=supplement
            gates,assessment=outcomes(data)
            self.assertFalse(gates['GATE-WRONG-LOCATOR']['triggered'])
            self.assertEqual('indeterminate',assessment['status'])
            self.assertEqual(['GATE-ASSESSMENT-UNCERTAINTY-SCOPE'],[b['blocker_id'] for b in assessment['blockers']])
            self.assertIn('UNC-ONE',assessment['blockers'][0]['reason'])

    def test_destination_scope_also_blocks_uncertain_supported_reference_attestation(self):
        for has_exception in (True,False):
            data=evidence(fit='exact_fit',judgment='supported',treatment='substantive')
            data[0]['uncertainties']=[uncertainty(affected=['XREF-ONE'])]
            data[0]['uncertainty_gate_scopes']=[scope('cross_reference_destination',['XREF-ONE'])]
            if not has_exception:data[0]['cross_reference_judgments']=[]
            gates,assessment=outcomes(data)
            self.assertFalse(gates['GATE-BROKEN-REFERENCE']['triggered'])
            self.assertEqual('GATE-ASSESSMENT-REFERENCE-UNCERTAIN',assessment['blockers'][0]['blocker_id'])

    def test_known_measurement_provenance_limitations_preserve_independent_gate_checks(self):
        for targets in (['GLOBAL-STRUCTURE'], ['CHUNK-001','CHUNK-017']):
            data=evidence()
            original=uncertainty(affected=targets);original.pop('evidence_ids')
            data[0]['uncertainties']=[original]
            mapped=scope('measurement_provenance',targets);mapped['evidence_ids']=[]
            mapped['rationale']='The preserved limitation concerns the density estimate, not inspected destination support.'
            data[0]['uncertainty_gate_scopes']=[mapped]
            gates,assessment=outcomes(data)
            self.assertEqual('sufficient',assessment['status'])
            self.assertTrue(gates['GATE-WRONG-LOCATOR']['triggered'])
            self.assertTrue(gates['GATE-BROKEN-REFERENCE']['triggered'])
            data[2][0]['judgments'][0]['confidence']='low'
            _,assessment=outcomes(data)
            self.assertEqual('GATE-ASSESSMENT-LOCATOR-UNCERTAIN',assessment['blockers'][0]['blocker_id'])
            data[0]['defects']=[{'defect_kind':'scope_failure'}]
            locators,references,assessment=cli._destination_gate_evidence(*data)
            self.assertEqual(([],[]),(locators,references))
            self.assertIn('GATE-ASSESSMENT-SOURCE',[b['blocker_id'] for b in assessment['blockers']])
            data[0].pop('uncertainty_gate_scopes')
            _,_,assessment=cli._destination_gate_evidence(*data)
            self.assertIn('GATE-ASSESSMENT-UNCERTAINTY-SCOPE',[b['blocker_id'] for b in assessment['blockers']])

    def test_scope_binding_rejects_unknown_duplicate_unbound_and_unproved_mappings(self):
        for bad in ('identity','duplicate','target','evidence','omitted_evidence','unknown_narrowing'):
            structure={'uncertainties':[uncertainty()], 'uncertainty_gate_scopes':[scope('locator_support',['LOC-ONE'])]}
            row=structure['uncertainty_gate_scopes'][0]
            if bad=='identity':row['uncertainty_id']='UNC-MISSING'
            if bad=='duplicate':structure['uncertainty_gate_scopes'].append(deepcopy(row))
            if bad=='target':row['target_ids']=['LOC-MISSING']
            if bad=='evidence':row['evidence_ids']=['EVID-INVENTED']
            if bad=='omitted_evidence':row['evidence_ids']=[]
            if bad=='unknown_narrowing':row['scope']='unknown'
            with self.subTest(bad=bad),self.assertRaises(StructureAuditError):validate_uncertainty_gate_scopes(structure)

    def test_bound_but_missing_candidate_target_remains_a_gap(self):
        data=evidence(resolution='valid_destination')
        data[0]['uncertainties']=[uncertainty(affected=['LOC-MISSING'])]
        data[0]['uncertainty_gate_scopes']=[scope('locator_support',['LOC-MISSING'])]
        _,assessment=outcomes(data)
        self.assertEqual('GATE-ASSESSMENT-UNCERTAINTY-TARGET',assessment['blockers'][0]['blocker_id'])

    def test_typed_scope_schema_and_all_calculation_outputs_are_invariant(self):
        fixture=completion.CurrentV8CompletionTests();fixture.setUp()
        try:
            registered=fixture.run_cli('register-structure','--state',str(fixture.state_path),'--input',str(fixture.structure_path))
            self.assertEqual(0,registered.returncode,registered.stdout)
            state=json.loads(fixture.state_path.read_text())
            loaded,*_=cli._calculation_loaded_from_state(state,fixture.state_path,fixture.root/'input.json')
            loaded['structure']['uncertainties']=[uncertainty(affected=['LOC-001','PATH-001'])]
            before=cli.calculate_loaded(loaded)
            preserved=deepcopy(loaded['structure']['uncertainties'])
            loaded['structure']['uncertainty_gate_scopes']=[scope('locator_support',['LOC-001'])]
            self.assertEqual([],schema_errors(loaded['structure'],'structure-audit-v6.schema.json'))
            self.assertEqual(before,cli.calculate_loaded(loaded))
            self.assertEqual(preserved,loaded['structure']['uncertainties'])
            record=next(r for r in state['artifacts'] if r['stage']=='structure_audit')
            path=fixture.root/record['path']
            native=json.loads(path.read_text())
            native['uncertainties']=preserved
            native['uncertainty_gate_scopes']=deepcopy(loaded['structure']['uncertainty_gate_scopes'])
            fixture.write(record['path'],native)
            record['sha256']=completion.file_hash(path)
            record['artifact_id']=completion.state_cli.artifact_id(record['path'],record['sha256'])
            fixture.state_path.write_text(json.dumps(state))
            for command in ('score','build-report'):
                result=fixture.run_cli(command,'--state',str(fixture.state_path))
                self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            state=json.loads(fixture.state_path.read_text())
            projection_record=next(r for r in state['artifacts'] if r.get('schema_version')=='ohfr-v8-canonical-web-projection-v1')
            projection=json.loads((fixture.root/projection_record['path']).read_text())
            readiness=projection['score_views']['views'][0]['readiness']
            self.assertEqual('indeterminate',readiness['status'])
            self.assertEqual([['LOC-001']],[b['affected_item_ids'] for b in readiness['assessment_blockers']])
            loaded['structure']['uncertainty_gate_scopes'][0]['target_ids']=['PATH-001']
            self.assertTrue(schema_errors(loaded['structure'],'structure-audit-v6.schema.json'))
            for targets in (['GLOBAL-STRUCTURE'],['CHUNK-001','CHUNK-017']):
                row=uncertainty(affected=targets);row.pop('evidence_ids')
                loaded['structure']['uncertainties']=[row]
                supplement=scope('measurement_provenance',targets);supplement['evidence_ids']=[]
                loaded['structure']['uncertainty_gate_scopes']=[supplement]
                self.assertEqual([],schema_errors(loaded['structure'],'structure-audit-v6.schema.json'))
                validate_uncertainty_gate_scopes(loaded['structure'])
            loaded['structure']['uncertainty_gate_scopes'][0]['target_ids']=['LOC-001']
            self.assertTrue(schema_errors(loaded['structure'],'structure-audit-v6.schema.json'))
        finally:fixture.tearDown()
