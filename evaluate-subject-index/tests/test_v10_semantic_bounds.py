"""Neutral semantic bounds preserve known facts, thresholds and physical counts."""
from copy import deepcopy
from decimal import Decimal
from itertools import product
import unittest
from unittest.mock import patch
from test_v10_semantic_utility import semantic
from test_v8_sensitivity_adversarial import reliability_ledgers,state,defect
from v10_semantic import resolved_possibilities
import runtime_profile
import dimension_score_v8_cli as scoring
import scoring_core as core


class SemanticBoundsTests(unittest.TestCase):
    def test_known_diagnostic_axes_and_zero_assessable_keep(self):
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            result=scoring.calculate_reliability(reliability_ledgers([semantic('mixed',None)]),'full')
        p=result['reliability_provenance']
        self.assertEqual(('0.7',1,'0.7'),(p['treatment_score_numerator'],p['treatment_score_denominator'],p['mean_treatment_score']))
        self.assertIsNone(p['mean_fit_score']);self.assertIsNone(p['keep_precision'])
        self.assertEqual({'lower':'0','central':None,'upper':'1'},p['keep_precision_uncertainty'])
        self.assertIsNone(result['dimension_percentage'])
        d=result['denominators']['components'][0]
        self.assertEqual((1,0,1,0,0),(d['original'],d['measured'],d['semantic_unresolved'],d['uninspectable'],d['not_measured']))
        self.assertFalse(d['small_denominator_exception'])

    def test_physical_exception_does_not_include_semantic(self):
        known=state('supported','substantive',locator_id='LOC-KNOWN')
        physical=state('uninspectable','unavailable',scope='unavailable',locator_id='LOC-PHYSICAL')
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            old=scoring.calculate_reliability(reliability_ledgers([known,physical]),'full')
            mixed=scoring.calculate_reliability(reliability_ledgers([known,physical,semantic()]),'full')
        self.assertTrue(old['denominators']['components'][0]['small_denominator_exception'])
        d=mixed['denominators']['components'][0]
        self.assertFalse(d['small_denominator_exception']);self.assertEqual(1,d['uninspectable']);self.assertEqual(1,d['semantic_unresolved'])
        self.assertEqual(1,mixed['reliability_provenance']['uninspectable_locator_count'])

    def test_known_nonkeep_fit_uncertainty_has_exact_existing_cap_envelope(self):
        unknown=semantic('mixed',None,'unsupported');unknown.update(error_codes=['LOC_POS'],severity='major')
        known=[state('unsupported','mixed',codes=['LOC_POS'],severity='major',fit='no_fit',locator_id=f'LOC-BAD-{i}') for i in range(2)]
        known += [state('supported','substantive',locator_id=f'LOC-GOOD-{i}') for i in range(20)]
        ledgers=reliability_ledgers(known+[unknown],defects=[defect('LOC_POS','generic','major',locator_id=unknown['locator_id'])])
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            result=scoring.calculate_reliability(ledgers,'full')
            outcomes=[]
            for world in resolved_possibilities(unknown):
                case=deepcopy(ledgers);case['locators'][-1]={**world,'_source_unit_id':'CHUNK-001'}
                resolved=scoring.calculate_reliability(case,'full')
                outcomes.append(Decimal(resolved['post_cap_percentage']))
        self.assertEqual(min(outcomes),Decimal(result['missing_data_bounds']['lower']['post_cap_percentage']))
        self.assertEqual(max(outcomes),Decimal(result['missing_data_bounds']['upper']['post_cap_percentage']))
        self.assertEqual('0',result['reliability_provenance']['locator_utility_assignments'][-1]['rating_credit'])

    def test_unknown_fit_does_not_invent_pattern_when_known_errors_exclude_it(self):
        rows=[semantic('mixed',None) for _ in range(3)]
        for i,row in enumerate(rows):row['locator_id']=f'LOC-UNKNOWN-{i}'
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            result=scoring.calculate_reliability(reliability_ledgers(rows),'full')
        for side in ('lower','upper'):
            pattern=next(r for r in result['missing_data_bounds'][side]['cap_evaluations'] if r['cap_id']=='reliability.distributed_unsupported_pattern')
            self.assertFalse(pattern['triggered']);self.assertEqual(0,pattern['observed']['unsupported_count'])

if __name__=='__main__':unittest.main()
