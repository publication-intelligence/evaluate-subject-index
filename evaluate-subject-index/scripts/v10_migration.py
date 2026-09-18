"""Explicit semantic V10 migration over immutable V8.2 source proof."""
from copy import deepcopy
from runtime_profile import identity, semantic_uncertainty
import v9_migration

SOURCE_IDENTITIES = v9_migration.SOURCE_IDENTITIES
CONTRACT = 'subject-index-evaluation-v10-decision-v3'
CONTRACT_SHA256 = '779fb8ffb21bc17fe87a23ee9160a124e013a094c08280b7bdb26fef40d2da50'
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
    value['schema_version'] = identity('subject-index-evaluation-policy-v4', profile='v10s' if semantic_uncertainty() else 'v10')
    value['policy_profile']['id'] = identity(v9_migration.SOURCE_PROFILE, profile='v10')
    value['policy_profile']['consequence_policy_reference'] = 'consequence-policy-v10.2.md'
    for setting in value['content_policies'].values():
        setting['profile'] = value['policy_profile']['id']
    for metric in value['density_profile']['metrics']:
        metric['provenance'] = value['policy_profile']['id']
    # Deliberate semantic amendment, unlike the invariant V9 migration.
    value['critical_gates'] = [{'gate_id': k, 'description': v, 'standard': True} for k,v in CRITICAL_GATES]
    require(tuple(row['gate_id'] for row in value['critical_gates']) == GATE_IDS, 'Unexpected core gate register')
    value['v10_contract'] = {'contract_id': CONTRACT, 'contract_sha256': CONTRACT_SHA256,
                             'consequence_policy': 'consequence-policy-v10.2.md',
                             'benchmark_access_profile': 'subject-index-benchmark-access-v10'}
    return value


def validate_source_policy(lock, release, source_state, path):
    import study_comparison as study
    # Reuse all source-byte/typed-registration checks, never the V9 target meaning.
    source = study.read(path)
    historical_lock = deepcopy(lock)
    historical_lock['policy_semantic_sha256'] = study.digest(v9_migration.policy_content(source))
    v9_migration.validate_source_policy(historical_lock, release, source_state, path)
    target = policy_content(source)
    target_hashes = {study.digest(target)}
    if semantic_uncertainty():
        # Decision-v1 states retain their reviewed V6 policy identity; new
        # decision-v3 amendments bind the active V7 identity.
        legacy = deepcopy(target)
        legacy['schema_version'] = identity('subject-index-evaluation-policy-v4', profile='v10')
        target_hashes.add(study.digest(legacy))
    study.require(lock['policy_semantic_sha256'] in target_hashes, 'V10 target policy differs from the approved semantic amendment')
    return source


def migrate_state_identity(state):
    state['schema_version'] = identity('subject-index-evaluation-state-v6')
    config = state['configuration']
    config['policy_profile'] = identity(v9_migration.SOURCE_PROFILE, profile='v10')
    config['rubric_version'] = identity(SOURCE_IDENTITIES['rubric_version'], profile='v10')
    config['scoring_identity'] = {'rubric_version': config['rubric_version'], 'dimension_calculation_profile': identity(SOURCE_IDENTITIES['calculation_profile'], profile='v10')}
if __name__ == "__main__":
    __import__("runtime_profile").require_public_cli()
