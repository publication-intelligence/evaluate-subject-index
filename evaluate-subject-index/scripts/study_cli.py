#!/usr/bin/env python3
"""Explicit retrospective benchmark migration and fail-closed study comparison."""
import argparse
import hashlib
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile

import study_comparison as study
from benchmark_review_cli import final_benchmark_structure_errors, legacy_review_errors, native_v8_review_errors
from schema_validation import schema_errors
from state_cli import artifact_id, evaluation_mutation_lock, now, save_state, validate_state


def payload(document):
    return (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode()


def record(root, path, content, stage, kind, schema=None):
    relative = path.relative_to(root).as_posix()
    sha = hashlib.sha256(content).hexdigest()
    return {'artifact_id': artifact_id(relative, sha), 'stage': stage, 'artifact_type': kind,
            'path': relative, 'sha256': sha, 'media_type': 'application/json',
            'schema_version': schema or json.loads(content).get('schema_version', 'study-evidence-v1'),
            'visibility': 'private', 'retention': 'required', 'frozen': True, 'recorded_at': now()}


def validate_release_review(release, descriptor, release_path, review_path, inventory_path, draft_path=None):
    review, inventory = study.read(review_path), study.read(inventory_path)
    study.require(study.file_digest(review_path) == descriptor['artifacts']['review_ledger']['file_sha256'], 'Historical review bytes mismatch')
    study.require(study.file_digest(inventory_path) == descriptor['artifacts']['review_inventory']['file_sha256'], 'Historical review inventory bytes mismatch')
    if draft_path is not None:
        errors = native_v8_review_errors(draft_path, study.read(draft_path), release, inventory, review)
    else:
        study.require('proposed_final' in review, 'Native review requires its preserved --release-draft')
        errors = legacy_review_errors(release, study.file_digest(release_path), inventory, review)
    study.require(not errors, f'Historical reviewed release is invalid: {errors}')


def migrate(args):
    state_path = Path(args.state).resolve()
    with evaluation_mutation_lock(state_path):
        state = study.read(state_path)
        errors, _ = validate_state(state, state_path=state_path)
        study.require(not errors, f'Invalid canonical state: {errors}')
        study.require(state.get('candidate') is not None, 'Retrospective migration requires an existing candidate; use the candidate-blind workflow for new evaluations')
        policy, _ = study.registered_document(state, state_path, 'define_policy', 'subject-index-evaluation-policy-v4')
        previous, _ = study.registered_document(state, state_path, 'benchmark_freeze', 'source-subject-benchmark-v2')
        study.require(previous['benchmark_sha256'] == study.digest({k:v for k,v in previous.items() if k != 'benchmark_sha256'}), 'Previous benchmark self-hash mismatch')
        lock_path = Path(args.study_lock).resolve()
        lock = study.read(lock_path)
        release_path = Path(args.release_benchmark)
        descriptor_path = Path(args.release_descriptor) if args.release_descriptor else None
        release = study.read(release_path)
        descriptor = study.read(descriptor_path) if descriptor_path else None
        study.validate_release(lock, release, study.file_digest(release_path), descriptor, study.file_digest(descriptor_path) if descriptor_path else None)
        page_map,_ = study.registered_document(state,state_path,'page_mapping','page-map-v1')
        manifest,_ = study.registered_document(state,state_path,'chunk_definition','chunk-manifest-v1')
        study.validate_density_evidence(lock, lock_path.parent, page_map, manifest)
        approval_path = Path(args.approval)
        approval = study.read(approval_path)
        study.require(not schema_errors(approval, 'retrospective-benchmark-approval.schema.json'), 'Invalid retrospective migration approval')
        study.require(approval['previous_state_sha256'] == study.file_digest(state_path), 'Approval does not bind the current state bytes')
        study.require(approval['previous_benchmark_sha256'] == previous['benchmark_sha256'], 'Approval does not bind the prior benchmark')
        study.require(approval['study_lock_sha256'] == lock['lock_sha256'] and approval['target_benchmark_sha256'] == release['benchmark_sha256'], 'Approval does not bind the target study release')
        review_path, inventory_path = Path(args.release_review), Path(args.release_review_inventory)
        draft_path = Path(args.release_draft) if args.release_draft else None
        release_state_path = Path(args.release_state) if args.release_state else None
        if lock['release']['lineage']['kind']=='native_source_freeze':
            study.validate_native_lineage(lock,release,release_state_path,draft_path,review_path,inventory_path)
        else:
            validate_release_review(release, descriptor, release_path, review_path, inventory_path, draft_path)
        study.require(release.get('candidate_blindness') == 'preserved', 'Selected historical release does not preserve candidate blindness')
        study.require(policy['policy_sha256'] == study.digest({k: v for k, v in policy.items() if k != 'policy_sha256'}), 'Current policy self-hash mismatch')
        study.require(approval['previous_policy_sha256'] == policy['policy_sha256'], 'Approval does not bind the previous policy')
        study.require(approval['target_policy_semantic_sha256'] == lock['policy_semantic_sha256'], 'Approval does not bind the target policy settings')
        from dimension_score_v8_cli import validate_v8_policy
        validate_v8_policy(policy)
        prior_policy = deepcopy(policy)
        template_path = Path(args.study_policy) if args.study_policy else None
        template = study.read(template_path) if template_path else None
        if template is not None:
            study.require(template.get('schema_version') == 'subject-index-study-policy-template-v1', 'Expected an unfrozen study policy template')
            study.require(study.file_digest(template_path) == approval.get('study_policy_template_sha256'), 'Approval does not bind the study policy template bytes')
            study.require(study.policy_semantic_hash(template) == lock['policy_semantic_sha256'], 'Study policy template differs from study lock')
            policy = deepcopy(template['policy_semantic_content'])
        policy_changed = study.policy_semantic_hash(prior_policy) != study.policy_semantic_hash(policy)
        if not policy_changed:
            policy = deepcopy(prior_policy)
        study.require(study.policy_semantic_hash(policy) == lock['policy_semantic_sha256'], 'Study semantic policy mismatch; supply explicitly approved --study-policy')
        same_content = study.benchmark_semantic_hash(previous) == lock['benchmark_semantic_sha256']
        root = state_path.parent
        output = (root / args.output_dir).resolve()
        study.require(output.is_relative_to(root) and output != root and not output.exists(), 'Migration directory must be new and inside the evaluation')
        backup = root / ('evaluation-state.before-' + study.file_digest(approval_path)[:12] + '.json')
        study.require(not backup.exists(), 'Preserved pre-migration state already exists')
        stamp = now()
        approved_at = datetime.fromisoformat(approval["approved_at"].replace("Z", "+00:00"))
        study.require(approved_at.utcoffset() is not None and approved_at <= datetime.fromisoformat(stamp.replace("Z", "+00:00")), "Approval timestamp must be timezone-aware and not in the future")
        if policy_changed:
            old_migration = prior_policy.get('retrospective_study_migration') or prior_policy.get('retrospective_migration')
            original_freeze = (old_migration.get('original_freeze') or old_migration.get('original_policy', {}).get('freeze')) if old_migration else prior_policy['freeze']
            policy['policy_id'] = prior_policy['policy_id'] + '.study-' + study.file_digest(approval_path)[:12]
            policy['freeze'] = {'frozen_at': stamp, 'candidate_seen': True}
            policy['retrospective_study_migration'] = {
                'candidate_seen': True, 'migrated_at': stamp, 'approval_id': approval['approval_id'],
                'approval_sha256': study.file_digest(approval_path), 'authorization': {'authorized_by': approval['authorized_by'], 'reference': approval['authorization_reference']},
                'study_lock_sha256': lock['lock_sha256'], 'target_policy_semantic_sha256': lock['policy_semantic_sha256'],
                'previous_policy': {'policy_id':prior_policy['policy_id'], 'policy_sha256':prior_policy['policy_sha256'], 'freeze':deepcopy(prior_policy['freeze']),
                    'artifact': {'path': (output/'previous-policy.json').relative_to(root).as_posix(), 'sha256': hashlib.sha256(payload(prior_policy)).hexdigest()}},
                'original_freeze': deepcopy(original_freeze), 'audit_transfer_authorized': False}
            policy['policy_sha256'] = study.digest({k:v for k,v in policy.items() if k != 'policy_sha256'})
            validate_v8_policy(policy)
        selected = deepcopy(previous) if same_content else study.normalized_benchmark(release)
        if not same_content or policy_changed:
            selected.update(evaluation_id=state['evaluation_id'], policy_sha256=policy['policy_sha256'])
            # The freeze remains the historical release's freeze. The new wrapper is openly retrospective.
            selected['retrospective_benchmark_migration'] = {'candidate_seen': True, 'migrated_at': stamp,
                'approval_id': approval['approval_id'], 'release_benchmark_sha256': release['benchmark_sha256'],
                'original_freeze': deepcopy(release['freeze']), 'fresh_review_performed': False, 'audit_transfer_authorized': False}
            selected['benchmark_sha256'] = study.digest({k: v for k, v in selected.items() if k != 'benchmark_sha256'})
        study.require(not final_benchmark_structure_errors(selected), 'Selected benchmark wrapper is invalid')
        updated = deepcopy(state)
        if policy_changed:
            updated['configuration']['intended_readership'] = policy['audience']['label']
            updated['configuration']['readership_provenance'] = {k: policy['audience'][k] for k in ('basis','confidence','rationale')}
        invalidated = ['scoring', 'web_report'] if same_content and not policy_changed else ['locator_chunk_preparation', 'locator_audit', 'missing_access_audit', 'structure_audit', 'scoring', 'web_report']
        if same_content and not policy_changed and any(r['stage']=='structure_audit' and r.get('schema_version')=='structure-audit-v6' for r in state['artifacts']):
            structure, _ = study.registered_document(state, state_path, 'structure_audit', 'structure-audit-v6')
            observed = [(r['chunk_id'],r['indexable_source_words']) for r in structure['density']['chapter_measurements']]
            expected = [(r['chunk_id'],r['indexable_source_words']) for r in lock['density_basis']['chunks']]
            if observed != expected:
                invalidated.insert(0, 'structure_audit')
        benchmark_stages = ['source_subject_discovery', 'benchmark_synthesis', 'benchmark_review', 'benchmark_freeze']
        removed = set(invalidated + ([] if same_content and not policy_changed else benchmark_stages) + (['define_policy'] if policy_changed else []))
        updated['artifacts'] = [r for r in updated['artifacts'] if r['stage'] not in removed
            and not (r['stage'] == 'initialize' and r.get('sha256') != state['source']['sha256'])]
        # Keep historical proof in portable checkpoints without selecting it as
        # current policy/benchmark or retaining invalidated candidate ledgers.
        active_paths = {r['path'] for r in updated['artifacts']}
        history_kinds = {'study_preserved_history','study_comparison_evidence','historical_release_benchmark','historical_release_review','evaluation_policy','source_benchmark'}
        for old in state['artifacts']:
            if old['path'] not in active_paths and old.get('artifact_type') in history_kinds:
                archived = deepcopy(old)
                archived.update(stage='initialize', artifact_type='study_preserved_history', visibility='private', retention='required')
                updated['artifacts'].append(archived)
        updated['artifacts'].append(record(root, backup, state_path.read_bytes(), 'initialize', 'study_preserved_history'))
        for stage in invalidated:
            updated['stages'][stage] = {'status': 'not_started', 'updated_at': stamp,
                'notes': ['Retrospective study binding invalidated downstream registration; prior files remain preserved. Audit reuse requires its own evidence validation/authorization.']}
        writes = {output/'study-benchmark-lock.v1.json': lock_path.read_bytes(),
                  output/'release-benchmark.json': release_path.read_bytes(),
                  output/'approval.json': approval_path.read_bytes(), output/'release-review.json': review_path.read_bytes(),
                  output/'release-review-inventory.json': inventory_path.read_bytes()}
        if descriptor_path is not None:
            writes[output/'release-descriptor.json'] = descriptor_path.read_bytes()
        if release_state_path is not None:
            writes[output/'release-state.json'] = release_state_path.read_bytes()
        if draft_path is not None:
            writes[output/'release-draft.json'] = draft_path.read_bytes()
        for row in lock['density_basis']['chunks']:
            target = (output / row['source_artifact']['path']).resolve()
            content = (lock_path.parent / row['source_artifact']['path']).read_bytes()
            study.require(target.is_relative_to(output) and (target not in writes or writes[target] == content), 'Density evidence path collision')
            writes[target] = content
        if policy_changed:
            previous_policy_record = next(r for r in state['artifacts'] if r['stage']=='define_policy' and r.get('schema_version')=='subject-index-evaluation-policy-v4')
            writes[output/'previous-policy.json'] = (root / previous_policy_record['path']).read_bytes()
            policy['retrospective_study_migration']['previous_policy']['artifact']['sha256'] = hashlib.sha256(writes[output/'previous-policy.json']).hexdigest()
            policy['policy_sha256'] = study.digest({k:v for k,v in policy.items() if k != 'policy_sha256'})
            selected['policy_sha256'] = policy['policy_sha256']
            selected['benchmark_sha256'] = study.digest({k:v for k,v in selected.items() if k != 'benchmark_sha256'})
            writes[output/'study-policy-template.json'] = template_path.read_bytes()
            writes[output/'selected-policy.json'] = payload(policy)
        if not same_content or policy_changed:
            writes[output/'selected-benchmark.json'] = payload(selected)
            for stage in benchmark_stages:
                updated['stages'][stage] = {'status': 'completed', 'updated_at': stamp,
                    'notes': ['Selected preserved reviewed release retrospectively with candidate visible; no discovery, synthesis, review or historical freeze rerun.']}
            updated['candidate']['benchmark_path'] = (output/'selected-benchmark.json').relative_to(root).as_posix()
            updated['candidate']['benchmark_sha256'] = selected['benchmark_sha256']
        binding = {'candidate_seen': True, 'migrated_at': stamp, 'semantic_change': not same_content, 'policy_semantic_change': policy_changed,
                   'audit_transfer_authorized': False, 'historical_freeze': deepcopy(release['freeze']),
                   'prior_state': {'path': backup.name, 'sha256': study.file_digest(state_path)}}
        names = {'lock':'study-benchmark-lock.v1.json', 'release_benchmark':'release-benchmark.json', 'approval':'approval.json', 'release_review':'release-review.json', 'release_review_inventory':'release-review-inventory.json'}
        for name in ('release-descriptor','release-draft','release-state'):
            if output/(name+'.json') in writes:
                names[name.replace('-','_')] = name+'.json'
        for name, filename in names.items():
            path = output/filename
            binding[name] = {'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(writes[path]).hexdigest()}
        updated['study_comparison'] = binding
        for path, content in writes.items():
            stage = 'benchmark_freeze'
            kind = 'study_comparison_evidence'
            if path.name == 'selected-policy.json': stage, kind = 'define_policy', 'evaluation_policy'
            elif path.name == 'selected-benchmark.json': kind = 'source_benchmark'
            elif path.name == 'release-benchmark.json':
                # Historical evidence must never be selected as the current wrapper.
                stage, kind = 'benchmark_synthesis', 'historical_release_benchmark'
            elif path.name == 'release-review.json': stage, kind = 'benchmark_review', 'historical_release_review'
            elif path.name == 'release-review-inventory.json': stage = 'source_subject_discovery'
            updated['artifacts'].append(record(root,path,content,stage,kind))
        updated['updated_at'] = stamp
        updated['artifacts'].sort(key=lambda r:r['path'])
        errors, _ = validate_state(updated, state_path=state_path, check_files=False)
        study.require(not errors, f'Migration would leave invalid state: {errors}')
        # Validate all bindings against staged bytes before committing any canonical mutation.
        staged = Path(tempfile.mkdtemp(prefix='.study-migration-', dir=root))
        committed = False
        try:
            for path, content in writes.items():
                target = staged / path.relative_to(output)
                target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(content)
            output.parent.mkdir(parents=True, exist_ok=True)
            staged.rename(output)
            backup.write_bytes(state_path.read_bytes())
            study.preflight_state(updated, state_path)
            save_state(state_path, updated)
            committed = True
        finally:
            if not committed:
                shutil.rmtree(staged, ignore_errors=True)
                shutil.rmtree(output, ignore_errors=True)
                backup.unlink(missing_ok=True)
        return {'ok': True, 'command':'migrate-benchmark', 'semantic_change': not same_content, 'policy_semantic_change': policy_changed,
                'candidate_seen': True, 'audit_transfer_authorized': False, 'invalidated_stages': invalidated,
                'preserved_state': str(backup), 'benchmark_sha256': selected['benchmark_sha256'], 'study_lock_sha256':lock['lock_sha256']}


def assemble(args):
    import web_projection
    paths = [Path(p).resolve() for p in args.state]
    identities, bundles = [], []
    for path in paths:
        state = study.read(path)
        identity = study.preflight_state(state,path,require_density=True)
        study.require(identity is not None, 'Comparison requires a bound study lock')
        projection, _ = study.registered_document(state,path,'web_report',web_projection.PROJECTION_SCHEMA_VERSION)
        study.require(projection.get('comparison_identity') == identity, 'Public bundle comparison identity is stale or absent')
        projection_record = next(r for r in state['artifacts'] if r.get('schema_version') == web_projection.PROJECTION_SCHEMA_VERSION)
        base = (path.parent / projection_record['path']).parent
        collections = {}
        for r in projection['collections']:
            study.require(r['artifact_path'] == web_projection.COLLECTION_PATHS.get(r['collection_id']), 'Unexpected public collection path')
            path = base/r['artifact_path']
            study.require(study.file_digest(path) == r['file_sha256'], 'Public collection bytes changed')
            collections[r['collection_id']] = study.read(path)
        web_projection.validate_bundle(projection,collections)
        identities.append(identity);bundles.append((projection,collections))
    study.require(len({p['evaluation_id'] for p,_ in bundles}) == len(bundles), 'Duplicate evaluation in study comparison')
    common = study.compare_identities(identities)
    output = Path(args.output_dir).resolve()
    study.require(not output.exists(), 'Comparison output directory already exists')
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.study-comparison-',dir=output.parent))
    try:
        members=[]
        for i,(projection,collections) in enumerate(bundles):
            directory=temporary/str(i+1);directory.mkdir()
            (directory/'projection.v1.json').write_bytes(payload(projection))
            for name,value in collections.items():
                target=directory/web_projection.COLLECTION_PATHS[name];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(web_projection.json_bytes(value))
            members.append({'evaluation_id':projection['evaluation_id'],'projection_path':f'{i+1}/projection.v1.json','projection_sha256':projection['projection_sha256']})
        manifest={'schema_version':'subject-index-study-comparison-v1','comparison_identity':common,'members':members}
        (temporary/'comparison.json').write_bytes(payload(manifest));temporary.rename(output)
    finally:
        shutil.rmtree(temporary,ignore_errors=True)
    return {'ok':True,'command':'assemble-comparison','evaluations':len(bundles),'output':str(output)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    policy_template=sub.add_parser('policy-template');policy_template.add_argument('--input',required=True);policy_template.add_argument('--output',required=True)
    fingerprint=sub.add_parser('fingerprint');fingerprint.add_argument('--benchmark',required=True);fingerprint.add_argument('--policy',required=True)
    check=sub.add_parser('preflight');check.add_argument('--state',action='append',required=True);check.add_argument('--require-density',action='store_true')
    migration=sub.add_parser('migrate-benchmark')
    for flag in ('state','study-lock','release-benchmark','release-review','release-review-inventory','approval','output-dir'):migration.add_argument('--'+flag,required=True)
    migration.add_argument('--release-descriptor', help='Required for a Git-bound reviewed release')
    migration.add_argument('--release-state', help='Required preserved source-only state for native release lineage')
    migration.add_argument('--release-draft', help='Required preserved draft for native V8 reviewed releases')
    migration.add_argument('--study-policy', help='Explicitly approved shared unfrozen policy template')
    assembly=sub.add_parser('assemble-comparison');assembly.add_argument('--state',action='append',required=True);assembly.add_argument('--output-dir',required=True)
    args=parser.parse_args()
    try:
        if args.command=='policy-template':
            import policy_cli
            source=study.read(args.input)
            study.require('retrospective_migration' not in source, 'A study policy template is unfrozen, not a migrated evaluation')
            policy=policy_cli.build_policy(source)
            template={'schema_version':'subject-index-study-policy-template-v1','policy_semantic_content':{k:v for k,v in policy.items() if k not in study.POLICY_WRAPPERS}}
            template['template_sha256']=study.digest(template)
            output=Path(args.output);study.require(not output.exists(),'Policy template output exists');output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(payload(template))
            result={'ok':True,'policy_semantic_sha256':study.policy_semantic_hash(template),'output':str(output),'freeze_created':False}
        elif args.command=='fingerprint':result={'ok':True,'benchmark_semantic_sha256':study.benchmark_semantic_hash(study.read(args.benchmark)),'policy_semantic_sha256':study.policy_semantic_hash(study.read(args.policy))}
        elif args.command=='migrate-benchmark':result=migrate(args)
        elif args.command=='assemble-comparison':result=assemble(args)
        else:
            identities=[]
            for name in args.state:
                path=Path(name).resolve();identity=study.preflight_state(study.read(path),path,require_density=args.require_density or len(args.state)>1)
                study.require(identity is not None,'Study lock is not bound');identities.append(identity)
            if len(identities)>1:study.compare_identities(identities)
            result={'ok':True,'command':'preflight','evaluations':len(identities)}
        print(json.dumps(result,indent=2))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'ok':False,'error':{'code':'study_comparison_failed','message':str(exc)}},indent=2));raise SystemExit(1)


if __name__=='__main__':main()
