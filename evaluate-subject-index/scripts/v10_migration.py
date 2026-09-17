"""Explicit semantic V10 migration over immutable V8.2 source proof."""
from copy import deepcopy
from runtime_profile import identity
import v9_migration

SOURCE_IDENTITIES = v9_migration.SOURCE_IDENTITIES
CONTRACT = 'subject-index-evaluation-v10-decision-v2'
CONTRACT_SHA256 = '058399c34c0a6997965b39fb5906bde3634c2cdd74d3192bdfd6b4e55452512f'
GATE_IDS = (
    'GATE-WRONG-LOCATOR', 'GATE-BROKEN-REFERENCE', 'GATE-SCOPE-LOCATOR',
    'GATE-SYSTEMIC-UNSUPPORTED', 'GATE-CENTRAL-OMISSION', 'GATE-STANCE',
    'GATE-COMPOUND', 'GATE-SEE-SUBSTITUTION', 'GATE-CROSS-REFERENCE',
    'GATE-CLUTTER', 'GATE-GROUNDING', 'GATE-STRUCTURE',
)


def policy_content(source):
    from study_comparison import require
    from policy_cli import CRITICAL_GATES
    value = v9_migration.policy_content(source)
    value['schema_version'] = identity('subject-index-evaluation-policy-v4', profile='v10')
    value['policy_profile']['id'] = identity(v9_migration.SOURCE_PROFILE, profile='v10')
    value['policy_profile']['consequence_policy_reference'] = 'consequence-policy-v10.1.md'
    for setting in value['content_policies'].values():
        setting['profile'] = value['policy_profile']['id']
    for metric in value['density_profile']['metrics']:
        metric['provenance'] = value['policy_profile']['id']
    # Deliberate semantic amendment, unlike the invariant V9 migration.
    value['critical_gates'] = [{'gate_id': k, 'description': v, 'standard': True} for k,v in CRITICAL_GATES]
    require(tuple(row['gate_id'] for row in value['critical_gates']) == GATE_IDS, 'Unexpected core gate register')
    value['v10_contract'] = {'contract_id': CONTRACT, 'contract_sha256': CONTRACT_SHA256,
                             'consequence_policy': 'consequence-policy-v10.1.md',
                             'benchmark_access_profile': 'subject-index-benchmark-access-v10'}
    return value


def validate_source_policy(lock, release, source_state, path):
    import study_comparison as study
    # Reuse all source-byte/typed-registration checks, never the V9 target meaning.
    source = study.read(path)
    historical_lock = deepcopy(lock)
    historical_lock['policy_semantic_sha256'] = study.digest(v9_migration.policy_content(source))
    v9_migration.validate_source_policy(historical_lock, release, source_state, path)
    study.require(study.digest(policy_content(source)) == lock['policy_semantic_sha256'], 'V10 target policy differs from the approved semantic amendment')
    return source


def migrate_state_identity(state):
    state['schema_version'] = identity('subject-index-evaluation-state-v6', profile='v10')
    config = state['configuration']
    config['policy_profile'] = identity(v9_migration.SOURCE_PROFILE, profile='v10')
    config['rubric_version'] = identity(SOURCE_IDENTITIES['rubric_version'], profile='v10')
    config['scoring_identity'] = {'rubric_version': config['rubric_version'], 'dimension_calculation_profile': identity(SOURCE_IDENTITIES['calculation_profile'], profile='v10')}
