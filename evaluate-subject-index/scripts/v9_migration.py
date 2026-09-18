"""The enumerated V8.2 → V9 representation migration; source bytes stay immutable."""
from copy import deepcopy
from runtime_profile import identity

SOURCE_PROFILE = 'subject-index-standard-policy-v8.2'
SOURCE_IDENTITIES = {
    'policy_profile': SOURCE_PROFILE,
    'rubric_version': 'subject-index-rubric-v8.2',
    'calculation_profile': 'subject-index-dimension-calculation-v7',
}


def policy_content(source):
    from study_comparison import POLICY_WRAPPERS, require
    require(source['schema_version'] == 'subject-index-evaluation-policy-v4', 'V9 migration requires the preserved V8.2 source policy')
    require(source['policy_profile']['id'] == SOURCE_PROFILE, 'Unexpected source policy profile')
    value = {k: deepcopy(v) for k, v in source.items() if k not in POLICY_WRAPPERS}
    value['schema_version'] = identity('subject-index-evaluation-policy-v4', profile='v9')
    value['policy_profile']['id'] = identity(SOURCE_PROFILE, profile='v9')
    for setting in value['content_policies'].values():
        require(setting['profile'] == SOURCE_PROFILE, 'Unexpected content-policy profile')
        setting['profile'] = identity(SOURCE_PROFILE, profile='v9')
    for metric in value['density_profile']['metrics']:
        require(metric['provenance'] == SOURCE_PROFILE, 'Unexpected density-policy provenance')
        metric['provenance'] = identity(SOURCE_PROFILE, profile='v9')
    # All other fields, including unknown extensions, remain fingerprinted verbatim.
    return value


def validate_source_policy(lock, release, source_state, path):
    import study_comparison as study
    from dimension_score_v8_cli import validate_v8_policy
    proof = lock['source_methodology']
    study.require(set(proof) == set(SOURCE_IDENTITIES) | {'source_policy_sha256', 'source_policy_file_sha256'}, 'Unexpected source methodology fields')
    study.require(all(proof.get(k) == v for k, v in SOURCE_IDENTITIES.items()), 'V9 source methodology must preserve V8.2 identity')
    study.require(path is not None and study.file_digest(path) == proof['source_policy_file_sha256'], 'Frozen source policy bytes mismatch')
    source = study.read(path)
    validate_v8_policy(source, profile='v8')
    study.require(source['freeze']['candidate_seen'] is False, 'Source policy must retain its candidate-blind freeze')
    study.require(source['policy_sha256'] == proof['source_policy_sha256'] == release['policy_sha256'], 'Frozen source policy identity mismatch')
    study.require(any(r['stage'] == 'define_policy' and r.get('schema_version') == 'subject-index-evaluation-policy-v4' and r['sha256'] == proof['source_policy_file_sha256'] for r in source_state['artifacts']), 'Source state does not register the preserved source policy')
    study.require(study.digest(policy_content(source)) == lock['policy_semantic_sha256'], 'V9 target policy changes substantive source settings')
    return source


def migrate_state_identity(state):
    state['schema_version'] = identity('subject-index-evaluation-state-v6', profile='v9')
    config = state['configuration']
    config['policy_profile'] = identity(SOURCE_PROFILE, profile='v9')
    config['rubric_version'] = identity(SOURCE_IDENTITIES['rubric_version'], profile='v9')
    config['scoring_identity'] = {'rubric_version': config['rubric_version'], 'dimension_calculation_profile': identity(SOURCE_IDENTITIES['calculation_profile'], profile='v9')}
if __name__ == "__main__":
    __import__("runtime_profile").require_public_cli()
