"""Study identities derived from evidence, never from displayed methodology labels."""
from runtime_profile import identity as runtime_identity, percentage_native, is_v10, semantic_uncertainty, versioned_cli, migration_module
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile

from schema_validation import schema_errors


BENCHMARK_WRAPPERS = {
    'schema_version', 'benchmark_sha256', 'benchmark_id', 'version', 'evaluation_id',
    'source_sha256', 'policy_sha256', 'page_map_sha256', 'chunk_manifest_sha256',
    'candidate_blindness', 'freeze', 'synthesis', 'compatibility_import',
    'retrospective_benchmark_migration', 'source_title', 'source_first_omission_pass',
    'synthesis_audit', 'quality_control', 'provenance', 'supersedes', 'change_ledger',
}
POLICY_WRAPPERS = {'policy_id', 'policy_sha256', 'freeze', 'retrospective_migration', 'retrospective_study_migration'}


def digest(value):
    # Scoring reads JSON decimals exactly; study files historically use JSON
    # numbers. Preserve that canonical encoding and reject lossy conversions.
    from decimal import Decimal
    def number(item):
        if isinstance(item, Decimal) and item.is_finite():
            result = float(item)
            if Decimal(str(result)) == item:
                return result
        raise TypeError("Study identity contains an unsupported or lossy JSON number")
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=number).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    value = json.loads(Path(path).read_text())
    require(isinstance(value, dict), f'Expected JSON object: {path}')
    return value


def normalized_benchmark(benchmark):
    value = deepcopy(benchmark)
    for row in value['relationships']:
        require(not ('type' in row and 'relationship_type' in row), 'Ambiguous relationship normalization')
        if 'type' in row:
            row['relationship_type'] = row.pop('type')
    return value


def benchmark_semantic_hash(benchmark):
    value = normalized_benchmark(benchmark)
    return digest({k: v for k, v in value.items() if k not in BENCHMARK_WRAPPERS})


def policy_semantic_hash(policy):
    if policy.get('schema_version') == 'subject-index-study-policy-template-v1':
        require(policy.get('template_sha256') == digest({k: v for k, v in policy.items() if k != 'template_sha256'}), 'Study policy template self-hash mismatch')
        policy = policy['policy_semantic_content']
    return digest({k: v for k, v in policy.items() if k not in POLICY_WRAPPERS})


def validate_lock(lock):
    require(not schema_errors(lock, 'study-benchmark-lock.schema.json'), 'Invalid study lock schema')
    if percentage_native():
        require(lock['release']['lineage']['kind'] == 'current_source_freeze', 'Percentage-runtime cutover requires the reviewed current V8.2 source freeze')
    require(lock['lock_sha256'] == digest({k: v for k, v in lock.items() if k != 'lock_sha256'}), 'Study lock self-hash mismatch')
    chunks = lock['density_basis']['chunks']
    require(len({r['chunk_id'] for r in chunks}) == len(chunks), 'Duplicate density chunk')
    require(lock['density_basis']['measurement_sha256'] == digest(chunks), 'Density basis digest mismatch')
    span = lock['source_scope']['document_page_span']
    require(span[0] <= span[1], 'Invalid study scope')
    for label in (lock['release']['release_id'], lock['release']['benchmark_id'], lock['density_basis']['basis_id']):
        public_label(label)


def validate_release(lock, benchmark, benchmark_bytes_sha, descriptor=None, descriptor_bytes_sha=None):
    validate_lock(lock)
    release = lock['release']
    lineage = release['lineage']
    require(benchmark.get('benchmark_sha256') == digest({k: v for k, v in benchmark.items() if k != 'benchmark_sha256'}), 'Release benchmark self-hash mismatch')
    for key in ('benchmark_id', 'version'):
        require(benchmark[key] == release[key], f'Release {key} mismatch')
    require(benchmark_bytes_sha == release['benchmark_file_sha256'], 'Release benchmark bytes mismatch')
    require(benchmark['benchmark_sha256'] == release['benchmark_sha256'], 'Release benchmark identity mismatch')
    if lineage['kind'] == 'git_freeze':
        require(descriptor is not None and descriptor_bytes_sha == release['release_descriptor_sha256'], 'Release descriptor bytes differ from study lock')
        require(descriptor.get('release_sha256') == digest({k:v for k,v in descriptor.items() if k != 'release_sha256'}), 'Release descriptor self-hash mismatch')
        require(descriptor['release_id'] == release['release_id'] and descriptor['artifact_freeze']['commit'] == lineage['artifact_freeze_commit'], 'Release lineage mismatch')
        expected = descriptor['artifacts']['benchmark']
        require(expected['file_sha256'] == benchmark_bytes_sha and expected['canonical_sha256'] == benchmark['benchmark_sha256'], 'Descriptor benchmark mismatch')
    require(benchmark_semantic_hash(benchmark) == lock['source_benchmark_semantic_sha256' if is_v10() else 'benchmark_semantic_sha256'], 'Mixed semantic benchmark family')
    for key in ('source_sha256', 'page_map_sha256', 'chunk_manifest_sha256'):
        require(benchmark[key] == lock['source_scope'][key], f'Release {key} mismatch')


