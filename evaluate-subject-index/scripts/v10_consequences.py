"""V10 evidence ownership and independent readiness, validity and release facts."""
from copy import deepcopy
import scoring_core as core
from v10_migration import GATE_IDS

ORDER = ('GATE-WRONG-LOCATOR', 'GATE-BROKEN-REFERENCE', 'GATE-STANCE',
         'GATE-COMPOUND', 'GATE-SEE-SUBSTITUTION', 'GATE-CROSS-REFERENCE',
         'GATE-SCOPE-LOCATOR', 'GATE-GROUNDING', 'GATE-SYSTEMIC-UNSUPPORTED',
         'GATE-CENTRAL-OMISSION', 'GATE-CLUTTER', 'GATE-STRUCTURE')


def delivered_severe_evidence(defect, locators):
    """Fit evidence is independent of the locator's severity label.

    Major/critical qualifies the structured defect consequence. This helper is
    exclusive to V10 quality gates; score and cap helpers retain their meaning.
    """
    affected=set(defect['affected_item_ids'])
    return [row for row in locators if {row['locator_id'],row.get('path_id')} & affected
            and row.get('complete_path_fit',row.get('fit_category')) in {'severe_mismatch','no_fit'}]


def gate_outcomes(policy, structure, calculation, destination_evidence, legacy):
    """Reuse the frozen predicates, tighten ownership and delivered populations.

    Remove whole conflicting findings/groups; never manufacture residual spread
    by subtracting IDs from an already qualified systemic group.
    """
    core.require(not any(row['defect_kind'] == 'scope_failure' for row in structure['defects']), 'VALIDITY-SOURCE-SPAN', 'Source binding failure cannot be a V10 candidate-quality defect.')
    core.require(tuple(row['gate_id'] for row in policy['critical_gates']) == GATE_IDS,
                 'v10_gate_register', 'V10 requires exactly its twelve core quality gates.')
    direct_locators, direct_references, assessment = destination_evidence or ([], [], {'blockers': []})
    invalid_source = any(row['blocker_id'] == 'GATE-ASSESSMENT-SOURCE' for row in assessment['blockers'])
    from runtime_profile import semantic_uncertainty
    semantic_blocks=[row for row in assessment['blockers'] if semantic_uncertainty() and 'semantic_unknown_axes' in row]
    general_blocked={item for row in assessment['blockers'] if row not in semantic_blocks for item in row['affected_item_ids']}
    dependencies={'GATE-WRONG-LOCATOR':{'keep','complete_path_fit'},'GATE-SCOPE-LOCATOR':{'complete_path_fit'},
                  'GATE-COMPOUND':{'complete_path_fit'},'GATE-GROUNDING':{'complete_path_fit'},
                  'GATE-SYSTEMIC-UNSUPPORTED':{'complete_path_fit'},'GATE-CLUTTER':{'treatment'},
                  'GATE-STRUCTURE':set(),'GATE-BROKEN-REFERENCE':set()}
    def blocked_for(gate):
        result=set(general_blocked)
        needed=dependencies.get(gate,{'keep','complete_path_fit','treatment'})
        for block in semantic_blocks:
            result.update(block.get('dependent_reference_ids',[]))
            if needed & set(block['semantic_unknown_axes']):result.update(block['affected_item_ids'])
        return result
    blocked = blocked_for('GATE-WRONG-LOCATOR')
    direct_locators=[row for row in direct_locators if not {row['locator_id'],row.get('path_id')} & blocked]
    direct_references=[row for row in direct_references if row['reference_id'] not in blocked_for('GATE-BROKEN-REFERENCE')]
    direct_owned = {row['locator_id'] for row in direct_locators} | {row['reference_id'] for row in direct_references}
    provenance = next(d for d in calculation['dimensions'] if d['dimension_id'] == 'page_reference_reliability')['reliability_provenance']
    locators = [dict(row, path_id=provenance.get('locator_path_bindings', {}).get(row['locator_id'],row.get('path_id')))
                for row in provenance.get('locator_utility_assignments', [])]
    refs = {row['reference_id']: row for row in structure.get('cross_reference_judgments', [])}
    delivered = set(structure['candidate_denominator']['cross_reference_ids'])
    bad_ids = {row['locator_id'] for row in locators if row.get('fit_category', row.get('complete_path_fit')) in {'severe_mismatch','no_fit'}}
    definitions = {row['gate_id']: row for row in policy['critical_gates']}
    owned = set(direct_owned)
    output = {}
    def atomic(row):
        return set(row['affected_item_ids']) | {x['locator_id'] for x in delivered_severe_evidence(row,locators)}
    def eligible(row, gate):
        if invalid_source:
            if gate not in {'GATE-BROKEN-REFERENCE','GATE-CROSS-REFERENCE','GATE-STRUCTURE'}: return False
            if gate == 'GATE-CROSS-REFERENCE' and row['defect_kind'] != 'circular_or_chained_reference': return False
        ids = atomic(row)
        if ids & blocked: return False
        # Atomic ownership prevents duplicate labels for one predicate.  It does
        # not erase a separately measured systemic-prevalence consequence.
        if gate not in {'GATE-CENTRAL-OMISSION','GATE-CLUTTER','GATE-STRUCTURE','GATE-SYSTEMIC-UNSUPPORTED'} and ids & owned: return False
        if gate == 'GATE-SEE-SUBSTITUTION':
            return any(x in delivered and refs.get(x,{}).get('reference_type', refs.get(x,{}).get('target_resolution',{}).get('reference_type')) == 'see' for x in row['affected_item_ids'])
        if gate == 'GATE-SYSTEMIC-UNSUPPORTED':
            return bool(row['affected_item_ids']) and set(row['affected_item_ids']) <= bad_ids
        if gate == 'GATE-CROSS-REFERENCE':
            return bool(row['affected_item_ids']) and bool(set(row['affected_item_ids']) & delivered)
        return True
    for gate in ORDER:
        blocked = blocked_for(gate)
        filtered = deepcopy(structure)
        filtered['defects'] = [row for row in structure['defects'] if eligible(row,gate)]
        result = legacy({'critical_gates':[definitions[gate]]}, filtered, calculation,
                        destination_evidence=(direct_locators,direct_references,assessment),
                        bad_locator_evidence=delivered_severe_evidence)[0]
        if gate == 'GATE-SYSTEMIC-UNSUPPORTED':
            rows = [row for row in structure['defects']
                    if row['dimension_owner'] == 'page_reference_reliability'
                    and eligible(row, gate)]
            result['systemic_groups'] = core.systemic_defect_groups(rows)
            keep = {x for group in result['systemic_groups'] for x in group['defect_ids']}
            result['consequence_evidence'] = [row for row in rows if row['defect_id'] in keep]
            result['qualifying_locator_evidence'] = [deepcopy(row) for row in locators
                if row['locator_id'] in {x for r in result['consequence_evidence'] for x in r['affected_item_ids']}]
        # Systemic groups must be formed before ownership filtering. A root
        # containing direct evidence cannot be revived from its residual rows.
        if gate in {'GATE-SYSTEMIC-UNSUPPORTED','GATE-CROSS-REFERENCE','GATE-CLUTTER'}:
            ownership_taint = blocked if gate == 'GATE-SYSTEMIC-UNSUPPORTED' else direct_owned | blocked
            tainted_roots = {(row.get('root_cause_family'), item.split('-',1)[0], row.get('applicable_count',0)) for row in structure['defects'] if atomic(row) & ownership_taint for item in row['affected_item_ids']}
            groups = [g for g in result['systemic_groups'] if (g['root_cause_family'],g['item_family'],g['applicable_count']) not in tainted_roots]
            if gate in {'GATE-SYSTEMIC-UNSUPPORTED','GATE-CLUTTER'}:
                keep = {x for g in groups for x in g['defect_ids']}
                result['consequence_evidence'] = [row for row in result['consequence_evidence'] if row['defect_id'] in keep]
            else:
                # A material individual XRF can survive a rejected systemic
                # group if its own complete predicate independently qualifies.
                keep = {x for g in groups for x in g['defect_ids']}
                result['consequence_evidence'] = [row for row in result['consequence_evidence'] if row['defect_id'] in keep or core.material_consequence(row)]
            result['systemic_groups'] = groups
            result['defect_ids'] = sorted(row['defect_id'] for row in result['consequence_evidence'])
            result['triggered'] = bool(result['consequence_evidence'])
            result['affected_evidence_ids'] = sorted({x for row in result['consequence_evidence'] for x in row['affected_item_ids']})
            result['qualifying_locator_evidence'] = [row for row in result['qualifying_locator_evidence'] if row['locator_id'] in result['affected_evidence_ids']]
        if result['triggered'] and gate not in {'GATE-CENTRAL-OMISSION','GATE-CLUTTER','GATE-STRUCTURE'}:
            owned.update(x for row in result['consequence_evidence'] for x in atomic(row))
        result['threshold_reason'] = ('Qualifying structured V10 evidence under the recorded predicate and ownership order.' if result['triggered'] else 'No independently qualifying evidence crosses this threshold.')
        output[gate] = result
    return [output[gate] for gate in GATE_IDS]


def readiness(result):
    triggered = [row['gate_id'] for row in result['critical_gates'] if row['triggered']]
    validity = result['evaluation_validity']['status']
    assessment = result['gate_assessment']
    status = 'not_ready' if triggered else 'indeterminate' if validity != 'valid' or assessment['status'] != 'sufficient' else 'ready'
    return {'status':status, 'triggered_gate_ids':triggered, 'assessment_blockers':deepcopy(assessment['blockers'])}


def authoritative(result):
    validity = result['evaluation_validity']['status']
    return {'status': 'invalid' if validity == 'invalid' else 'authoritative' if validity == 'valid' and result['gate_assessment']['status'] == 'sufficient' else 'indeterminate'}


def outcome_fields(result):
    return {'method_readiness': readiness(result), 'authoritative_evaluation': authoritative(result),
            'human_release_decision': {'status':'not_recorded'}}
if __name__ == "__main__":
    __import__("runtime_profile").require_public_cli()
