"""V8.1 false-positive and material-consequence regression matrix."""
from copy import deepcopy
from decimal import Decimal
import unittest
from test_critical_gates import defect, gate_outcomes
from test_v8_sensitivity_adversarial import reliability_ledgers, state
import dimension_score_v8_cli as cli
import scoring_core as core
import policy_cli


def finding(kind='generic', code='LOC_POS', severity='major', ids=None, owner='page_reference_reliability', **extra):
    ids = ids or ['LOC-TEST']
    return dict(defect('DEFECT-TEST', kind, ids[0], code=code), severity=severity,
                severity_basis='materially_misleading' if severity == 'major' else 'central_reversal' if severity == 'critical' else 'localized_repairable_friction',
                retrieval_consequence='misleads' if severity in {'major','critical'} else 'slows',
                dimension_owner=owner, affected_item_ids=ids, affected_count=len(ids), applicable_count=100,
                affected_rate=str(len(ids)/100), root_cause_family='same_cause',
                affected_source_sections=['CHUNK-1','CHUNK-2'], source_section_denominator=8,
                affected_structural_sections=[], structural_section_denominator=100,
                high_priority_access_destroyed=False) | extra


def outcomes(rows, locators=(), complete=True, uninspectable=0, attempt='meaningful_attempt'):
    policy = {'audit_design': {'uninspectable_locator_rate_tolerance': .01},
              'critical_gates': [{'gate_id': id, 'description': description} for id, description in policy_cli.CRITICAL_GATES]}
    structure = {'defects': rows, 'candidate_denominator': {'nodes': [], 'cross_reference_ids': ['XREF-1']},
                 'full_scope_attestation': {'complete': complete},
                 'scoring_context': {'candidate_attempt': {'status': attempt, 'evidence_ids': ['GLOBAL-STRUCTURE']}}}
    calc = {'dimensions': [{'dimension_id': 'page_reference_reliability', 'reliability_provenance': {
        'original_locator_denominator': 100, 'uninspectable_locator_count': uninspectable,
        'locator_utility_assignments': list(locators)}}]}
    return {row['gate_id']: row for row in cli._critical_gate_outcomes(policy, structure, calc)}, cli._evaluation_validity(policy, structure, calc)