def public_label(value):
    label = value.strip()
    require(not label.lower().startswith('file:') and not PurePosixPath(label).is_absolute() and not PureWindowsPath(label).drive and not PureWindowsPath(label).is_absolute(), 'Public identity label must not be an absolute path')
    return value


def public_release_identity(release):
    # Private transport locations never participate in a public comparison.
    fields = ('release_id', 'benchmark_id', 'version', 'benchmark_sha256', 'benchmark_file_sha256', 'release_descriptor_sha256')
    value = {key: deepcopy(release[key]) for key in fields if key in release}
    for key in ('release_id', 'benchmark_id'):
        public_label(value[key])
    lineage_fields = ('kind', 'artifact_freeze_commit', 'source_only_state_sha256', 'draft_file_sha256', 'review_file_sha256', 'review_inventory_file_sha256')
    value['lineage'] = {key: release['lineage'][key] for key in lineage_fields if key in release['lineage']}
    return value


def public_density_identity(density):
    rows = [{'chunk_id': public_label(row['chunk_id']), 'indexable_source_words': row['indexable_source_words'], 'source_artifact': {'sha256': row['source_artifact']['sha256']}} for row in density['chunks']]
    return {'basis_id': public_label(density['basis_id']), 'chunks': rows, 'measurement_sha256': digest(rows)}


def benchmark_identity(benchmark):
    public_label(benchmark['benchmark_id'])
    return {'benchmark_id': benchmark['benchmark_id'], 'version': benchmark['version'],
            'benchmark_sha256': benchmark['benchmark_sha256'],
            'benchmark_semantic_sha256': benchmark_semantic_hash(benchmark)}


def evaluation_identity(*, benchmark, policy, structure, manifest, audit_mode, rubric, calculation_profile, lock=None):
    scope = {k: policy['source_scope'][k] for k in ('source_sha256', 'document_page_span', 'page_map_sha256', 'chunk_manifest_sha256')}
    rows = structure['density']['chapter_measurements']
    measurements = [{'chunk_id': r['chunk_id'], 'indexable_source_words': r['indexable_source_words']} for r in rows]
    ordered_chunks = [r['chunk_id'] for r in sorted(manifest['chunks'], key=lambda r: r['packet_order'])]
    require([r['chunk_id'] for r in measurements] == ordered_chunks, 'Density order/population differs from frozen manifest')
    identity = {'source_scope': scope, 'benchmark_semantic_sha256': benchmark_semantic_hash(benchmark),
                'policy_semantic_sha256': policy_semantic_hash(policy), 'policy_profile': policy['policy_profile']['id'],
                'audit_mode': audit_mode, 'rubric_version': rubric, 'calculation_profile': calculation_profile,
                'density_measurements_sha256': digest(measurements), 'release': None, 'density_basis': None}
    for key in ('source_sha256', 'page_map_sha256', 'chunk_manifest_sha256'):
        require(benchmark[key] == scope[key], f'Benchmark {key} differs from evaluated scope')
    require(benchmark['policy_sha256'] == policy['policy_sha256'], 'Benchmark policy wrapper differs from evaluated policy')
    if lock is not None:
        validate_lock(lock)
        for key in ('source_scope', 'benchmark_semantic_sha256', 'policy_semantic_sha256', 'policy_profile', 'audit_mode', 'rubric_version', 'calculation_profile'):
            require(identity[key] == lock[key], f'Study comparison mismatch: {key}')
        expected = [{k: r[k] for k in ('chunk_id', 'indexable_source_words')} for r in lock['density_basis']['chunks']]
        require(measurements == expected, 'Study comparison mismatch: exact density measurement map')
        if percentage_native():
            identity['source_methodology'] = deepcopy(lock['source_methodology'])
            if is_v10():
                identity['benchmark_access'] = {k: deepcopy(lock['benchmark_access'][k]) for k in ('overlay_sha256','effective_benchmark_semantic_sha256','frozen_at')}
                identity['benchmark_access']['overlay_file_sha256'] = lock['benchmark_access']['overlay']['sha256']
                identity['benchmark_access']['review_file_sha256'] = lock['benchmark_access']['review']['sha256']
        identity['release'] = public_release_identity(lock['release'])
        identity['density_basis'] = public_density_identity(lock['density_basis'])
    identity['identity_sha256'] = digest(identity)
    return identity


