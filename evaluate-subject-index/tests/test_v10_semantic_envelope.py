"""Synthetic exact-envelope checks against the unchanged resolved calculator."""
from copy import deepcopy
from decimal import Decimal
from itertools import product
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import scoring_core as core
from v10_semantic_envelope import selectivity_envelope


def row(i,treatment,fit='exact_fit',unit=0):
    return {'locator_id':f'LOC-SYNTH-{i}','source_scope_status':'indexable','treatment_class':treatment,
            'complete_path_fit':fit,'judgment':'semantic_unresolved' if treatment is None or fit is None else 'partially_supported' if fit=='material_partial_fit' else 'supported' if treatment in {'substantive','mixed'} else 'unsupported',
            'error_codes':[],'severity':'none',
            '_source_unit_id':f'CHUNK-{unit}'}


def oracle(rows,units):
    ledgers={'locators':rows,'locator_original':len(rows),'locator_not_measured':[],
             'locator_not_measured_units':[],'source_units':units,'context':{'candidate_attempt':{'status':'meaningful_attempt'}}}
    with patch.object(core,'calculate_density',return_value=(Decimal(80),{})),patch.object(core,'percentage_native',return_value=True):
        result=core.calculate_selectivity(ledgers,'full')
    cap=result['cap_evaluations'][0]
    return (Decimal(result['substantive_selectivity_percentage']),
            (cap['cap_id'] if cap['triggered'] else None,Decimal(str(cap['maximum_percentage'])),result['denominators']['components'][0]['defined_zero_rule']))


def exhaustive(rows,units):
    choices=[]
    for r in rows:
        treatments=[r['treatment_class']] if r['treatment_class'] is not None else list(core.SELECTIVITY_CREDIT)+['absent']
        options=[]
        for treatment in treatments:
            fits=[r['complete_path_fit']] if r['complete_path_fit'] is not None else ['exact_fit','material_partial_fit','material_mismatch','severe_mismatch','no_fit']
            for fit in fits:
                if treatment=='absent' and fit!='no_fit':
                    if r['complete_path_fit'] is None:continue
                    # Fixed fit incompatible with absent cannot produce a truthful
                    # scenario; the envelope must honor this known fact.
                    continue
                keeps=[r['judgment']] if r['judgment']!='semantic_unresolved' else ['supported','partially_supported','unsupported']
                import locator_utility
                for keep in keeps:
                    value=deepcopy(r);value.update(treatment_class=treatment,complete_path_fit=fit,judgment=keep)
                    if not locator_utility.combined_state_errors(value):options.append(value)
        choices.append(options)
    results=[oracle(list(values),units) for values in product(*choices)]
    return min(x[0] for x in results),max(x[0] for x in results),len({x[1] for x in results})==1


class SemanticEnvelopeTests(unittest.TestCase):
    def test_small_exhaustive_scenarios(self):
        for seed in range(8):
            rng=random.Random(seed);known=[row(i,rng.choice(['substantive','mixed','passing_mention']),rng.choice(['exact_fit','material_partial_fit']),i%2) for i in range(3)]
            unknown=[row(i+3,None,None,i%2) for i in range(2)]
            rows=known+unknown;units=['CHUNK-0','CHUNK-1']
            with self.subTest(seed=seed):
                result=selectivity_envelope(rows,units);low,high,stable=exhaustive(rows,units)
                self.assertEqual((low,high,stable),(result['lower']['percentage'],result['upper']['percentage'],result['cap_invariant']))

    def test_cap_threshold_and_partial_fit_dilution(self):
        rows=[row(i,'passing_mention',unit=i%4) for i in range(10)]+[row(i+10,'substantive') for i in range(10)]
        # Null fit permits both absent and eligible-zero scenarios.
        rows += [row(21,None,None,4),row(22,None,None,5)]
        units=[f'CHUNK-{i}' for i in range(8)]
        result=selectivity_envelope(rows,units);low,high,stable=exhaustive(rows,units)
        self.assertEqual((low,high,stable),(result['lower']['percentage'],result['upper']['percentage'],result['cap_invariant']))
        self.assertIsNone(result['central_percentage'])

    def test_known_fit_excludes_absent_and_preserves_fixed_applicability(self):
        rows=[row(i,'passing_mention',unit=i%4) for i in range(10)]+[row(i+10,'substantive') for i in range(10)]
        rows += [row(21,None,'material_partial_fit'),row(22,None,'exact_fit')]
        units=[f'CHUNK-{i}' for i in range(8)]
        result=selectivity_envelope(rows,units);low,high,stable=exhaustive(rows,units)
        self.assertEqual((low,high,stable),(result['lower']['percentage'],result['upper']['percentage'],result['cap_invariant']))
        self.assertEqual({'lower':22,'upper':22},result['applicability_interval'])

    def test_resolved_cases_unchanged(self):
        for count in (0,1,9,10,20):
            rows=[row(i,'passing_mention',unit=i%4) for i in range(count)]+[row(100,'substantive')]
            result=selectivity_envelope(rows,['CHUNK-0','CHUNK-1','CHUNK-2','CHUNK-3'])
            expected,_=oracle(rows,['CHUNK-0','CHUNK-1','CHUNK-2','CHUNK-3'])
            self.assertEqual(expected,result['central_percentage'])

if __name__=='__main__':unittest.main()