class ConsequencePolicyTests(unittest.TestCase):
    def test_minor_relationship_reference_and_local_clutter_do_not_gate(self):
        rows = [finding(kind='misleading_relationship', code='CON', severity='minor'),
                finding(kind='unsupported_reference', code='XRF', severity='minor', ids=['XREF-1']),
                finding(kind='clutter_pattern', code='SEL', severity='minor')]
        gates, _ = outcomes(rows)
        self.assertFalse(any(row['triggered'] for row in gates.values()))

    def test_partial_locator_never_caps_or_gates_even_with_major_cmp_or_stance(self):
        for code, kind in [('CMP','generic'),('STA','stance_reversal'),('LOC_POS','generic')]:
            row = state('partially_supported','substantive',codes=[code],severity='major')
            d = finding(code=code,kind=kind)
            result = cli.calculate_reliability(reliability_ledgers([row], defects=[d]), "full")
            self.assertFalse(any(cap['triggered'] for cap in result['cap_evaluations']))
            self.assertEqual('70', str(result['reliability_provenance']['locator_utility_assignments'][0]['diagnostic_grade']))
            gates, _ = outcomes([d], [row])
            self.assertFalse(any(gate['triggered'] for gate in gates.values()))

    def test_delivered_no_fit_and_severe_cmp_have_explicit_caps_and_gates(self):
        for code, fit, gate in [('LOC_POS','no_fit','GATE-GROUNDING'),('CMP','severe_mismatch','GATE-COMPOUND')]:
            row = state('unsupported','absent' if fit == 'no_fit' else 'substantive',codes=[code],severity='major',fit=fit)
            d = finding(code=code)
            result = cli.calculate_reliability(reliability_ledgers([row], defects=[d]), "full")
            cap = next(c for c in result['cap_evaluations'] if c['cap_id']=='reliability.major_delivered_no_fit')
            self.assertTrue(cap['triggered'])
            gates, _ = outcomes([d], [row])
            self.assertTrue(gates[gate]['triggered'])
            for key in ('threshold','affected_evidence_ids','consequence_evidence','threshold_reason'):
                self.assertTrue(gates[gate][key])

    def test_expected_treatment_misses_only_reduce_recall(self):
        row = state('supported','substantive')
        result = cli.calculate_reliability(reliability_ledgers([row],[('missed','principal')]), 'full')
        self.assertFalse(any(cap['triggered'] for cap in result['cap_evaluations']))
        self.assertEqual('0', result['dimension_percentage'])

    def test_missing_routes_do_not_cap_but_delivered_destructive_routes_do(self):
        d = finding(kind='misleading_access_route',code='XRF',ids=['TASK-1'],owner='findability_navigation')
        ledgers = {'defects':[d], 'locators':[], 'references':[{'reference_id':'XREF-1','judgment':'unsupported'}], 'nodes':[]}
        self.assertEqual([], core.navigation_cap_defects(ledgers))
        d.update(defect_kind='unsupported_reference',affected_item_ids=['XREF-1'])
        self.assertEqual([d], core.navigation_cap_defects(ledgers))
        d.update(affected_item_ids=['SUBJ-1'],high_priority_access_destroyed=True)
        self.assertEqual([d], core.navigation_cap_defects(ledgers))

    def test_central_omission_requires_critical_or_destroyed_access(self):
        d = finding(kind='central_omission',code='COV',ids=['SUBJ-1'],owner='meaningful_coverage')
        gates, _ = outcomes([d]); self.assertFalse(gates['GATE-CENTRAL-OMISSION']['triggered'])
        d['high_priority_access_destroyed'] = True
        gates, _ = outcomes([d]); self.assertTrue(gates['GATE-CENTRAL-OMISSION']['triggered'])
        d.update(severity='critical',severity_basis='broken_scope',high_priority_access_destroyed=False)
        gates, _ = outcomes([d]); self.assertTrue(gates['GATE-CENTRAL-OMISSION']['triggered'])

    def test_stance_has_specific_gate_without_grounding_duplicate(self):
        row = state('unsupported','substantive',fit='severe_mismatch',codes=['STA'],severity='major')
        gates, _ = outcomes([finding(kind='stance_reversal',code='STA')],[row])
        self.assertTrue(gates['GATE-STANCE']['triggered'])
        self.assertFalse(gates['GATE-GROUNDING']['triggered'])

    def test_substitutive_see_blocks_access(self):
        d = finding(kind='substitutive_see',code='XRF',ids=['XREF-1'],owner='findability_navigation',retrieval_consequence='blocks',severity_basis='blocked_retrieval')
        gates, _ = outcomes([d]); self.assertTrue(gates['GATE-SEE-SUBSTITUTION']['triggered'])

    def test_clutter_systemic_boundary_deduplication_and_locality(self):
        d = finding(kind='clutter_pattern',code='SEL',severity='minor',ids=[f'LOC-{i}' for i in range(10)])
        gates, _ = outcomes([d]); self.assertTrue(gates['GATE-CLUTTER']['triggered'])
        duplicate = deepcopy(d); duplicate['defect_id']='DEFECT-DUP'
        self.assertEqual(10,core.systemic_defect_groups([d,duplicate])[0]['affected_count'])
        for change in ({'affected_item_ids':d['affected_item_ids'][:9]}, {'applicable_count':201}, {'affected_source_sections':['CHUNK-1']}):
            gates, _ = outcomes([d | change]); self.assertFalse(gates['GATE-CLUTTER']['triggered'])

    def test_evaluation_blockers_do_not_condemn_index(self):
        for kwargs, status in [({'uninspectable':2},'indeterminate'),({'complete':False},'indeterminate'),({'rows':[finding(kind='scope_failure')]},'invalid')]:
            gates, validity = outcomes(**({'rows':[]} | kwargs))
            self.assertEqual(status,validity['status'])
            self.assertFalse(any(gate['triggered'] for gate in gates.values()))
        gates, _ = outcomes([],attempt='unparseable')
        self.assertTrue(gates['GATE-STRUCTURE']['triggered'])

    def test_minor_singleton_cannot_cap_from_small_denominator(self):
        self.assertFalse(any(c['triggered'] for c in core.mechanics_aggregate_caps(1,1,['NODE-1'])))

    def test_nonbinding_ceiling_is_not_presented_as_applied(self):
        dim = {'dimension_id':'mechanics_consistency','components':[], 'denominators':{'components':[]},
               'pre_cap_percentage':'70','dimension_percentage':'70',
               'applied_cap':{'cap_id':'example','maximum_percentage':90,'affected_evidence_ids':['DEFECT-1']},
               'cap_evaluations':[{'cap_id':'example','threshold':{'severity':'major'},'observed':{'count':1}}]}
        lines=cli._presentation_calculation_basis(dim)
        self.assertTrue(any('Non-binding triggered ceiling' in row['equation'] for row in lines))
        self.assertFalse(any('Applied cap' in row['equation'] for row in lines))

    def test_frozen_v8_policy_is_rejected_under_revised_runtime(self):
        policy = policy_cli.build_policy({'source_scope': {'source_sha256':'1'*64,'page_map_sha256':'2'*64,'document_page_span':[1,10], 'chunk_manifest_sha256':'3'*64}, 'audience':{'label':'general','basis':'user_supplied','confidence':'high','rationale':'Test policy'}})
        cli.validate_v8_policy(policy)
        policy['policy_profile']['id'] = 'subject-index-standard-policy-v8'
        policy['policy_sha256'] = core.canonical_hash(policy, 'policy_sha256')
        with self.assertRaises(core.CalculationError):
            cli.validate_v8_policy(policy)

    def test_yellow_review_signals_keep_omissions_and_depth_visible(self):
        structure = {'defects': [], 'candidate_denominator': {'nodes':[{'node_id':'NODE-1','heading_path':['A','B','C']}]},
                     'scoring_context': {'cross_reference_applicability':{'warranted_reference_obligation_ids':['TASK-1']}}}
        calculation = {'dimensions':[{'dimension_id':'page_reference_reliability','reliability_provenance':{'locator_utility_assignments':[{'locator_id':'LOC-1','fit_category':'material_partial_fit'}]}}]}
        signals = cli._review_signals(structure, calculation)
        self.assertEqual(3,len(signals))
        self.assertTrue(all(row['color']=='yellow' and not row['individually_caps_or_gates'] for row in signals))

    def test_material_mismatch_and_missed_treatment_cannot_ground_gate(self):
        row = state('unsupported','substantive',fit='material_mismatch',codes=['LOC_POS'],severity='minor')
        for d in [finding(severity='minor'), finding(code='LOC_NEG', ids=['TREAT-1'])]:
            gates, _ = outcomes([d],[row])
            self.assertFalse(gates['GATE-GROUNDING']['triggered'])

    def test_systemic_partial_clutter_is_excluded(self):
        rows = [state('partially_supported','mixed',codes=['SEL'],severity='minor',locator_id=f'LOC-{i}') for i in range(10)]
        d = finding(kind='clutter_pattern',code='SEL',severity='minor',ids=[row['locator_id'] for row in rows])
        gates, _ = outcomes([d], rows)
        self.assertFalse(gates['GATE-CLUTTER']['triggered'])

    def test_major_no_fit_ceiling_lowers_otherwise_high_precision(self):
        good = [state('supported','substantive',locator_id=f'LOC-GOOD-{i}') for i in range(99)]
        bad = state('unsupported','absent',codes=['LOC_POS'],severity='major',fit='no_fit')
        result = cli.calculate_reliability(reliability_ledgers(good+[bad], defects=[finding()]),'full')
        self.assertGreater(Decimal(result['pre_cap_percentage']), 90)
        self.assertEqual('80',result['dimension_percentage'])

    def test_path_bound_delivered_locator_provenance_reaches_gate(self):
        d = finding(code='CMP',ids=['PATH-1'])
        row = {'locator_id':'LOC-1','path_id':'PATH-1','locator_severity':'major','fit_category':'severe_mismatch'}
        gates, _ = outcomes([d],[row])
        self.assertTrue(gates['GATE-COMPOUND']['triggered'])
        self.assertEqual('severe_mismatch',gates['GATE-COMPOUND']['qualifying_locator_evidence'][0]['fit_category'])

    def test_navigation_aggregate_threshold_does_not_promote_tiny_population(self):
        for count in (1,2,9):
            self.assertFalse(any(c['triggered'] for c in core.reference_rate_caps(count,count,[])))
            self.assertFalse(any(c['triggered'] for c in core.task_failure_caps(count,count,[])))
        self.assertTrue(all(c['triggered'] for c in core.reference_rate_caps(10,10,[])))