def compare_identities(identities):
    require(len(identities) >= 2, 'Comparison requires at least two evaluations')
    for identity in identities:
        require(identity.get('identity_sha256') == digest({k: v for k, v in identity.items() if k != 'identity_sha256'}), 'Comparison identity self-hash mismatch')
        require(identity.get('release') is not None and identity.get('density_basis') is not None, 'Comparison requires verified study release lineage and density basis')
    if any('execution_contract' in identity for identity in identities):
        require(all('execution_contract' in identity for identity in identities),'Corrected and baseline execution identities cannot mix')
        require(all(identity['execution_contract']==identities[0]['execution_contract'] for identity in identities),'Mixed semantic execution compatibility')
    keys = ('source_scope', 'benchmark_semantic_sha256', 'release', 'policy_semantic_sha256', 'policy_profile', 'audit_mode', 'rubric_version', 'calculation_profile', 'density_basis', 'density_measurements_sha256')
    if percentage_native():
        require(all('source_methodology' in row for row in identities), 'Percentage-runtime comparison requires preserved source methodology')
        keys += ('source_methodology',)
    if is_v10():
        require(all('benchmark_access' in row for row in identities), 'V10 comparison requires independently reviewed access proof')
        keys += ('benchmark_access',)
    mismatches = [key for key in keys if any(row[key] != identities[0][key] for row in identities[1:])]
    require(not mismatches, 'Incomparable evaluations: ' + ', '.join(mismatches))
    return deepcopy(identities[0])


def bound_document(root, reference):
    path = (root / reference['path']).resolve()
    require(path.is_relative_to(root.resolve()), 'Study artifact escapes evaluation directory')
    require(path.is_file() and file_digest(path) == reference['sha256'], f'Study artifact bytes changed: {reference["path"]}')
    return read(path)


def registered_document(state, state_path, stage, schema):
    records = [r for r in state['artifacts'] if r['stage'] == stage and r.get('schema_version') == schema]
    if not records and semantic_uncertainty() and schema == 'subject-index-evaluation-policy-v7':
        # Read preserved V10 policy bytes after a study adopts the native V10
        # execution runtime. New studies register V7 directly.
        records = [r for r in state['artifacts'] if r['stage'] == stage and r.get('schema_version') == 'subject-index-evaluation-policy-v6']
    require(len(records) == 1, f'Expected one registered {schema}')
    return bound_document(state_path.parent, records[0]), records[0]


def verified_scope(lock, page_map, manifest):
    from page_chunk_cli import validated_chunk_owners
    from candidate_preparation_cli import PreparationError
    for document, name, field in ((page_map,'page-map.schema.json','page_map_sha256'), (manifest,'chunk-manifest.schema.json','chunk_manifest_sha256')):
        require(not schema_errors(document,name), f'Invalid selected {name}')
        require(document[field] == digest({k:v for k,v in document.items() if k != field}) == lock['source_scope'][field], f'Selected {field} does not reconstruct')
    require(page_map['source_sha256'] == lock['source_scope']['source_sha256'], 'Selected map uses another source')
    require(manifest['page_map_sha256'] == page_map['page_map_sha256'], 'Manifest uses another page map')
    try:
        chunks, owners = validated_chunk_owners(manifest,page_map)
    except PreparationError as exc:
        raise ValueError(str(exc)) from exc
    keys=[r['normalized_locator_key'] for r in page_map['pages'] if r['accepts_index_locators']]
    require(None not in keys and len(set(keys)) == len(keys), 'Selected map has ambiguous indexable locator keys')
    span=lock['source_scope']['document_page_span']
    require(set(owners) == {r['document_page'] for r in page_map['pages'] if r['in_evaluation_scope']}, 'Study chunks do not cover selected scope exactly')
    require(all(span[0] <= p <= span[1] for p in owners), 'Study owned pages exceed source span')
    return chunks, owners


