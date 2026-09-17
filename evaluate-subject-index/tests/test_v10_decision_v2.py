"""Calibration probes for the V10 decision-v2 score backstop."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from v10_overall_caps import evaluate
from v10_access import reconciliation
from v10_defect_reconciliation import material_ids
import scoring_core as core


def defect(identity, ids, denominator, *, owner='page_reference_reliability', kind='generic',
           code='LOC_POS', severity='minor', consequence='slows', root='ROOT-A'):
    return {'defect_id':identity,'code':code,'dimension_owner':owner,'severity':severity,
            'severity_basis':'localized_repairable_friction' if severity=='minor' else 'materially_misleading',
            'retrieval_consequence':consequence,'defect_kind':kind,'affected_item_ids':ids,
            'affected_source_sections':['CHUNK-1','CHUNK-2'],'affected_structural_sections':[],
            'root_cause_family':root,'affected_count':len(ids),'applicable_count':denominator,
            'affected_rate':str(Decimal(len(ids))/Decimal(denominator)),'source_section_denominator':8,
            'source_section_rate':'0.25','structural_section_denominator':1,'structural_section_rate':'0',
            'high_priority_access_destroyed':kind=='central_omission'}


def locator(i,path='PATH-OTHER',unsupported=True,page=None):
    return {'locator_id':f'LOC-{i:04d}','path_id':path,'complete_heading_path':['National'] if path=='PATH-EAC65BF97664' else ['Other'],
            'document_page':i+1 if page is None else page,'judgment':'unsupported' if unsupported else 'supported',
            'complete_path_fit':'no_fit' if unsupported else 'exact_fit'}


def score(locators, defects, pre='95', locator_documents=()):
    return evaluate({'source_scope':{'document_page_span':[1,400]}},{'locators':locators},
                    {'defects':defects,'scoring_context':{'candidate_attempt':{'status':'meaningful_attempt','evidence_ids':[]}}},Decimal(pre),locator_documents)


class V10DecisionV2Tests(unittest.TestCase):
    def test_isolated_wrong_locator_has_no_overall_cap(self):
        result=score([locator(0)],[])
        self.assertIsNone(result['applied_cap']);self.assertEqual('95',result['post_cap_overall_percentage'])

    def test_systemic_five_fifteen_and_thirty_percent(self):
        for count,denominator,maximum in ((10,200,'75'),(30,200,'60'),(60,200,'40')):
            ids=[f'LOC-{i:04d}' for i in range(count)]
            result=score([locator(i) for i in range(count)],[defect('DEFECT-SYSTEMIC',ids,denominator)])
            self.assertEqual(maximum,result['applied_cap']['maximum_percentage'])
            self.assertLessEqual(Decimal(result['post_cap_overall_percentage']),Decimal(maximum))

    def test_distinct_harms_survive_atomic_ownership_and_dominant_route(self):
        path='PATH-EAC65BF97664';locators=[locator(i,path,page=1+i*2) for i in range(175)]
        defects=[defect('DEFECT-CONCEPT',[path],2543,owner='conceptual_stance_fidelity',kind='misleading_relationship',code='CON',severity='major',consequence='misleads'),
                 defect('DEFECT-NAV',[path],2543,owner='findability_navigation',kind='misleading_access_route',code='HED',severity='major',consequence='misleads')]
        result=score(locators,defects,'88.52')
        self.assertEqual('40',result['applied_cap']['maximum_percentage'])
        dominant=next(row for row in result['cap_evaluations'] if row['cap_id']=='overall.dominant_malformed_route')
        self.assertTrue(dominant['triggered']);self.assertIn('DEFECT-CONCEPT',dominant['evidence_ids']);self.assertIn('DEFECT-NAV',dominant['evidence_ids'])

    def test_observed_indexia_and_indexerlabs_inputs_cannot_keep_high_scores(self):
        national=[locator(i,'PATH-EAC65BF97664',page=1+(i*399//174)) for i in range(175)]
        other=[locator(175+i) for i in range(526)]
        ids=[row['locator_id'] for row in national+other]
        indexia_defects=[defect('DEFECT-701',ids,13143),
                         defect('DEFECT-NATIONAL-CON',['PATH-EAC65BF97664'],2543,owner='conceptual_stance_fidelity',kind='misleading_relationship',code='CON',severity='major',consequence='misleads'),
                         defect('DEFECT-NATIONAL-NAV',['PATH-EAC65BF97664'],2543,owner='findability_navigation',kind='misleading_access_route',code='HED',severity='major',consequence='misleads')]
        self.assertLess(Decimal(score(national+other,indexia_defects,'88.52')['post_cap_overall_percentage']),Decimal('88.52'))
        zero_ids=[f'LOC-{i:04d}' for i in range(410)]
        labs=[]
        labs += [defect(f'DEFECT-OMIT-{i}',[f'SUBJ-{i}'],617,owner='meaningful_coverage',kind='central_omission',code='COV',severity='critical',consequence='blocks',root=f'OMIT-{i}') for i in range(7)]
        rows=[locator(i) for i in range(6222)];documents=[]
        for section in range(17):
            chunk=rows[section::17]
            for row in chunk:row['judgment']='supported';row['complete_path_fit']='exact_fit'
            documents.append({'chunk_id':f'CHUNK-{section+1:03d}','judgments':chunk})
        for row in rows[:410]:row['judgment']='unsupported';row['complete_path_fit']='no_fit' if int(row['locator_id'].split('-')[1])<151 else 'material_mismatch'
        result=score(rows,labs,'89.15',documents)
        self.assertEqual('75',result['applied_cap']['maximum_percentage'])
        self.assertLess(Decimal(result['post_cap_overall_percentage']),Decimal('89.15'))

    def test_denominator_and_prior_defect_conservation_helpers(self):
        before={name:[{'id':f'{name}-1','weight':1},{'id':f'{name}-2','weight':1}] for name in ('subjects','reader_tasks','treatments','weighted_access_obligations')}
        after=deepcopy(before);after['subjects'].pop()
        row=next(item for item in reconciliation(before,after) if item['family']=='subjects')
        self.assertEqual(-1,row['delta']);self.assertEqual(['subjects-2'],row['retired_ids'])
        structure={'defects':[defect('DEFECT-MAJOR',['PATH-1'],10,severity='major'),defect('DEFECT-MINOR',['LOC-1'],10)]}
        self.assertEqual(['DEFECT-MAJOR'],material_ids(structure))

    def test_critical_optional_missing_route_remains_scored(self):
        ledgers={'optional_map':{'SUBJ-MAP':False},'subjects':[{'subject_id':'SUBJ-MAP','priority':'optional',
                 'coverage':'missing','stance_preserved':'no','realistic_first_lookup_success':'no','severity':'critical'}],
                 'subject_original':1,'subject_not_measured':[],'defects':[],
                 'context':{'candidate_attempt':{'status':'meaningful_attempt'}}}
        result=core.calculate_coverage(ledgers,'full')
        denominator=result['denominators']['components'][0]
        self.assertEqual(1,denominator['applicable']);self.assertEqual('0',result['dimension_percentage'])


if __name__=='__main__':unittest.main()
