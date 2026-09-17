"""Truthful synthetic axis records and unchanged historical profile behavior."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import locator_utility as utility
import runtime_profile
from schema_validation import schema_errors


def semantic(treatment='substantive',fit=None,keep='semantic_unresolved'):
    return {'locator_id':'LOC-SYNTHETIC','path_id':'PATH-SYNTHETIC','document_page':1,'source_page_label':'1',
            'complete_heading_path':['Synthetic heading'],'source_scope_status':'indexable','treatment_class':treatment,
            'complete_path_fit':fit,'judgment':keep,'error_codes':[],'severity':'none','confidence':'low',
            'evidence_summary':'Synthetic physically inspected evidence.','fit_rationale':'A declared axis remains unresolved after inspection.',
            'evidence_ids':['EVID-SYNTHETIC'],
            'axis_resolution':{'treatment':'unresolved' if treatment is None else 'known','complete_path_fit':'unresolved' if fit is None else 'known',
                               'keep':'unresolved' if keep=='semantic_unresolved' else 'known','inspection_completed':True,
                               'reason_category':'unresolved_relationship','rationale':'Synthetic unresolved relationship; known facts preserved.'}}


def nonkeep():
    row=semantic('passing_mention',None,'not_kept_subtype_unresolved')
    row['keep_decision']='not_kept';row['axis_resolution']['judgment_subtype']='unresolved'
    return row


class SemanticUtilityTests(unittest.TestCase):
    def test_known_axes_and_keep_are_preserved(self):
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            for treatment,fit,keep in [('substantive',None,'semantic_unresolved'),(None,'exact_fit','semantic_unresolved'),(None,None,'semantic_unresolved'),('mixed',None,'unsupported')]:
                row=semantic(treatment,fit,keep)
                with self.subTest(treatment=treatment,fit=fit,keep=keep):
                    self.assertEqual([],utility.combined_state_errors(row));out=utility.assign_locator_utility(row).as_dict()
                    self.assertEqual('inspectable',out['inspectability_state'])
                    self.assertEqual(treatment,out['treatment_class'])
                    self.assertEqual(None if keep=='semantic_unresolved' else '0',out['rating_credit'])
                    self.assertEqual(None if treatment is None else '1' if treatment=='substantive' else '0.7',out['treatment_score'])
                    self.assertEqual(None if fit is None else '1',out['fit_score'])
                    self.assertEqual('Semantically unresolved after inspection',out['disposition_reason'])

    def test_old_profiles_reject_semantic_branch(self):
        for profile in ('v8','v9','v10'):
            with patch.object(runtime_profile,'ACTIVE',profile):
                self.assertIn('invalid:semantic_uncertainty_execution_profile_required',utility.combined_state_errors(semantic()))

    def test_native_schema_and_truthfulness_rejections(self):
        row=semantic();audit={'schema_version':'locator-audit-v3','evaluation_id':'EVAL-SYNTHETIC','candidate_sha256':'0'*64,'chunk_id':'CHUNK-001','expected_locator_ids':['LOC-SYNTHETIC'],'judgments':[row],'completion':{'expected':1,'judged':1,'unique':True,'complete':True}}
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            self.assertEqual([],schema_errors(audit,'locator-audit-v2.schema.json'))
            for field,value in [('source_scope_status','ambiguous'),('treatment_class','unavailable'),('judgment','uninspectable')]:
                bad=deepcopy(row);bad[field]=value
                self.assertTrue(utility.combined_state_errors(bad))
            bad=deepcopy(row);bad['axis_resolution']['complete_path_fit']='known';self.assertTrue(utility.combined_state_errors(bad))
            bad=deepcopy(row);bad['axis_resolution']['inspection_completed']=False;self.assertTrue(utility.combined_state_errors(bad))
        self.assertTrue(schema_errors(audit,'locator-audit-v2.schema.json',profile='v10'))

    def test_singleton_unknown_axes_are_rejected(self):
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            for row,axis in [(semantic('mixed','material_partial_fit'),'keep'),(semantic('mixed','no_fit'),'keep'),(semantic('mixed',None,'supported'),'complete_path_fit'),(semantic('absent',None,'unsupported'),'complete_path_fit')]:
                self.assertIn('inconsistent:unresolved_axis_is_logically_resolved_'+axis,utility.combined_state_errors(row))

    def test_known_nonkeep_plural_subtype_branch(self):
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            row=nonkeep();self.assertEqual([],utility.combined_state_errors(row))
            result=utility.assign_locator_utility(row).as_dict()
            self.assertEqual('0',result['rating_credit']);self.assertEqual({'lower':'0','upper':'0'},result['rating_credit_uncertainty_bounds'])
            self.assertEqual('not_kept',result['keep_decision'])
            for field,value in [('treatment_class','mixed'),('complete_path_fit','no_fit'),('complete_path_fit','material_partial_fit')]:
                bad=deepcopy(row);bad[field]=value
                if field=='complete_path_fit':bad['axis_resolution']['complete_path_fit']='known'
                self.assertTrue(utility.combined_state_errors(bad))
            self.assertTrue(utility.combined_state_errors(semantic('passing_mention',None)))
        for profile in ('v8','v9','v10'):
            with patch.object(runtime_profile,'ACTIVE',profile):self.assertTrue(utility.combined_state_errors(nonkeep()))

    def test_exact_packet_completion_counts_semantic_separately(self):
        import parallel_candidate_audit_cli as audits
        row=semantic();document={'schema_version':'locator-audit-v3','evaluation_id':'EVAL-SYNTHETIC','candidate_sha256':'0'*64,'chunk_id':'CHUNK-001','expected_locator_ids':[row['locator_id']],'judgments':[row],'completion':{'expected':1,'judged':1,'unique':True,'complete':True,'semantic_unresolved':1}}
        frozen={'state':{'evaluation_id':document['evaluation_id']},'candidate_sha256':document['candidate_sha256']}
        packet={'assignments':{row['locator_id']:{'path_id':row['path_id'],'heading_path':row['complete_heading_path'],'document_page':1,'source_page_label':'1'}},'paths':[row['path_id']]}
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            result=audits.validate_locator_audit(document,frozen,packet,'CHUNK-001')
            self.assertEqual(1,result['semantic_unresolved_locator_count'])
            self.assertEqual(0,result['judgment_counts']['uninspectable'])
            for mutation in ('missing','duplicate','foreign','count'):
                bad=deepcopy(document)
                if mutation=='missing':bad['judgments']=[]
                elif mutation=='duplicate':bad['judgments']*=2
                elif mutation=='foreign':bad['judgments'][0]['locator_id']='LOC-FOREIGN'
                else:bad['completion']['semantic_unresolved']=0
                with self.assertRaises(Exception):audits.validate_locator_audit(bad,frozen,packet,'CHUNK-001')

if __name__=='__main__':unittest.main()