def validate_density_evidence(lock, root, page_map, manifest):
    chunks, owners = verified_scope(lock,page_map,manifest)
    require([r['chunk_id'] for r in sorted(manifest['chunks'],key=lambda r:r['packet_order'])] == [r['chunk_id'] for r in lock['density_basis']['chunks']], 'Density map order/population mismatch')
    measurements = {}
    for row in lock['density_basis']['chunks']:
        document = bound_document(root, row['source_artifact'])
        if document.get('schema_version') == 'source-density-measurement-v1':
            key = row['source_artifact']['sha256']
            if key not in measurements:
                validate_density_measurement(document, lock, page_map, owners)
                measurements[key] = {r['chunk_id']:r for r in document['chunks']}
            require(measurements[key][row['chunk_id']]['indexable_source_words'] == row['indexable_source_words'], 'Standalone density measurement differs from locked chunk count')
            continue
        require(document['chunk']['chunk_id'] == row['chunk_id'], 'Density evidence chunk mismatch')
        require(document['page_review']['indexable_source_words'] == row['indexable_source_words'], 'Density evidence word count mismatch')
        expected = sorted(p for p,c in owners.items() if c == row['chunk_id'])
        require(document['chunk']['owned_document_pages'] == expected, 'Density evidence owned-page population mismatch')
        review=document['page_review']
        require(review.get('complete') is True and review.get('expected_owned_pages') == review.get('reviewed_owned_pages') == len(expected), 'Incomplete density page review')
        # Some historical chunks predate embedded identities. The approved lock binds
        # their exact bytes to this verified scope; never synthesize missing fields.
        for source in (document,document.get('provenance',{})):
            for key in ('source_sha256','page_map_sha256','chunk_manifest_sha256'):
                if key in source:
                    require(source[key] == lock['source_scope'][key], f'Density evidence {key} mismatch')


def validate_density_measurement(document, lock, page_map, owners):
    require(not schema_errors(document,'source-density-measurement.schema.json'), 'Invalid standalone density measurement')
    for key in ('source_sha256','page_map_sha256','chunk_manifest_sha256'):
        require(document[key] == lock['source_scope'][key], f'Density measurement {key} mismatch')
    pages=document['pages']
    require(len(pages) == len(owners) and {r['document_page'] for r in pages} == set(owners), 'Density measurement page population mismatch')
    labels={r['document_page']:r['source_page_label'] for r in page_map['pages']}
    require(all(r['source_page_label']==labels[r['document_page']] for r in pages), 'Density measurement source labels differ')
    counts={r['document_page']:r['indexable_source_words'] for r in pages}
    rows=document['chunks']
    require([r['chunk_id'] for r in rows] == [r['chunk_id'] for r in lock['density_basis']['chunks']], 'Density measurement chunk population/order mismatch')
    for row in rows:
        expected=sorted(p for p,c in owners.items() if c==row['chunk_id'])
        require(row['owned_document_pages']==expected, 'Density measurement owned-page population mismatch')
        require(row['indexable_source_words']==sum(counts[p] for p in expected), 'Density measurement chunk total does not recompute')
    require(document['total_indexable_source_words']==sum(counts.values()), 'Density measurement total does not recompute')


