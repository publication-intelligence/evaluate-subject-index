"""Study locking, retrospective visibility, and comparison fail at real boundaries."""
import argparse
import hashlib
from copy import deepcopy
import json
import shutil
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_v8_completion as completion
import study_cli
import study_comparison as study
import web_projection
from schema_validation import schema_errors


def self_hash(document, field):
    document[field] = study.digest({k:v for k,v in document.items() if k != field})
    return document


class StudyFixture:
    def __init__(self, case, *, different=False, policy_change=False, evaluation_id=None):
        self.case=case;self.f=completion.CurrentV8CompletionTests();self.f.setUp()
        self.root=self.f.root;self.state_path=self.f.state_path
        if evaluation_id:
            for p in self.root.rglob("*.json"):
                p.write_text(p.read_text().replace(completion.EVALUATION_ID,evaluation_id))
        # Replace the completion fixture's placeholder map with actual frozen scope.
        page_map={'schema_version':'page-map-v1','source_sha256':completion.SOURCE_SHA,'document_page_count':1,'document_page_basis':'one_based_inclusive',
            'pages':[{'document_page':1,'source_page_label':'1','normalized_locator_key':'1','label_style':'arabic','mapping_id':'MAP-1','in_evaluation_scope':True,'accepts_index_locators':True}],
            'validation':{'all_document_pages_covered':True,'unique_indexable_locator_keys':True}}
        self_hash(page_map,'page_map_sha256');self.f.write('page-map.json',page_map)
        def rebind(old,new):
            for p in self.root.rglob('*.json'):
                p.write_text(p.read_text().replace(old,new))
        rebind(completion.PAGE_MAP_SHA,page_map['page_map_sha256'])
        for name,field in (('chunk-manifest.json','chunk_manifest_sha256'),('evaluation-policy.json','policy_sha256')):
            document=study.read(self.root/name);old=document[field];self_hash(document,field)
            self.f.write(name,document);rebind(old,document[field])
        # Bind real benchmark bytes as well.
        benchmark=study.read(self.root/'source-benchmark.json');self_hash(benchmark,'benchmark_sha256')
        self.f.write('source-benchmark.json',benchmark)
        state=study.read(self.state_path);state['candidate']['benchmark_sha256']=benchmark['benchmark_sha256'];state['candidate']['normalized_sha256']=study.file_digest(self.root/state['candidate']['normalized_path'])
        missing=study.read(self.root/'candidate/missing-access-audit.CHUNK-001.v1.json');missing['benchmark_sha256']=benchmark['benchmark_sha256']
        self.f.write('candidate/missing-access-audit.CHUNK-001.v1.json',missing)
        for r in state['artifacts']:
            p=self.root/r['path'];r['sha256']=study.file_digest(p);r['artifact_id']=completion.state_cli.artifact_id(r['path'],r['sha256'])
        self.f.write('evaluation-state.json',state)
        registered=self.f.run_cli('register-structure','--state',str(self.state_path),'--input',str(self.f.structure_path));case.assertEqual(0,registered.returncode,registered.stdout)
        self.policy=study.read(self.root/'evaluation-policy.json')
        self.release=deepcopy(benchmark);self.release.update(benchmark_id='REVIEWED-RELEASE',evaluation_id='HISTORICAL-SOURCE-ONLY',version=4)
        if different:self.release['subjects'][0]['meaning']='A different source-defined retrieval need.'
        self_hash(self.release,'benchmark_sha256');self.f.write('release/benchmark.json',self.release)
        queues={'subject_ids':['SUBJ-001'],'relationship_ids':[],'reader_task_ids':['TASK-001'],'cross_chapter_subject_ids':[],'unresolved_relationship_ids':[],'fallback_reader_task_ids':[]}
        draft={'version':3,'file_sha256':'a'*64,'canonical_sha256':'b'*64}
        inv={'schema_version':'source-benchmark-review-inventory-v1','evaluation_id':self.release['evaluation_id'],'draft':draft,'queues':queues}
        coverage=dict(zip(('subject_ids_reviewed','relationship_ids_reviewed','reader_task_ids_reviewed','cross_chapter_subject_ids_reviewed','unresolved_relationship_ids_dispositioned','fallback_reader_task_ids_reviewed'),queues.values()))
        review={'schema_version':'source-benchmark-review-v1','evaluation_id':self.release['evaluation_id'],'review_mode':'full','candidate_blindness':'preserved',
            'reviewer_independence':{'fresh_context':True,'candidate_unseen':True,'source_reconnected_sha256':self.release['source_sha256']},
            'draft':draft,'coverage':coverage,'recommendation':'approve_revised','completion':{key:True for key in ('structural_validation_passed','editorial_review_complete','source_first_omission_review_complete','candidate_blindness_preserved','no_unreviewed_required_items','public_claims_allowed')},
            'proposed_final':{'version':4,'file_sha256':study.file_digest(self.root/'release/benchmark.json'),'canonical_sha256':self.release['benchmark_sha256']}}
        self.f.write('release/review.json',review);self.f.write('release/inventory.json',inv)
        descriptor={'schema_version':'subject-index-benchmark-release-v1','release_id':'SELECTABLE-REVIEWED-V4','artifact_freeze':{'commit':'c'*40},
            'artifacts':{'benchmark':{'file_sha256':study.file_digest(self.root/'release/benchmark.json'),'canonical_sha256':self.release['benchmark_sha256']},
                'review_ledger':{'file_sha256':study.file_digest(self.root/'release/review.json')},'review_inventory':{'file_sha256':study.file_digest(self.root/'release/inventory.json')}}}
        self_hash(descriptor,'release_sha256');self.f.write('release/descriptor.json',descriptor)
        self.f.write('release/source/chunk.json',{'schema_version':'source-subject-chunk-v1','chunk':{'chunk_id':'CHUNK-001','owned_document_pages':[1]},'page_review':{'indexable_source_words':100,'complete':True,'expected_owned_pages':1,'reviewed_owned_pages':1}})
        chunks=[{'chunk_id':'CHUNK-001','indexable_source_words':100,'source_artifact':{'path':'source/chunk.json','sha256':study.file_digest(self.root/'release/source/chunk.json')}}]
        target=deepcopy(self.policy)
        if policy_change:target['audience']['label']='One shared scholarly audience'
        self.lock={'schema_version':'ohfr-study-benchmark-lock-v1','study_id':'STUDY-SYNTHETIC',
            'release':{'release_id':descriptor['release_id'],'lineage':{'kind':'git_freeze','artifact_freeze_commit':'c'*40},'benchmark_id':self.release['benchmark_id'],'version':4,'benchmark_sha256':self.release['benchmark_sha256'],'benchmark_file_sha256':study.file_digest(self.root/'release/benchmark.json'),'release_descriptor_sha256':study.file_digest(self.root/'release/descriptor.json')},
            'benchmark_semantic_sha256':study.benchmark_semantic_hash(self.release),
            'source_scope':{k:self.policy['source_scope'][k] for k in ('source_sha256','document_page_span','page_map_sha256','chunk_manifest_sha256')},
            'policy_profile':self.policy['policy_profile']['id'],'policy_semantic_sha256':study.policy_semantic_hash(target),'audit_mode':'full',
            'rubric_version':completion.dimensions.RUBRIC_VERSION,'calculation_profile':completion.dimensions.CALCULATION_PROFILE,
            'density_basis':{'basis_id':'frozen-source-discovery','chunks':chunks,'measurement_sha256':study.digest(chunks)}}
        self_hash(self.lock,'lock_sha256');self.f.write('release/study-benchmark-lock.v1.json',self.lock)
        approval={'schema_version':'subject-index-retrospective-benchmark-approval-v1','approval_id':'TEST-EXPLICIT-AUTHORIZATION','authorized_by':'Synthetic test user','authorization_reference':'Synthetic test instruction',
            'approved_at':'2026-09-16T00:00:00Z','candidate_seen':True,'previous_state_sha256':study.file_digest(self.state_path),'previous_benchmark_sha256':benchmark['benchmark_sha256'],
            'previous_policy_sha256':self.policy['policy_sha256'],'target_policy_semantic_sha256':self.lock['policy_semantic_sha256'],
            'study_lock_sha256':self.lock['lock_sha256'],'target_benchmark_sha256':self.release['benchmark_sha256'],'audit_transfer_authorized':False}
        template_path=None
        if policy_change:
            template={'schema_version':'subject-index-study-policy-template-v1','policy_semantic_content':{k:v for k,v in target.items() if k not in study.POLICY_WRAPPERS}}
            self_hash(template,'template_sha256');template_path=self.f.write('release/policy-template.json',template)
            approval['study_policy_template_sha256']=study.file_digest(template_path)
        self.f.write('release/approval.json',approval)
        self.args=argparse.Namespace(state=str(self.state_path),study_lock=str(self.root/'release/study-benchmark-lock.v1.json'),release_benchmark=str(self.root/'release/benchmark.json'),release_descriptor=str(self.root/'release/descriptor.json'),release_review=str(self.root/'release/review.json'),release_review_inventory=str(self.root/'release/inventory.json'),approval=str(self.root/'release/approval.json'),output_dir='migration',study_policy=str(template_path) if template_path else None,release_draft=None,release_state=None)

    def current_source_release(self, *, revised=False):
        from test_benchmark_freeze import run_cli
        import benchmark_review_cli as review_cli
        root=self.root/'current-source-freeze';root.mkdir()
        state=study.read(self.state_path);state['candidate']=None
        state['evaluation_id']=self.release['evaluation_id']
        order=list(completion.state_cli.STAGES);first=order.index('benchmark_synthesis')
        source_stages=set(order[:first])
        state['artifacts']=[r for r in state['artifacts'] if r['stage'] in source_stages]
        for row in state['artifacts']:
            target=root/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((self.root/row['path']).read_bytes())
        for stage in order[first:]:
            state['stages'][stage]={'status':'not_started','updated_at':None,'notes':[]}
        source_state=root/'evaluation-state.json';source_state.write_bytes(study_cli.payload(state))
        draft=deepcopy(self.release);draft.pop('freeze');draft.pop('benchmark_sha256')
        draft['schema_version']='source-subject-benchmark-draft-v1'
        draft['synthesis']={'whole_source_pass_complete':True,'all_chunk_artifacts_reconciled':True,'candidate_unseen':True}
        draft_path=root/'draft.json';draft_path.write_bytes(study_cli.payload(draft))
        run_cli('state_cli.py','set-stage','--state',source_state,'--stage','benchmark_synthesis','--status','completed','--artifact-path',draft_path)
        inventory_path=root/'temporary-screen.json'
        run_cli('benchmark_review_cli.py','screen','--draft',draft_path,'--output',inventory_path)
        inventory=study.read(inventory_path)
        final=deepcopy(self.release)
        if revised:
            final['subjects'][0]['meaning']='A source-reviewed successor meaning.'
            final['version']+=1
        self_hash(final,'benchmark_sha256')
        final_path=root/'final.json';final_path.write_bytes(study_cli.payload(final))
        review=study.read(self.args.release_review);review.pop('proposed_final')
        review['draft']=inventory['draft'];review['approved_changes']=review_cli.approved_changes(draft,final)
        review['remaining_issues']=[];review['recommendation']='approve_revised' if revised else 'retain_draft'
        review_path=root/'review.json';review_path.write_bytes(study_cli.payload(review))
        run_cli('benchmark_review_cli.py','freeze','--state',source_state,'--draft',draft_path,'--inventory',inventory_path,'--review',review_path,'--final',final_path)
        frozen=study.read(source_state)
        self.case.assertFalse(any(r.get('schema_version')=='source-benchmark-review-inventory-v1' for r in frozen['artifacts']))
        # A successful current freeze does not depend on retaining its temporary screen.
        inventory_path.unlink()
        self.release=final
        self.lock['release']={'release_id':'CURRENT-REVIEWED-SUCCESSOR','benchmark_id':final['benchmark_id'],'version':final['version'],
            'benchmark_sha256':final['benchmark_sha256'],'benchmark_file_sha256':study.file_digest(final_path),
            'lineage':{'kind':'current_source_freeze','source_only_state_sha256':study.file_digest(source_state),
                'draft_file_sha256':study.file_digest(draft_path),'review_file_sha256':study.file_digest(review_path),'checkpoint_artifacts':[]}}
        self.lock['benchmark_semantic_sha256']=study.benchmark_semantic_hash(final)
        self_hash(self.lock,'lock_sha256');Path(self.args.study_lock).write_bytes(study_cli.payload(self.lock))
        approval=study.read(self.args.approval);approval.update(study_lock_sha256=self.lock['lock_sha256'],target_benchmark_sha256=final['benchmark_sha256'])
        Path(self.args.approval).write_bytes(study_cli.payload(approval))
        self.args.release_state=str(source_state);self.args.release_draft=str(draft_path)
        self.args.release_review=str(review_path);self.args.release_benchmark=str(final_path)
        self.args.release_descriptor=None;self.args.release_review_inventory=None
        return source_state

    def close(self):self.f.tearDown()


