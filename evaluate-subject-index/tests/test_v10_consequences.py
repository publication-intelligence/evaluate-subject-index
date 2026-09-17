"""Boundary evidence for the approved V10 core gate register and ownership."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from test_wrong_destination_gates import evidence
from test_critical_gates import defect as minimal_defect
import scoring_core as core
import dimension_score_v8_cli as scoring
from policy_cli import CRITICAL_GATES
from v10_consequences import gate_outcomes


def defect(defect_id, kind, affected_item_id, *, code='XRF'):
    row=minimal_defect(defect_id,kind,affected_item_id,code=code)
    row['dimension_owner']={'COV':'meaningful_coverage','SEL':'editorial_selectivity','STA':'conceptual_stance_fidelity','CMP':'conceptual_stance_fidelity','LOC_POS':'page_reference_reliability','XRF':'findability_navigation','MEC':'mechanics_consistency'}[code]
    row.update(affected_source_sections=['CHUNK-001'],affected_structural_sections=[],root_cause_family='ROOT-'+defect_id,applicable_count=1,source_section_denominator=1,structural_section_denominator=1,high_priority_access_destroyed=False)
    return row


def outcomes(data):
    structure, calculation, documents, inventory=data
    for row in structure['defects']:
        row['affected_count']=len(row['affected_item_ids'])
        row['affected_rate']=core.rounded_rate(row['affected_count'],row['applicable_count'])
        row['source_section_rate']=core.rounded_rate(len(row['affected_source_sections']),row['source_section_denominator'])
        row['structural_section_rate']=core.rounded_rate(len(row['affected_structural_sections']),row['structural_section_denominator'])
        core.validate_defect(row,0)
    proof=scoring._destination_gate_evidence(structure,calculation,documents,inventory)
    policy={'critical_gates':[{'gate_id':key,'description':value} for key,value in CRITICAL_GATES]}
    return {row['gate_id']:row for row in gate_outcomes(policy,structure,calculation,proof,scoring._legacy_critical_gate_outcomes)},proof[2]


def pattern(data, count=10, denominator=200, sections=2, section_population=8):
    structure, calculation, documents, inventory=data
    provenance=calculation['dimensions'][0]['reliability_provenance']
    template=deepcopy(documents[0]['judgments'][0])
    documents[0]['judgments']=[];provenance['locator_utility_assignments']=[];provenance['locator_path_bindings']={}
    for i in range(count):
        row=deepcopy(template);row.update(locator_id=f'LOC-{i}',path_id=f'PATH-{i}',complete_path_fit='severe_mismatch',judgment='unsupported',severity='minor')
        documents[0]['judgments'].append(row)
        provenance['locator_utility_assignments'].append({'locator_id':row['locator_id'],'fit_category':'severe_mismatch','locator_severity':'minor'})
        provenance['locator_path_bindings'][row['locator_id']]=row['path_id']
        inventory['paths'].append({'path_id':row['path_id']})
    provenance['original_locator_denominator']=count
    row=defect('DEFECT-PATTERN','generic','LOC-0',code='LOC_POS')
    row.update(severity='minor',severity_basis='localized_repairable_friction',retrieval_consequence='slows',dimension_owner='page_reference_reliability',affected_item_ids=[f'LOC-{i}' for i in range(count)],root_cause_family='ROOT-A',applicable_count=denominator,affected_source_sections=[f'CHUNK-{i}' for i in range(sections)],source_section_denominator=section_population,affected_structural_sections=[],structural_section_denominator=1)
    structure['defects']=[row]
    return data


class V10ConsequenceTests(unittest.TestCase):
    def test_atomic_destination_predicates_and_uncertainty(self):
        for fit,judgment,treatment,expected in [('no_fit','unsupported','absent',True),('material_partial_fit','partially_supported','mixed',False),('material_mismatch','unsupported','substantive',False),('severe_mismatch','unsupported','substantive',False)]:
            with self.subTest(fit=fit):
                gates,_=outcomes(evidence(fit=fit,judgment=judgment,treatment=treatment,resolution='valid_destination'))
                self.assertEqual(expected,gates['GATE-WRONG-LOCATOR']['triggered'])
        for change in ('confidence','scope','rationale','uninspectable'):
            data=evidence(resolution='valid_destination');row=data[2][0]['judgments'][0]
            if change=='confidence':row['confidence']='low'
            elif change=='scope':row['source_scope_status']='unavailable'
            elif change=='rationale':row['fit_rationale']=' '
            else:row['judgment']='uninspectable'
            gates,assessment=outcomes(data);self.assertFalse(gates['GATE-WRONG-LOCATOR']['triggered']);self.assertEqual('indeterminate',assessment['status'])

    def test_reference_must_be_exact_confirmed_delivered_destination(self):
        for resolution,trigger in [('no_valid_destination',True),('valid_destination',False),('defective_but_identifiable_destination',False),(None,False)]:
            data=evidence(resolution=resolution);gates,_=outcomes(data)
            self.assertEqual(trigger,gates['GATE-BROKEN-REFERENCE']['triggered'])
        data=evidence();data[0]['cross_reference_judgments'][0]['target_resolution']['target_display']='Different'
        gates,assessment=outcomes(data);self.assertFalse(gates['GATE-BROKEN-REFERENCE']['triggered']);self.assertEqual('indeterminate',assessment['status'])

    def test_systemic_thresholds_and_no_residual_spread_inference(self):
        for count,denominator,sections,population,expected in [(9,180,2,8,False),(10,201,2,8,False),(10,200,1,4,False),(10,200,2,9,False),(10,200,2,8,True)]:
            data=pattern(evidence(resolution='valid_destination'),count,denominator,sections,population)
            gates,_=outcomes(data);self.assertEqual(expected,gates['GATE-SYSTEMIC-UNSUPPORTED']['triggered'])
        data=pattern(evidence(resolution='valid_destination'),11)
        data[2][0]['judgments'][0]['complete_path_fit']='no_fit'
        data[1]['dimensions'][0]['reliability_provenance']['locator_utility_assignments'][0]['fit_category']='no_fit'
        gates,_=outcomes(data)
        self.assertTrue(gates['GATE-WRONG-LOCATOR']['triggered'])
        self.assertFalse(gates['GATE-SYSTEMIC-UNSUPPORTED']['triggered'])
        self.assertEqual([],gates['GATE-SYSTEMIC-UNSUPPORTED']['systemic_groups'])
        data=pattern(evidence(resolution='valid_destination'))
        data[1]['dimensions'][0]['reliability_provenance']['locator_utility_assignments'][0]['fit_category']='material_partial_fit'
        gates,_=outcomes(data);self.assertFalse(gates['GATE-SYSTEMIC-UNSUPPORTED']['triggered'])

    def test_specific_semantics_own_scope_and_grounding_atomic_evidence(self):
        data=evidence(fit='severe_mismatch',resolution='valid_destination')
        data[1]['dimensions'][0]['reliability_provenance']['locator_utility_assignments'][0]['locator_severity']='major'
        stance=defect('DEFECT-STANCE','stance_reversal','LOC-ONE',code='STA');stance.update(retrieval_consequence='misleads',severity_basis='materially_misleading')
        scope=defect('DEFECT-SCOPE','out_of_scope_locator','LOC-ONE',code='LOC_POS')
        grounding=defect('DEFECT-GROUND','generic','LOC-ONE',code='LOC_POS')
        data[0]['defects']=[scope,grounding,stance]
        gates,_=outcomes(data)
        self.assertTrue(gates['GATE-STANCE']['triggered'])
        self.assertFalse(gates['GATE-SCOPE-LOCATOR']['triggered']);self.assertFalse(gates['GATE-GROUNDING']['triggered'])

    def test_candidate_scope_defect_is_not_source_binding_invalidity(self):
        data=evidence(resolution='valid_destination')
        data[0]['defects']=[defect('DEFECT-SCOPE','out_of_scope_locator','LOC-ONE')]
        with patch.object(scoring,'is_v10',return_value=True):
            validity=scoring._evaluation_validity({'audit_design':{'uninspectable_locator_rate_tolerance':.01}},data[0],data[1])
            self.assertEqual('valid',validity['status'])
            gates,assessment=outcomes(data)
        self.assertTrue(gates['GATE-WRONG-LOCATOR']['triggered'])
        self.assertEqual('sufficient',assessment['status'])

    def test_invalid_source_blocks_dependent_but_not_inventory_destination_proof(self):
        data=evidence()
        with patch.object(scoring,'is_v10',return_value=True):
            proof=scoring._destination_gate_evidence(*data, source_binding_valid=False)
        policy={'critical_gates':[{'gate_id':k,'description':v} for k,v in CRITICAL_GATES]}
        gates={row['gate_id']:row for row in gate_outcomes(policy,data[0],data[1],proof,scoring._legacy_critical_gate_outcomes)}
        self.assertFalse(gates['GATE-WRONG-LOCATOR']['triggered'])
        self.assertTrue(gates['GATE-BROKEN-REFERENCE']['triggered'])
        self.assertEqual('indeterminate',proof[2]['status'])

    def test_source_failure_cannot_enter_candidate_quality_channel(self):
        data=evidence();data[0]['defects']=[defect('DEFECT-SOURCE','scope_failure','LOC-ONE')]
        from scoring_core import CalculationError
        with self.assertRaises(CalculationError):outcomes(data)
        from v10_contract import candidate_defect_errors
        self.assertTrue(candidate_defect_errors(data[0]))

    def test_remaining_individual_core_gate_predicates(self):
        cases=[('GATE-SCOPE-LOCATOR','out_of_scope_locator','LOC_POS','LOC-ONE'),
               ('GATE-CENTRAL-OMISSION','central_omission','COV','SUBJ-ONE'),
               ('GATE-COMPOUND','generic','CMP','LOC-ONE'),
               ('GATE-SEE-SUBSTITUTION','substitutive_see','XRF','XREF-ONE'),
               ('GATE-CROSS-REFERENCE','circular_or_chained_reference','XRF','XREF-ONE'),
               ('GATE-GROUNDING','generic','LOC_POS','LOC-ONE'),
               ('GATE-STRUCTURE','representation_corruption','MEC','NODE-ONE')]
        for gate,kind,code,item in cases:
            with self.subTest(gate=gate):
                data=evidence(fit='severe_mismatch',resolution='valid_destination')
                data[1]['dimensions'][0]['reliability_provenance']['locator_utility_assignments'][0]['locator_severity']='major'
                data[0]['cross_reference_judgments'][0]['target_resolution']['reference_type']='see';data[3]['cross_references'][0]['reference_type']='see'
                row=defect('DEFECT-ONE',kind,item,code=code)
                if gate=='GATE-CENTRAL-OMISSION':row['high_priority_access_destroyed']=True
                if gate=='GATE-STRUCTURE':row.update(severity='critical',severity_basis='systemic_nonuse',dimension_owner='mechanics_consistency',affected_item_ids=['NODE-ONE','NODE-TWO','NODE-THREE'],applicable_count=3)
                data[0]['defects']=[row]
                gates,_=outcomes(data);self.assertTrue(gates[gate]['triggered'])
                row.update(severity='minor',severity_basis='localized_repairable_friction',retrieval_consequence='slows')
                gates,_=outcomes(data);self.assertFalse(gates[gate]['triggered'])
        data=evidence(fit='material_partial_fit',judgment='partially_supported',treatment='mixed',resolution='valid_destination')
        data[0]['defects']=[defect('DEFECT-CMP','generic','LOC-ONE',code='CMP')]
        gates,_=outcomes(data);self.assertFalse(gates['GATE-COMPOUND']['triggered'])

    def test_unresolved_access_review_scopes_linked_structure_gate_evidence(self):
        data=evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='valid_destination')
        data[0]['candidate_denominator']['nodes']=[{'node_id':'NODE-001','heading_path':['A']}]
        row=defect('DEFECT-STANCE','stance_reversal','NODE-001',code='STA')
        row.update(severity_basis='materially_misleading',retrieval_consequence='misleads')
        data[0]['defects']=[row]
        before,_=outcomes(data);self.assertTrue(before['GATE-STANCE']['triggered'])
        proof=scoring._destination_gate_evidence(*data)
        proof[2]['status']='indeterminate';proof[2]['blockers'].append({'blocker_id':'GATE-ASSESSMENT-ACCESS-REVIEW','affected_item_ids':['SUBJ-ONE','PATH-ONE','NODE-001'],'reason':'Unresolved requirement linked to the structured finding.'})
        policy={'critical_gates':[{'gate_id':k,'description':v} for k,v in CRITICAL_GATES]}
        after={r['gate_id']:r for r in gate_outcomes(policy,data[0],data[1],proof,scoring._legacy_critical_gate_outcomes)}
        self.assertFalse(after['GATE-STANCE']['triggered'])

    def test_locator_severity_is_not_an_extra_individual_gate_threshold(self):
        cases=[('GATE-SCOPE-LOCATOR','out_of_scope_locator','LOC_POS'),('GATE-COMPOUND','generic','CMP'),('GATE-GROUNDING','generic','LOC_POS')]
        for gate,kind,code in cases:
            for fit,expected in [('severe_mismatch',True),('material_mismatch',False),('material_partial_fit',False)]:
                with self.subTest(gate=gate,fit=fit):
                    data=evidence(fit=fit,judgment='partially_supported' if fit=='material_partial_fit' else 'unsupported',treatment='mixed',resolution='valid_destination')
                    row=defect('DEFECT-MAJOR',kind,'LOC-ONE',code=code);data[0]['defects']=[row]
                    gates,_=outcomes(data);self.assertEqual(expected,gates[gate]['triggered'])
                    if expected:self.assertEqual('minor',gates[gate]['qualifying_locator_evidence'][0]['locator_severity'])
                    row.update(severity='minor',severity_basis='localized_repairable_friction',retrieval_consequence='slows')
                    gates,_=outcomes(data);self.assertFalse(gates[gate]['triggered'])

    def test_reference_and_clutter_systemic_thresholds(self):
        for gate,family,kind,code in [('GATE-CROSS-REFERENCE','XREF','unsupported_reference','XRF'),('GATE-CLUTTER','NODE','clutter_pattern','SEL')]:
            for count,denominator,sections,population,expected in [(9,180,2,8,False),(10,201,2,8,False),(10,200,1,4,False),(10,200,2,9,False),(10,200,2,8,True)]:
                with self.subTest(gate=gate,count=count,denominator=denominator,sections=sections,population=population):
                    data=evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='valid_destination')
                    ids=[f'{family}-{i}' for i in range(count)]
                    if family=='XREF':data[0]['candidate_denominator']['cross_reference_ids']+=ids
                    row=defect('DEFECT-PATTERN',kind,ids[0],code=code)
                    row.update(severity='minor',severity_basis='localized_repairable_friction',retrieval_consequence='slows',affected_item_ids=ids,root_cause_family='ROOT-PATTERN',applicable_count=denominator,affected_source_sections=[f'CHUNK-{i}' for i in range(sections)],source_section_denominator=population,affected_structural_sections=[],structural_section_denominator=1)
                    data[0]['defects']=[row];gates,_=outcomes(data);self.assertEqual(expected,gates[gate]['triggered'])

    def test_tool_or_format_uninspectability_does_not_establish_structure_failure(self):
        data=evidence(fit='uninspectable',judgment='uninspectable',treatment='unavailable',resolution=None)
        data[0]['full_scope_attestation']['complete']=False
        data[1]['dimensions'][0]['reliability_provenance']['uninspectable_locator_count']=1
        gates,assessment=outcomes(data)
        self.assertFalse(gates['GATE-STRUCTURE']['triggered'])
        self.assertFalse(any(row['triggered'] for row in gates.values()))
        self.assertEqual('indeterminate',assessment['status'])
        validity=scoring._evaluation_validity({'audit_design':{'uninspectable_locator_rate_tolerance':.01}},data[0],data[1])
        self.assertIn('VALIDITY-UNINSPECTABLE',[row['blocker_id'] for row in validity['blockers']])

    def test_true_candidate_output_failure_is_separate_from_attestation(self):
        data=evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='valid_destination')
        data[0]['full_scope_attestation']['complete']=False
        gates,_=outcomes(data);self.assertFalse(gates['GATE-STRUCTURE']['triggered'])
        for status in ('empty','structurally_incomplete','unparseable'):
            data[0]['scoring_context']={'candidate_attempt':{'status':status,'evidence_ids':['EVID-ATTEMPT']}}
            gates,_=outcomes(data);self.assertTrue(gates['GATE-STRUCTURE']['triggered'])

    def test_missing_reference_and_deep_heading_are_not_quality_gates(self):
        data=evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='valid_destination')
        data[0]['defects']=[defect('DEFECT-MISSING','substitutive_see','TASK-001')]
        data[0]['candidate_denominator']['nodes']=[{'node_id':'NODE-ONE','heading_path':['A','B','C']}]
        gates,_=outcomes(data);self.assertFalse(any(row['triggered'] for row in gates.values()))
        self.assertNotIn('GATE-DEPTH',gates)

if __name__=='__main__':unittest.main()