def load_study_binding(state, state_path):
    binding = state.get('study_comparison')
    if binding is None:
        return None
    require(not schema_errors(binding, 'retrospective-study-binding.schema.json'), 'Invalid retrospective study binding')
    root = state_path.parent
    lock = bound_document(root, binding['lock'])
    release = bound_document(root, binding['release_benchmark'])
    descriptor = bound_document(root, binding['release_descriptor']) if 'release_descriptor' in binding else None
    validate_release(lock, release, binding['release_benchmark']['sha256'], descriptor, binding.get('release_descriptor',{}).get('sha256'))
    bound_document(root,binding['release_review'])
    inventory_path = None
    if lock['release']['lineage']['kind'] != 'current_source_freeze':
        bound_document(root,binding['release_review_inventory'])
        inventory_path = root/binding['release_review_inventory']['path']
    else:
        require('release_review_inventory' not in binding, 'Current screening inventory must remain temporary')
    if lock['release']['lineage']['kind'] in ('native_source_freeze', 'current_source_freeze'):
        for name in ('release_state','release_draft'):
            bound_document(root,binding[name])
        validate_native_lineage(lock,release,*[(root/binding[name]['path']) for name in ('release_state','release_draft','release_review')],inventory_path,policy_path=(root/binding['release_policy']['path']) if percentage_native() else None)
    else:
        from study_cli import validate_release_review
        validate_release_review(release,descriptor,root/binding['release_benchmark']['path'],root/binding['release_review']['path'],root/binding['release_review_inventory']['path'],root/binding['release_draft']['path'] if 'release_draft' in binding else None)
    approval = bound_document(root, binding['approval'])
    require(not schema_errors(approval, 'retrospective-benchmark-approval.schema.json'), 'Invalid retrospective approval')
    require(approval['study_lock_sha256'] == lock['lock_sha256'] and approval['target_benchmark_sha256'] == lock['release']['benchmark_sha256'], 'Approval does not bind selected study release')
    require(binding['historical_freeze']==release['freeze'], 'Historical release freeze differs from preserved binding')
    prior = bound_document(root, binding['prior_state'])
    require(prior.get('candidate') is not None and approval['previous_state_sha256'] == binding['prior_state']['sha256'], 'Retrospective approval/state lineage mismatch')
    if percentage_native():
        from state_cli import validate_state
        errors, _ = validate_state(prior, check_files=False, profile='v8')
        require(not errors, 'Invalid preserved V8 prior state')
        bound_document(root, binding['release_policy'])
    previous_policy, _ = registered_document(prior, root / binding['prior_state']['path'], 'define_policy', runtime_identity('subject-index-evaluation-policy-v4', profile='v8' if percentage_native() else None))
    previous_benchmark, _ = registered_document(prior, root / binding['prior_state']['path'], 'benchmark_freeze', 'source-subject-benchmark-v2')
    require(approval['previous_policy_sha256']==previous_policy['policy_sha256'] and approval['previous_benchmark_sha256']==previous_benchmark['benchmark_sha256'], 'Approval historical identities differ')
    require(approval['target_policy_semantic_sha256']==lock['policy_semantic_sha256'], 'Approval target policy differs from study lock')
    # Evidence paths in the immutable lock resolve beside its preserved copy.
    page_map,_ = registered_document(state,state_path,'page_mapping','page-map-v1')
    manifest,_ = registered_document(state,state_path,'chunk_definition','chunk-manifest-v1')
    validate_density_evidence(lock, (root / binding['lock']['path']).parent, page_map, manifest)
    if is_v10():
        from v10_access import validate_access
        validate_access(lock, release, (root / binding['lock']['path']).parent)
    return lock