class StudyComparisonTests(unittest.TestCase):
    def fixture(self, **kw):
        f=StudyFixture(self,**kw);self.addCleanup(f.close);return f

    def test_wrapper_rebinding_keeps_audits_and_reports_benchmark_beside_methodology(self):
        f=self.fixture();before=study.read(f.state_path);old_policy=(f.root/'evaluation-policy.json').read_bytes()
        result=study_cli.migrate(f.args);self.assertFalse(result['semantic_change']);self.assertFalse(result['audit_transfer_authorized'])
        after=study.read(f.state_path)
        self.assertEqual(before['candidate'],after['candidate'])
        self.assertEqual(old_policy,(f.root/'evaluation-policy.json').read_bytes())
        self.assertEqual(before,study.read(Path(result['preserved_state'])))
        self.assertEqual('completed',after['stages']['missing_access_audit']['status'])
        for command in ('score','build-report'):
            r=f.f.run_cli(command,'--state',str(f.state_path));self.assertEqual(0,r.returncode,r.stdout+r.stderr)
        state=study.read(f.state_path);identity=study.preflight_state(state,f.state_path,require_density=True)
        report,_=study.registered_document(state,f.state_path,'web_report','subject-index-web-report-v10')
        self.assertEqual(identity['benchmark_semantic_sha256'],report['methodology']['benchmark']['benchmark_semantic_sha256'])
        self.assertEqual(4,report['methodology']['benchmark']['release']['version'])

    def test_semantic_replacement_preserves_freezes_and_invalidates_audits_without_transfer(self):
        f=self.fixture(different=True);before=f.state_path.read_bytes();policy=(f.root/'evaluation-policy.json').read_bytes()
        result=study_cli.migrate(f.args);state=study.read(f.state_path)
        self.assertTrue(result['semantic_change']);self.assertEqual(before,Path(result['preserved_state']).read_bytes())
        self.assertEqual(policy,(f.root/'evaluation-policy.json').read_bytes())
        selected,_=study.registered_document(state,f.state_path,'benchmark_freeze','source-subject-benchmark-v2')
        self.assertEqual(f.release['freeze'],selected['freeze'])
        self.assertTrue(selected['retrospective_benchmark_migration']['candidate_seen'])
        self.assertFalse(selected['retrospective_benchmark_migration']['fresh_review_performed'])
        self.assertTrue(all(state['stages'][s]['status']=='not_started' for s in result['invalidated_stages']))
        self.assertFalse(any(r['stage'] in result['invalidated_stages'] for r in state['artifacts']))
        self.assertTrue((f.root/'candidate/locator-audit.CHUNK-001.v2.json').is_file())
        r=f.f.run_cli('score','--state',str(f.state_path));self.assertNotEqual(0,r.returncode)

    def test_explicit_shared_policy_migration_preserves_historical_bytes_and_visibility(self):
        f=self.fixture(policy_change=True);before=(f.root/'evaluation-policy.json').read_bytes()
        result=study_cli.migrate(f.args);state=study.read(f.state_path)
        policy,_=study.registered_document(state,f.state_path,'define_policy','subject-index-evaluation-policy-v4')
        self.assertTrue(result['policy_semantic_change']);self.assertTrue(policy['freeze']['candidate_seen'])
        self.assertEqual([],schema_errors(policy,'evaluation-policy-v4.schema.json'))
        self.assertEqual(f.policy['freeze'],policy['retrospective_study_migration']['original_freeze'])
        self.assertEqual(before,(f.root/'migration/previous-policy.json').read_bytes())
        self.assertEqual(f.lock['policy_semantic_sha256'],study.policy_semantic_hash(policy))
        self.assertEqual('not_started',state['stages']['locator_audit']['status'])
        tampered=deepcopy(policy);tampered['freeze']['candidate_seen']=False
        self.assertTrue(schema_errors(tampered,'evaluation-policy-v4.schema.json'))
        tampered=deepcopy(policy);tampered['audience']['label']='Changed later'
        self.assertTrue(schema_errors(tampered,'evaluation-policy-v4.schema.json'))

    def test_known_638_vs_1366_families_fail_and_counts_alone_cannot_establish_equivalence(self):
        f=self.fixture();study_cli.migrate(f.args)
        identity=study.preflight_state(study.read(f.state_path),f.state_path,require_density=True)
        def family(count,treatments):
            b=deepcopy(f.release);b['subjects']=[]
            for i in range(count):
                row=deepcopy(f.release['subjects'][0]);row['subject_id']=f'SUBJ-{count}-{i}'
                row['evidence']=[{'evidence_id':f'EVID-{count}-{n}','document_page':n+1,'locator_class':'principal'} for n in range(i,treatments,count)]
                b['subjects'].append(row)
            return b
        a=deepcopy(identity);b=deepcopy(identity)
        a['benchmark_semantic_sha256']=study.benchmark_semantic_hash(family(638,1569));self_hash(a,'identity_sha256')
        b['benchmark_semantic_sha256']=study.benchmark_semantic_hash(family(1366,3210));self_hash(b,'identity_sha256')
        with self.assertRaisesRegex(ValueError,'benchmark_semantic_sha256'):study.compare_identities([a,b])
        altered=family(638,1569);altered['subjects'][0]['meaning']='Changed without changing counts'
        self.assertNotEqual(a['benchmark_semantic_sha256'],study.benchmark_semantic_hash(altered))
        wrapper=deepcopy(f.release);wrapper['benchmark_id']='Different evaluation wrapper';wrapper['freeze']['frozen_at']='2030-01-01';wrapper['compatibility_import']={'approved':'preserved elsewhere'}
        self.assertEqual(study.benchmark_semantic_hash(f.release),study.benchmark_semantic_hash(wrapper))

    def test_each_comparison_axis_and_unknown_lineage_fails_closed(self):
        f=self.fixture();study_cli.migrate(f.args);identity=study.preflight_state(study.read(f.state_path),f.state_path,require_density=True)
        self.assertEqual(identity,study.compare_identities([identity,deepcopy(identity)]))
        for key in ('source_scope','benchmark_semantic_sha256','release','policy_semantic_sha256','policy_profile','audit_mode','rubric_version','calculation_profile','density_basis','density_measurements_sha256'):
            other=deepcopy(identity);other[key]={'changed':True} if isinstance(other[key],dict) else 'different';self_hash(other,'identity_sha256')
            with self.subTest(key=key),self.assertRaises(ValueError):study.compare_identities([identity,other])
        other=deepcopy(identity);other['release']=None;self_hash(other,'identity_sha256')
        with self.assertRaises(ValueError):study.compare_identities([identity,other])

    def test_migration_rollback_and_tampered_approval_leave_prior_state_untouched(self):
        f=self.fixture(different=True);before=f.state_path.read_bytes()
        with patch.object(study_cli,'save_state',side_effect=OSError('Injected commit failure')):
            with self.assertRaises(OSError):study_cli.migrate(f.args)
        self.assertEqual(before,f.state_path.read_bytes());self.assertFalse((f.root/'migration').exists())
        self.assertEqual([],list(f.root.glob('evaluation-state.before-*.json')))
        approval=study.read(f.args.approval);approval['candidate_seen']=False;Path(f.args.approval).write_bytes(study_cli.payload(approval))
        with self.assertRaisesRegex(ValueError,'approval'):study_cli.migrate(f.args)
        self.assertEqual(before,f.state_path.read_bytes())

    def test_density_tampering_fails_before_score_and_same_total_different_map_fails(self):
        f=self.fixture();study_cli.migrate(f.args);state=study.read(f.state_path)
        structure,record=study.registered_document(state,f.state_path,'structure_audit','structure-audit-v6')
        structure['density']['chapter_measurements'][0]['indexable_source_words']+=1
        p=f.root/record['path'];p.write_bytes(study_cli.payload(structure));record['sha256']=study.file_digest(p)
        original=next(r for r in state['artifacts'] if r['path']==record['path']);original.update(record)
        f.f.write('evaluation-state.json',state)
        r=f.f.run_cli('score','--state',str(f.state_path));self.assertNotEqual(0,r.returncode);self.assertIn('density',r.stdout)
        lock=deepcopy(f.lock);lock['density_basis']['chunks']*=2;self_hash(lock,'lock_sha256')
        with self.assertRaises(ValueError):study.validate_lock(lock)

    def test_comparison_assembly_accepts_bound_pair_and_rejects_stale_or_mixed_bundle(self):
        a=self.fixture();b=self.fixture(evaluation_id='EVAL-SECOND')
        approval=study.read(b.args.approval)
        shutil.copytree(a.root/'release',b.root/'release',dirs_exist_ok=True)
        approval.update(study_lock_sha256=a.lock['lock_sha256'],target_benchmark_sha256=a.release['benchmark_sha256'])
        Path(b.args.approval).write_bytes(study_cli.payload(approval))
        for f in (a,b):
            study_cli.migrate(f.args)
            for command in ('score','build-report'):
                r=f.f.run_cli(command,'--state',str(f.state_path));self.assertEqual(0,r.returncode,r.stdout+r.stderr)
        output=a.root/'comparison'
        result=study_cli.assemble(argparse.Namespace(state=[str(a.state_path),str(b.state_path)],output_dir=str(output)))
        self.assertEqual(2,result['evaluations']);self.assertEqual(2,len(study.read(output/'comparison.json')['members']))
        for member in study.read(output/'comparison.json')['members']:
            projection_path=output/member['projection_path'];projection=study.read(projection_path)
            source=next(f for f in (a,b) if study.read(f.state_path)['evaluation_id']==member['evaluation_id'])
            _,report_record=study.registered_document(study.read(source.state_path),source.state_path,'web_report','subject-index-web-report-v10')
            report_path=output/member['web_report_path']
            self.assertRegex(member['web_report_path'],r'^[12]/web-report\.v10\.json$')
            self.assertEqual(report_record['sha256'],member['web_report_file_sha256'])
            self.assertEqual(report_record['sha256'],study.file_digest(report_path))
            self.assertEqual((source.root/report_record['path']).read_bytes(),report_path.read_bytes())
            for collection in projection['collections']:
                self.assertEqual(collection['file_sha256'],study.file_digest(projection_path.parent/collection['artifact_path']))
        state=study.read(b.state_path);benchmark,record=study.registered_document(state,b.state_path,'benchmark_freeze','source-subject-benchmark-v2')
        benchmark['subjects'][0]['meaning']='Different source need';self_hash(benchmark,'benchmark_sha256')
        path=b.root/record['path'];path.write_bytes(study_cli.payload(benchmark))
        next(r for r in state['artifacts'] if r['path']==record['path'])['sha256']=study.file_digest(path)
        b.f.write('evaluation-state.json',state)
        with self.assertRaisesRegex(ValueError,'Mixed semantic|artifact bytes changed'):
            study_cli.assemble(argparse.Namespace(state=[str(a.state_path),str(b.state_path)],output_dir=str(a.root/'must-not-exist')))
        self.assertFalse((a.root/'must-not-exist').exists())

    def test_resume_import_rejects_study_scope_mismatch_and_missing_binding_cannot_score(self):
        import bundle_cli
        f=self.fixture();study_cli.migrate(f.args);state=study.read(f.state_path)
        state['source']['document_page_span']=[1,2];f.f.write('evaluation-state.json',state)
        archive=f.root/'portable.zip'
        command=subprocess.run([sys.executable,str(completion.SCRIPTS/'bundle_cli.py'),'checkpoint','--state',str(f.state_path),'--output',str(archive)],capture_output=True,text=True)
        self.assertEqual(0,command.returncode,command.stdout+command.stderr)
        command=subprocess.run([sys.executable,str(completion.SCRIPTS/'bundle_cli.py'),'import-bundle','--input',str(archive),'--output-dir',str(f.root/'resumed')],capture_output=True,text=True)
        self.assertNotEqual(0,command.returncode);self.assertIn('study_comparison_failed',command.stdout)
        state=study.read(f.state_path);state['source']['document_page_span']=[1,1];f.f.write('evaluation-state.json',state)
        other=self.fixture(different=True,policy_change=True);study_cli.migrate(other.args);state=study.read(other.state_path);state.pop('study_comparison')
        with self.assertRaisesRegex(ValueError,'binding is missing'):study.preflight_state(state,other.state_path)

    def test_policy_template_is_unfrozen_and_no_missing_approval_can_change_policy(self):
        f=self.fixture(policy_change=True)
        approval=study.read(f.args.approval);approval.pop('study_policy_template_sha256');Path(f.args.approval).write_bytes(study_cli.payload(approval))
        before=f.state_path.read_bytes()
        with self.assertRaisesRegex(ValueError,'template bytes'):study_cli.migrate(f.args)
        self.assertEqual(before,f.state_path.read_bytes())
        source={'policy_id':'UNFROZEN-REFERENCE','source_scope':{k:f.policy['source_scope'][k] for k in ('source_sha256','document_page_span','page_map_sha256','chunk_manifest_sha256','availability')},'audience':f.policy['audience'],'audit_design':{'mode':'full','candidate_blindness':'required'},'deviations':[]}
        f.f.write('template-input.json',source)
        command=subprocess.run([sys.executable,str(completion.SCRIPTS/'study_cli.py'),'policy-template','--input',str(f.root/'template-input.json'),'--output',str(f.root/'unfrozen.json')],capture_output=True,text=True)
        self.assertEqual(0,command.returncode,command.stdout+command.stderr)
        self.assertNotIn('freeze',study.read(f.root/'unfrozen.json')['policy_semantic_content'])

    def test_native_review_requires_exact_historical_draft_without_claiming_new_review(self):
        import tempfile
        from test_benchmark_compatibility_import import CompatibilityImportFixture
        with tempfile.TemporaryDirectory() as name:
            f=CompatibilityImportFixture(Path(name));f.make_native_v8()
            release=study.read(f.legacy_benchmark)
            descriptor={'artifacts':{'review_ledger':{'file_sha256':study.file_digest(f.review)},'review_inventory':{'file_sha256':study.file_digest(f.inventory)}}}
            study_cli.validate_release_review(release,descriptor,f.legacy_benchmark,f.review,f.inventory,f.legacy_draft)
            with self.assertRaisesRegex(ValueError,'release-draft'):
                study_cli.validate_release_review(release,descriptor,f.legacy_benchmark,f.review,f.inventory)
            draft=study.read(f.legacy_draft);draft['subjects'][0]['meaning']='Unreviewed change';f.legacy_draft.write_bytes(study_cli.payload(draft))
            with self.assertRaisesRegex(ValueError,'Historical reviewed release'):
                study_cli.validate_release_review(release,descriptor,f.legacy_benchmark,f.review,f.inventory,f.legacy_draft)

    def test_native_source_freeze_verifies_real_state_shape_without_git_identity(self):
        import tempfile
        from test_benchmark_compatibility_import import CompatibilityImportFixture
        with tempfile.TemporaryDirectory() as name:
            f=CompatibilityImportFixture(Path(name));f.make_native_v8()
            release=study.read(f.legacy_benchmark)
            lineage={'kind':'native_source_freeze','source_only_state_sha256':study.file_digest(f.legacy_state),
                'draft_file_sha256':study.file_digest(f.legacy_draft),'review_file_sha256':study.file_digest(f.review),
                'review_inventory_file_sha256':study.file_digest(f.inventory),'checkpoint_artifacts':[]}
            lock={'release':{'lineage':lineage,'benchmark_file_sha256':study.file_digest(f.legacy_benchmark)}}
            study.validate_native_lineage(lock,release,f.legacy_state,f.legacy_draft,f.review,f.inventory)
            self.assertNotIn('artifact_freeze_commit',lineage)
            state=study.read(f.legacy_state);state['candidate']={'candidate_id':'EXPOSED'}
            f.legacy_state.write_bytes(study_cli.payload(state));lineage['source_only_state_sha256']=study.file_digest(f.legacy_state)
            with self.assertRaisesRegex(ValueError,'candidate exposure'):
                study.validate_native_lineage(lock,release,f.legacy_state,f.legacy_draft,f.review,f.inventory)

    def test_standalone_density_measurement_requires_complete_owned_pages_and_totals(self):
        f=self.fixture()
        measurement={'schema_version':'source-density-measurement-v1','measurement_id':'INDEPENDENT-COUNT',
            **{k:v for k,v in f.lock['source_scope'].items() if k!='document_page_span'},
            'candidate_information_used':False,'extractor':'synthetic counter','script_sha256':'a'*64,'extraction_xml_sha256':'b'*64,
            'protocol':{'inclusions':['Body prose'],'exclusions':['Running heads'],'token':'Whitespace-delimited words','scope':'Owned pages once'},
            'total_indexable_source_words':100,'chunks':[{'chunk_id':'CHUNK-001','owned_document_pages':[1],'indexable_source_words':100}],
            'pages':[{'document_page':1,'source_page_label':'1','indexable_source_words':100}]}
        path=f.f.write('release/source/measurement.json',measurement)
        row=f.lock['density_basis']['chunks'][0];row['source_artifact']={'path':'source/measurement.json','sha256':study.file_digest(path)}
        f.lock['density_basis']['measurement_sha256']=study.digest(f.lock['density_basis']['chunks']);self_hash(f.lock,'lock_sha256')
        Path(f.args.study_lock).write_bytes(study_cli.payload(f.lock))
        approval=study.read(f.args.approval);approval['study_lock_sha256']=f.lock['lock_sha256'];Path(f.args.approval).write_bytes(study_cli.payload(approval))
        study_cli.migrate(f.args)
        study.preflight_state(study.read(f.state_path),f.state_path,require_density=True)
        page_map=study.read(f.root/'page-map.json');owners={1:'CHUNK-001'}
        for field,value in [('pages',[]),('total_indexable_source_words',101)]:
            broken=deepcopy(measurement);broken[field]=value
            with self.assertRaises(ValueError):study.validate_density_measurement(broken,f.lock,page_map,owners)
        broken=deepcopy(measurement);broken['chunks'][0]['owned_document_pages']=[2]
        with self.assertRaisesRegex(ValueError,'owned-page'):study.validate_density_measurement(broken,f.lock,page_map,owners)

    def test_portable_checkpoint_roundtrip_preserves_migration_proof_and_rejects_before_extract(self):
        for changes in ({},{'different':True,'policy_change':True}):
            with self.subTest(changes=changes):
                f=self.fixture(**changes);study_cli.migrate(f.args)
                archive=f.root/'portable.zip';output=f.root/'resumed'
                result=subprocess.run([sys.executable,str(completion.SCRIPTS/'bundle_cli.py'),'checkpoint','--state',str(f.state_path),'--output',str(archive)],capture_output=True,text=True)
                self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                result=subprocess.run([sys.executable,str(completion.SCRIPTS/'bundle_cli.py'),'import-bundle','--input',str(archive),'--output-dir',str(output)],capture_output=True,text=True)
                self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                study.preflight_state(study.read(output/'evaluation-state.json'),output/'evaluation-state.json')
        state=study.read(f.state_path);state['source']['document_page_span']=[1,2];f.f.write('evaluation-state.json',state)
        archive=f.root/'invalid.zip'
        subprocess.run([sys.executable,str(completion.SCRIPTS/'bundle_cli.py'),'checkpoint','--state',str(f.state_path),'--output',str(archive)],capture_output=True,check=True)
        rejected=f.root/'rejected'
        result=subprocess.run([sys.executable,str(completion.SCRIPTS/'bundle_cli.py'),'import-bundle','--input',str(archive),'--output-dir',str(rejected)],capture_output=True,text=True)
        self.assertNotEqual(0,result.returncode);self.assertFalse(rejected.exists())

    def test_same_total_different_density_map_and_false_map_self_hash_are_rejected(self):
        f=self.fixture();study_cli.migrate(f.args)
        state=study.read(f.state_path)
        structure,_=study.registered_document(state,f.state_path,'structure_audit','structure-audit-v6')
        manifest=study.read(f.root/'chunk-manifest.json');second=deepcopy(manifest['chunks'][0]);second.update(chunk_id='CHUNK-002',packet_order=2);manifest['chunks'].append(second)
        lock=deepcopy(f.lock);lock['density_basis']['chunks'].append({**deepcopy(lock['density_basis']['chunks'][0]),'chunk_id':'CHUNK-002','indexable_source_words':50})
        lock['density_basis']['measurement_sha256']=study.digest(lock['density_basis']['chunks']);self_hash(lock,'lock_sha256')
        structure['density']['chapter_measurements']=[{'chunk_id':'CHUNK-001','indexable_source_words':50},{'chunk_id':'CHUNK-002','indexable_source_words':100}]
        with self.assertRaisesRegex(ValueError,'exact density measurement map'):
            study.evaluation_identity(benchmark=study.read(f.root/'source-benchmark.json'),policy=f.policy,structure=structure,manifest=manifest,audit_mode=lock['audit_mode'],rubric=lock['rubric_version'],calculation_profile=lock['calculation_profile'],lock=lock)
        page_map=study.read(f.root/'page-map.json');page_map['pages'][0]['source_page_label']='2'
        path=f.f.write('page-map.json',page_map)
        next(r for r in state['artifacts'] if r['path']=='page-map.json')['sha256']=study.file_digest(path)
        with self.assertRaisesRegex(ValueError,'does not reconstruct'):study.preflight_state(state,f.state_path)

    def test_audit_import_runs_study_preflight_before_accepting_inputs(self):
        import parallel_candidate_audit_cli as audit
        f=self.fixture();study_cli.migrate(f.args)
        state=study.read(f.state_path);state['source']['document_page_span']=[1,2];f.f.write('evaluation-state.json',state)
        with self.assertRaisesRegex(audit.PreparationError,'scope mismatch'):
            audit.load_frozen_inputs(argparse.Namespace(state=str(f.state_path)),'missing_access')

    def test_later_study_binding_keeps_prior_policy_provenance_and_unfinished_audits(self):
        f=self.fixture(policy_change=True);study_cli.migrate(f.args)
        state=study.read(f.state_path);policy,record=study.registered_document(state,f.state_path,'define_policy','subject-index-evaluation-policy-v4')
        original_bytes=(f.root/record['path']).read_bytes()
        approval=study.read(f.args.approval);approval.update(approval_id='LATER-EXPLICIT-AUTHORIZATION',previous_state_sha256=study.file_digest(f.state_path),previous_policy_sha256=policy['policy_sha256'],previous_benchmark_sha256=state['candidate']['benchmark_sha256'])
        Path(f.args.approval).write_bytes(study_cli.payload(approval));f.args.output_dir='migration-2'
        result=study_cli.migrate(f.args)
        self.assertFalse(result['semantic_change']);self.assertFalse(result['policy_semantic_change'])
        state=study.read(f.state_path);study.preflight_state(state,f.state_path)
        self.assertEqual(original_bytes,(f.root/record['path']).read_bytes())
        self.assertEqual('not_started',state['stages']['structure_audit']['status'])

    def test_current_typed_freeze_migrates_successor_without_registering_temporary_screen(self):
        f=self.fixture();source_state=f.current_source_release(revised=True)
        historical=source_state.read_bytes()
        result=study_cli.migrate(f.args)
        self.assertTrue(result['semantic_change'])
        self.assertEqual(historical,source_state.read_bytes())
        state=study.read(f.state_path);study.preflight_state(state,f.state_path)
        self.assertNotIn('release_review_inventory',state['study_comparison'])
        self.assertFalse(any(r.get('schema_version')=='source-benchmark-review-inventory-v1' for r in state['artifacts']))
        self.assertFalse((f.root/'migration/release-review-inventory.json').exists())
        self.assertTrue(study.read(f.root/'migration/release-review.json')['approved_changes'])
        self.assertNotIn('changes',study.read(f.root/'migration/release-review.json'))
        self.assertEqual('not_started',state['stages']['missing_access_audit']['status'])
        archive=f.root/'current-portable.zip';output=f.root/'current-resumed'
        from test_benchmark_freeze import run_cli
        run_cli('bundle_cli.py','checkpoint','--state',f.state_path,'--output',archive)
        run_cli('bundle_cli.py','import-bundle','--input',archive,'--output-dir',output)
        study.preflight_state(study.read(output/'evaluation-state.json'),output/'evaluation-state.json')

    def test_current_freeze_rejects_unapproved_changes_and_missing_typed_registration(self):
        f=self.fixture();source_state=f.current_source_release(revised=True)
        review=study.read(f.args.release_review);review['approved_changes']=[]
        Path(f.args.release_review).write_bytes(study_cli.payload(review))
        state=study.read(source_state)
        for record in state['artifacts']:
            if record['stage']=='benchmark_review':
                record['sha256']=study.file_digest(f.args.release_review)
        source_state.write_bytes(study_cli.payload(state))
        lineage=f.lock['release']['lineage'];lineage['source_only_state_sha256']=study.file_digest(source_state);lineage['review_file_sha256']=study.file_digest(f.args.release_review)
        with self.assertRaisesRegex(ValueError,'approved_changes'):
            study.validate_native_lineage(f.lock,f.release,source_state,Path(f.args.release_draft),Path(f.args.release_review))
        state['artifacts']=[r for r in state['artifacts'] if r['stage']!='benchmark_review']
        source_state.write_bytes(study_cli.payload(state));lineage['source_only_state_sha256']=study.file_digest(source_state)
        with self.assertRaisesRegex(ValueError,'registration mismatch'):
            study.validate_native_lineage(f.lock,f.release,source_state,Path(f.args.release_draft),Path(f.args.release_review))

    def test_source_freeze_public_outputs_omit_private_transport_and_density_paths(self):
        a=self.fixture();a.current_source_release()
        private_paths=['/Users/private/native-freeze.zip',r'C:\Private\native-freeze.zip',r'\\server\restricted\native-freeze.zip','file:///Users/private/native-freeze.zip']
        a.lock['release']['lineage']['checkpoint_artifacts']=[{'path':path,'sha256':str(i+1)*64} for i,path in enumerate(private_paths)]
        self_hash(a.lock,'lock_sha256');Path(a.args.study_lock).write_bytes(study_cli.payload(a.lock))
        approval=study.read(a.args.approval);approval['study_lock_sha256']=a.lock['lock_sha256'];Path(a.args.approval).write_bytes(study_cli.payload(approval))
        b=self.fixture(evaluation_id='EVAL-CURRENT-SECOND')
        for name in ('study_lock','release_benchmark','release_review','release_review_inventory','release_descriptor','release_state','release_draft'):
            setattr(b.args,name,getattr(a.args,name))
        approval=study.read(b.args.approval);approval.update(study_lock_sha256=a.lock['lock_sha256'],target_benchmark_sha256=a.release['benchmark_sha256'])
        Path(b.args.approval).write_bytes(study_cli.payload(approval))
        for f in (a,b):
            study_cli.migrate(f.args)
            for command in ('score','build-report'):
                result=f.f.run_cli(command,'--state',str(f.state_path));self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            state=study.read(f.state_path)
            self.assertEqual(private_paths,[r['path'] for r in study.read(f.root/'migration/study-benchmark-lock.v1.json')['release']['lineage']['checkpoint_artifacts']])
            for record in state['artifacts']:
                if record['visibility']=='public':
                    encoded=(f.root/record['path']).read_text()
                    self.assertNotIn('checkpoint_artifacts',encoded)
                    for path in private_paths:self.assertNotIn(json.dumps(path)[1:-1],encoded)
            identity=study.preflight_state(state,f.state_path,require_density=True)
            self.assertNotIn('checkpoint_artifacts',identity['release']['lineage'])
            self.assertTrue(all('path' not in r['source_artifact'] for r in identity['density_basis']['chunks']))
        output=a.root/'public-comparison'
        study_cli.assemble(argparse.Namespace(state=[str(a.state_path),str(b.state_path)],output_dir=str(output)))
        for path in output.rglob('*.json'):
            encoded=path.read_text();self.assertNotIn('checkpoint_artifacts',encoded)
            for private in private_paths:self.assertNotIn(json.dumps(private)[1:-1],encoded)
        for kind in ('current_source_freeze','native_source_freeze'):
            release=deepcopy(a.lock['release']);release['lineage']['kind']=kind
            self.assertNotIn('checkpoint_artifacts',study.public_release_identity(release)['lineage'])
            relocated=deepcopy(release);relocated['lineage']['checkpoint_artifacts']=[]
            self.assertEqual(study.public_release_identity(release),study.public_release_identity(relocated))
        for private in private_paths:
            changed=deepcopy(a.lock);changed['release']['release_id']=private;self_hash(changed,'lock_sha256')
            with self.assertRaisesRegex(ValueError,'absolute path'):study.validate_lock(changed)

    def test_assembly_preserves_exact_report_bytes_and_rejects_stale_report_without_output(self):
        a=self.fixture();b=self.fixture(evaluation_id='EVAL-REPORT-SECOND')
        approval=study.read(b.args.approval)
        shutil.copytree(a.root/'release',b.root/'release',dirs_exist_ok=True)
        approval.update(study_lock_sha256=a.lock['lock_sha256'],target_benchmark_sha256=a.release['benchmark_sha256'])
        Path(b.args.approval).write_bytes(study_cli.payload(approval))
        for f in (a,b):
            study_cli.migrate(f.args)
            for command in ('score','build-report'):
                result=f.f.run_cli(command,'--state',str(f.state_path));self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        state=study.read(b.state_path)
        report,report_record=study.registered_document(state,b.state_path,'web_report','subject-index-web-report-v10')
        projection,projection_record=study.registered_document(state,b.state_path,'web_report',web_projection.PROJECTION_SCHEMA_VERSION)
        report_path=b.root/report_record['path'];projection_path=b.root/projection_record['path']
        def bind_report(report_bytes, current_report_record, current_projection):
            current_report_record['sha256']=hashlib.sha256(report_bytes).hexdigest()
            current_report_record['artifact_id']=completion.state_cli.artifact_id(current_report_record['path'],current_report_record['sha256'])
            for refs in [current_projection['provenance']['source_artifacts'],current_projection['score_views']['views'][0]['provenance_artifacts']]:
                for ref in refs:
                    if ref.get('schema_version')=='subject-index-web-report-v10':ref['sha256']=current_report_record['sha256']
        # Keep deliberately noncanonical whitespace: assembly must copy, not serialize.
        exact=b'\n \n'+report_path.read_bytes()+b'\n'
        bind_report(exact,report_record,projection);report_path.write_bytes(exact)
        self_hash(projection,'projection_sha256');projection_path.write_bytes(study_cli.payload(projection))
        projection_record['sha256']=study.file_digest(projection_path)
        b.f.write('evaluation-state.json',state)
        output=a.root/'with-reports'
        study_cli.assemble(argparse.Namespace(state=[str(a.state_path),str(b.state_path)],output_dir=str(output)))
        member=study.read(output/'comparison.json')['members'][1]
        self.assertEqual(exact,(output/member['web_report_path']).read_bytes())
        self.assertEqual(study.file_digest(report_path),member['web_report_file_sha256'])
        baseline={path:path.read_bytes() for path in (b.state_path,report_path,projection_path)}
        cases=('bytes','stale_projection_binding','authoritative_binding','study_identity','benchmark_identity','comparability_wrapper','projection_provenance','methodology','private','missing')
        for case in cases:
            with self.subTest(case=case):
                for path,content in baseline.items():path.write_bytes(content)
                current=study.read(b.state_path)
                current_report=study.read(report_path);current_projection=study.read(projection_path)
                record=next(r for r in current['artifacts'] if r['path']==report_record['path'])
                if case=='bytes':report_path.write_bytes(exact+b'\n')
                elif case=='private':record['visibility']='private'
                elif case=='missing':current['artifacts'].remove(record)
                elif case=='projection_provenance':current_projection['provenance']['judgment_policy_sha256']='0'*64
                elif case=='authoritative_binding':
                    for ref in current_projection['score_views']['views'][0]['provenance_artifacts']:
                        if ref.get('schema_version')=='subject-index-web-report-v10':ref['sha256']='0'*64
                else:
                    if case=='stale_projection_binding':current_report['summary']='A later report not bound by this projection.'
                    elif case=='study_identity':current_report['comparability']['study_identity']['audit_mode']='pilot'
                    elif case=='comparability_wrapper':current_report['comparability']['benchmark_sha256']='0'*64
                    elif case=='benchmark_identity':current_report['methodology']['benchmark']['version']+=1
                    elif case=='methodology':current_report['methodology']['rubric_version']='stale-rubric'
                    content=study_cli.payload(current_report);report_path.write_bytes(content)
                    if case=='stale_projection_binding':record['sha256']=study.file_digest(report_path)
                    else:bind_report(content,record,current_projection)
                self_hash(current_projection,'projection_sha256');projection_path.write_bytes(study_cli.payload(current_projection))
                next(r for r in current['artifacts'] if r['path']==projection_record['path'])['sha256']=study.file_digest(projection_path)
                b.f.write('evaluation-state.json',current)
                rejected=a.root/f'rejected-report-{case}'
                with self.assertRaises(ValueError):
                    study_cli.assemble(argparse.Namespace(state=[str(a.state_path),str(b.state_path)],output_dir=str(rejected)))
                self.assertFalse(rejected.exists())
                self.assertEqual([],list(a.root.glob('.study-comparison-*')))