def preflight_state(state, state_path, *, require_density=False, allow_pending_execution=False):
    execution = None
    if semantic_uncertainty():
        if not allow_pending_execution or state.get('execution_compatibility'):
            from v10_execution import bound_execution
            execution=bound_execution(state,state_path)
    elif state.get('execution_compatibility'):
        require(False,'This state requires its explicitly adopted semantic execution runtime')
    if percentage_native():
        require(state.get("study_comparison") is not None, "The percentage runtime requires a preserved V8.2 source/methodology binding")
    lock = load_study_binding(state, state_path)
    if lock is None:
        for stage, schema, field in (('define_policy',runtime_identity('subject-index-evaluation-policy-v4'),'retrospective_study_migration'), ('benchmark_freeze','source-subject-benchmark-v2','retrospective_benchmark_migration')):
            rows = [r for r in state.get('artifacts', []) if r['stage']==stage and r.get('schema_version')==schema]
            if len(rows)==1:
                require(field not in bound_document(state_path.parent,rows[0]), 'Study binding is missing from a retrospectively migrated evaluation')
        return None
    benchmark, _ = registered_document(state, state_path, 'benchmark_freeze', 'source-subject-benchmark-v2')
    policy, _ = registered_document(state, state_path, 'define_policy', runtime_identity('subject-index-evaluation-policy-v4'))
    manifest, _ = registered_document(state, state_path, 'chunk_definition', 'chunk-manifest-v1')
    require(benchmark['benchmark_sha256'] == digest({k:v for k,v in benchmark.items() if k != 'benchmark_sha256'}), 'Current benchmark self-hash mismatch')
    require(policy['policy_sha256'] == digest({k:v for k,v in policy.items() if k != 'policy_sha256'}), 'Current policy self-hash mismatch')
    require(not schema_errors(policy, 'evaluation-policy-v4.schema.json'), 'Invalid study policy')
    migration=policy.get('retrospective_study_migration')
    if migration:
        approvals=[r for r in state['artifacts'] if r['sha256']==migration['approval_sha256'] and r.get('schema_version')=='subject-index-retrospective-benchmark-approval-v1']
        require(bool(approvals), 'Study policy migration approval is not preserved')
        policy_approval=bound_document(state_path.parent,approvals[0])
        previous=bound_document(state_path.parent,migration['previous_policy']['artifact'])
        require(migration['study_lock_sha256']==policy_approval['study_lock_sha256'] and migration['target_policy_semantic_sha256']==policy_approval['target_policy_semantic_sha256'], 'Study policy migration approval differs')
        require(previous['policy_sha256']==migration['previous_policy']['policy_sha256'] and previous['freeze']==migration['previous_policy']['freeze'], 'Preserved policy provenance differs')

    scope = {key: policy['source_scope'][key] for key in lock['source_scope']}
    require(manifest['chunk_manifest_sha256'] == scope['chunk_manifest_sha256'], 'Registered chunk manifest differs from study scope')
    require(scope == lock['source_scope'] and state['source']['sha256'] == scope['source_sha256'] and state['source']['document_page_span'] == scope['document_page_span'], 'Study source/scope mismatch')
    require(benchmark_semantic_hash(benchmark) == lock['benchmark_semantic_sha256'], 'Mixed semantic benchmark family')
    require(benchmark['policy_sha256'] == policy['policy_sha256'], 'Study benchmark policy wrapper mismatch')
    require(policy_semantic_hash(policy) == lock['policy_semantic_sha256'], 'Study semantic policy mismatch')
    retrospective=benchmark.get('retrospective_benchmark_migration')
    if retrospective:
        require(retrospective.get('candidate_seen') is True and retrospective.get('fresh_review_performed') is False and retrospective.get('audit_transfer_authorized') is False, 'Benchmark retrospective provenance is inconsistent')

    require(policy['policy_profile']['id'] == lock['policy_profile'], 'Study policy profile mismatch')
    require(state['configuration']['audit_mode'] == lock['audit_mode'] == policy['audit_design']['mode'], 'Study audit mode mismatch')
    scoring = state['configuration']['scoring_identity']
    require(scoring['rubric_version'] == state['configuration']['rubric_version'] == lock['rubric_version'], 'Study rubric mismatch')
    require(scoring['dimension_calculation_profile'] == lock['calculation_profile'], 'Study calculation profile mismatch')
    require([r['chunk_id'] for r in sorted(manifest['chunks'], key=lambda r: r['packet_order'])] == [r['chunk_id'] for r in lock['density_basis']['chunks']], 'Study density chunk population/order mismatch')
    for key in ('source_sha256', 'page_map_sha256', 'chunk_manifest_sha256'):
        require(benchmark[key] == scope[key], f'Study benchmark {key} mismatch')
    if state.get('candidate'):
        require(state['candidate']['benchmark_sha256'] == benchmark['benchmark_sha256'], 'Candidate benchmark binding is stale')
    for record in state['artifacts']:
        if record.get('schema_version') in ({'missing-access-audit-v1','missing-access-audit-v2'} if __import__('runtime_profile').semantic_uncertainty() else {'missing-access-audit-v1'}) and record['stage'] == 'missing_access_audit':
            document = bound_document(state_path.parent, record)
            require(document['benchmark_sha256'] == benchmark['benchmark_sha256'], 'Registered audit uses a different benchmark')
    candidate_access_review = None
    if is_v10() and (require_density or state['stages']['structure_audit']['status'] == 'completed'):
        from v10_candidate_access import bound_review
        candidate_access_review = bound_review(state, state_path, benchmark, lock)
    if require_density:
        structure, _ = registered_document(state, state_path, 'structure_audit', 'structure-audit-v6')
        result = evaluation_identity(benchmark=benchmark, policy=policy, structure=structure, manifest=manifest,
            audit_mode=lock['audit_mode'], rubric=lock['rubric_version'], calculation_profile=lock['calculation_profile'], lock=lock)
        if execution is not None:
            result['execution_contract']=execution
        if candidate_access_review is not None:
            result['candidate_access_review'] = {key:candidate_access_review[key] for key in ('receipt_file_sha256','status','requirement_count')}
            result['identity_sha256'] = digest({k:v for k,v in result.items() if k != 'identity_sha256'})
        return result
    return lock


def validate_native_lineage(lock, release, state_path, draft_path, review_path, inventory_path=None, *, policy_path=None):
    from benchmark_review_cli import build_inventory, json_bytes, legacy_registered_hash, native_v8_review_errors, validate_final_data
    lineage=lock['release']['lineage']
    require(lineage['kind'] in ('native_source_freeze', 'current_source_freeze'),'Expected native source-only lineage')
    current = lineage['kind'] == 'current_source_freeze'
    proofs = [(state_path,'source_only_state_sha256'),(draft_path,'draft_file_sha256'),(review_path,'review_file_sha256')]
    if not current:
        proofs.append((inventory_path,'review_inventory_file_sha256'))
    else:
        require(inventory_path is None, 'Current screening inventory must remain temporary; omit --release-review-inventory')
    for path,key in proofs:
        require(path is not None and file_digest(path)==lineage[key],f'Native release {key} mismatch')
    state=read(state_path)
    if percentage_native():
        require(current, 'Percentage-runtime cutover requires the reviewed current V8.2 source freeze')
        migration_module().validate_source_policy(lock, release, state, policy_path)
    require(state.get('candidate') is None and not any(r.get('stage')=='candidate_normalization' for r in state['artifacts']), 'Native historical state contains candidate exposure')
    for stage in ('candidate_normalization','locator_chunk_preparation','locator_audit','missing_access_audit','structure_audit','scoring','web_report'):
        require(state['stages'][stage]['status']=='not_started',f'Native historical candidate-era stage is active: {stage}')
    require(state['source']['sha256']==release['source_sha256'],'Native historical source differs')
    require(state['evaluation_id']==release['evaluation_id'],'Native historical evaluation identity differs')
    registrations = [('benchmark_synthesis',file_digest(draft_path)),('benchmark_review',file_digest(review_path)),('benchmark_freeze',lock['release']['benchmark_file_sha256'])]
    if not current:
        registrations.append(('benchmark_review',file_digest(inventory_path)))
    for stage,sha in registrations:
        require(state['stages'][stage]['status']=='completed' and legacy_registered_hash(state,stage,sha),f'Native historical registration mismatch: {stage}')
    if current:
        from state_cli import validate_state
        state_errors, _ = validate_state(state, check_files=False, profile="v8")
        require(not state_errors, f'Current source freeze state is invalid: {state_errors}')
        require(not any(r.get('schema_version')=='source-benchmark-review-inventory-v1' for r in state['artifacts']), 'Current screening inventory must not be registered')
        for (stage, sha), schema in zip(registrations, ('source-subject-benchmark-draft-v1','source-benchmark-review-v1','source-subject-benchmark-v2')):
            require(any(r['stage']==stage and r['sha256']==sha and r.get('schema_version')==schema for r in state['artifacts']), f'Current typed freeze registration mismatch: {stage}')
        # Recompute standard screening diagnostics for validation only. This is
        # neither a preserved historical inventory nor a new editorial review.
        with tempfile.TemporaryDirectory(prefix='study-freeze-review-') as directory:
            inventory = Path(directory)/'inventory.json'
            final = Path(directory)/'final.json'
            inventory.write_bytes(json_bytes(build_inventory(draft_path, 0.93)))
            final.write_bytes(json_bytes(release))
            errors, _, _ = validate_final_data(draft_path, inventory, review_path, final)
    else:
        errors=native_v8_review_errors(draft_path,read(draft_path),release,read(inventory_path),read(review_path))
    require(not errors,f'Native historical review chain invalid: {errors}')
    # Checkpoint checksums are retained transport provenance, not resume/import gates.
if __name__ == "__main__":
    __import__("runtime_profile").require_public_cli()
