"""V9 cutover uses real preserved V8 proof and rejects identity-only relabeling."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import test_v8_completion as completion
from test_study_comparison import StudyFixture, self_hash
import study_comparison as study
from v9_migration import policy_content, SOURCE_IDENTITIES
from runtime_profile import IDENTITIES

SCRIPTS = completion.SCRIPTS


def v9(*args):
    return subprocess.run([sys.executable, str(SCRIPTS/'v9_cli.py'), *map(str,args)], capture_output=True, text=True)


def prepare_v9(case, *, evaluation_id=None):
    f = StudyFixture(case, evaluation_id=evaluation_id)
    f.current_source_release(revised=True)
    f.args.release_policy = str(Path(f.args.release_state).parent/'evaluation-policy.json')
    source_policy = study.read(f.args.release_policy)
    template = {'schema_version':'subject-index-study-policy-template-v1','policy_semantic_content':policy_content(source_policy)}
    self_hash(template,'template_sha256')
    f.args.study_policy = str(f.f.write('release/v9-policy-template.json',template))
    lock=f.lock
    for key in ('schema_version','policy_profile','rubric_version','calculation_profile'):
        lock[key]=IDENTITIES[lock[key]]
    lock['policy_semantic_sha256']=study.policy_semantic_hash(template)
    lock['source_methodology']={**SOURCE_IDENTITIES,'source_policy_sha256':source_policy['policy_sha256'],'source_policy_file_sha256':study.file_digest(f.args.release_policy)}
    self_hash(lock,'lock_sha256');Path(f.args.study_lock).write_bytes(json.dumps(lock,indent=2).encode())
    approval=study.read(f.args.approval)
    approval.update(study_lock_sha256=lock['lock_sha256'],target_policy_semantic_sha256=lock['policy_semantic_sha256'],study_policy_template_sha256=study.file_digest(f.args.study_policy))
    Path(f.args.approval).write_text(json.dumps(approval,indent=2)+'\n')
    case.addCleanup(f.f.tearDown)
    return f


def migrate(f):
    args=['study','migrate-benchmark']
    for name,value in vars(f.args).items():
        if value is not None:args += ['--'+name.replace('_','-'),value]
    return v9(*args)


class V9RuntimeTests(unittest.TestCase):
    def test_fresh_or_relabelled_unbound_v9_run_is_rejected(self):
        f=prepare_v9(self);output=f.root/'unbound-state.json'
        initialized=v9('state','init','--output',output,'--evaluation-id','EVAL-UNBOUND','--source-title','Synthetic','--source-file',f.root/'source.pdf','--page-start','1','--page-end','1','--intended-readership','Synthetic reader')
        self.assertNotEqual(0,initialized.returncode)
        self.assertIn('v9_migration_required',initialized.stdout)
        self.assertFalse(output.exists())
        policy=v9('policy','--help');self.assertNotEqual(0,policy.returncode)
        from v9_migration import migrate_state_identity
        unbound=study.read(f.state_path);migrate_state_identity(unbound)
        output.write_text(json.dumps(unbound));before=output.read_bytes()
        for command in [('state','validate'),('study','preflight'),('score','score'),('state','adopt-standard-policy')]:
            result=v9(*command,'--state',output)
            self.assertNotEqual(0,result.returncode,result.stdout+result.stderr)
            self.assertEqual(before,output.read_bytes())
        self.assertFalse((f.root/'scoring').exists())

    def test_migration_preserves_source_bytes_and_invalidates_candidate_audits(self):
        f=prepare_v9(self)
        proof_paths=[Path(getattr(f.args,k)) for k in ('release_policy','release_state','release_draft','release_review','release_benchmark')]
        before={p:p.read_bytes() for p in proof_paths}
        old_state=f.state_path.read_bytes()
        result=migrate(f)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        state=study.read(f.state_path)
        self.assertEqual('subject-index-evaluation-state-v7',state['schema_version'])
        self.assertEqual('subject-index-rubric-v9',state['configuration']['rubric_version'])
        for stage in ('locator_chunk_preparation','locator_audit','missing_access_audit','structure_audit','scoring','web_report'):
            self.assertEqual('not_started',state['stages'][stage]['status'])
        self.assertEqual(old_state,(f.root/state['study_comparison']['prior_state']['path']).read_bytes())
        next_action=v9('state','next','--state',f.state_path)
        self.assertEqual(0,next_action.returncode,next_action.stdout+next_action.stderr)
        self.assertEqual('v9_cli.py page-chunks prepare-locator-chunks',json.loads(next_action.stdout)['next_actions'][0]['command'])
        self.assertTrue(all(row['command'].startswith('v9_cli.py ') for row in json.loads(next_action.stdout)['parallel_actions']))
        self.assertEqual(before,{p:p.read_bytes() for p in proof_paths})
        check=v9('study','preflight','--state',f.state_path)
        self.assertEqual(0,check.returncode,check.stdout+check.stderr)
        # The V8 entrypoint does not silently resume a V9 state.
        rejected=f.f.run_cli('score','--state',str(f.state_path))
        self.assertNotEqual(0,rejected.returncode)

    def complete_v9_fixture(self, *, with_overlay=True, evaluation_id=None, source_fixture=None, attempt=None):
        f=prepare_v9(self,evaluation_id=evaluation_id)
        if source_fixture is not None:
            for key in ('release_policy','release_state','release_draft','release_review','release_benchmark','release_descriptor','release_review_inventory','study_lock','study_policy'):
                setattr(f.args,key,getattr(source_fixture.args,key))
            f.lock=deepcopy(source_fixture.lock)
            approval=study.read(f.args.approval)
            approval.update(study_lock_sha256=f.lock['lock_sha256'],target_benchmark_sha256=f.lock['release']['benchmark_sha256'],target_policy_semantic_sha256=f.lock['policy_semantic_sha256'],study_policy_template_sha256=study.file_digest(f.args.study_policy))
            Path(f.args.approval).write_text(json.dumps(approval))
        if attempt:
            structure=study.read(f.f.structure_path)
            structure['scoring_context']['candidate_attempt']={'status':attempt,'evidence_ids':['EVID-ATTEMPT-SYNTHETIC']}
            f.f.structure_path.write_text(json.dumps(structure))
            initial=study.read(f.state_path)
            initial['artifacts']=[f.f.record(f.f.structure_path,'structure_audit',r['artifact_type'],r['schema_version']) if r['stage']=='structure_audit' else r for r in initial['artifacts']]
            f.state_path.write_text(json.dumps(initial))
        for command, extra in [('score',[])]:
            original=f.f.run_cli(command,'--state',str(f.state_path),*extra)
            self.assertEqual(0,original.returncode,original.stdout+original.stderr)
        original_calculation=study.read(f.root/'scoring/dimension-calculations.v6.json')
        approval=study.read(f.args.approval);approval['previous_state_sha256']=study.file_digest(f.state_path);Path(f.args.approval).write_text(json.dumps(approval))
        prior=study.read(f.state_path)
        result=migrate(f)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        state=study.read(f.state_path)
        policy=study.read(f.root/'migration/selected-policy.json')
        benchmark=study.read(f.root/'migration/selected-benchmark.json')
        # Re-create this tiny synthetic candidate audit after migration. This is
        # test data construction, never a production audit-transfer operation.
        for path in (f.root/'candidate').glob('*.json'):
            path.write_text(path.read_text().replace(f.policy['policy_sha256'],policy['policy_sha256']).replace(prior['candidate']['benchmark_sha256'],benchmark['benchmark_sha256']))
        structure=f.f.structure_path
        structure.write_text(structure.read_text().replace(f.policy['policy_sha256'],policy['policy_sha256']))
        for stage in ('locator_chunk_preparation','locator_audit','missing_access_audit'):
            state['stages'][stage]=deepcopy(prior['stages'][stage])
            for record in prior['artifacts']:
                if record['stage']==stage:
                    fresh=f.f.record(f.root/record['path'],stage,record['artifact_type'],record.get('schema_version'))
                    state['artifacts'].append(fresh)
        f.state_path.write_text(json.dumps(state,indent=2)+'\n')
        for command,extra in [('register-structure',['--input',str(structure)]),('score',['--output-dir','scoring-v9']),('build-report',[])]:
            if command=='build-report' and with_overlay:
                overlay={'schema_version':'ohfr-v8-representation-correction-overlay-v1','evaluation_id':prior['evaluation_id'],'overlay_role':'display_only_counterfactual_bound_to_canonical_v8','causal_classification':'confirmed_representation_only','affected_heading_count':1,'affected_node_ids':['NODE-001'],'character_replacement_count':1,'headings':[{'node_id':'NODE-001'}],'character_replacements':[{'node_id':'NODE-001'}],'adjusted_item_changes':{},'provenance':{'basis':'synthetic confirmed ledger'}}
                self_hash(overlay,'overlay_sha256');overlay_path=f.f.write('corrections/overlay.json',overlay)
                with_overlay=study.read(f.state_path)
                with_overlay['artifacts'].append(f.f.record(overlay_path,'scoring','correction_overlay',overlay['schema_version']))
                f.state_path.write_text(json.dumps(with_overlay))
                before=f.state_path.read_bytes();rejected=v9('score','build-report','--state',f.state_path)
                self.assertNotEqual(0,rejected.returncode)
                self.assertIn('legacy_overlay_requires_rebinding',rejected.stdout)
                self.assertEqual(before,f.state_path.read_bytes())
                overlay.update(schema_version='ohfr-v9-representation-correction-overlay-v1',overlay_role='display_only_counterfactual_bound_to_canonical_v9')
                self_hash(overlay,'overlay_sha256');f.f.write('corrections/overlay.json',overlay)
                with_overlay['artifacts'][-1]=f.f.record(overlay_path,'scoring','correction_overlay',overlay['schema_version'])
                f.state_path.write_text(json.dumps(with_overlay))
            result=v9('score',command,'--state',f.state_path,*extra)
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        calculations=study.read(f.root/'scoring-v9/dimension-calculations.v7.json')
        report=study.read(f.root/'scoring-v9/web-report.v11.json')
        current=study.read(f.state_path)
        projected=next(r for r in current['artifacts'] if r.get('schema_version')=='ohfr-v9-canonical-web-projection-v1')
        projection=study.read(f.root/projected['path'])
        from v9_contract import contract_errors
        self.assertFalse(contract_errors(calculations))
        self.assertFalse(contract_errors(report))
        self.assertFalse(contract_errors(projection))
        self.assertEqual('subject-index-rubric-v9',calculations['rubric_version'])
        selectivity=next(d for d in calculations['dimensions'] if d['dimension_id']=='editorial_selectivity')
        self.assertIsInstance(selectivity['density_points_out_of_5'],str)
        self.assertEqual(original_calculation['overall_percentage'],calculations['overall_percentage'])
        self.assertEqual(original_calculation['final_rounding'],calculations['final_rounding'])
        added={'weighted_percentage_numerator','total_weighted_percentage_numerator','total_indexable_source_words','substantive_selectivity_percentage','density_points_out_of_5','substantive_points_out_of_10','density_fit_percentage','input_artifacts'}
        def original_shape(value):
            if isinstance(value,dict):return {k:original_shape(v) for k,v in value.items() if k not in added}
            if isinstance(value,list):return [original_shape(v) for v in value]
            if isinstance(value,str) and value.startswith('subject-index-dimension-calculation-v8:'):return value.replace('-v8:', '-v7:',1)
            return value
        self.assertEqual(original_shape(original_calculation['dimensions']),original_shape(calculations['dimensions']))
        checkpoint=f.root/'exports/v9-checkpoint.zip'
        exported=v9('bundle','checkpoint','--state',f.state_path,'--output',checkpoint)
        self.assertEqual(0,exported.returncode,exported.stdout+exported.stderr)
        restored=f.root/'restored'
        imported=v9('bundle','import-bundle','--input',checkpoint,'--output-dir',restored)
        self.assertEqual(0,imported.returncode,imported.stdout+imported.stderr)
        resumed=v9('state','validate','--state',restored/'evaluation-state.json')
        self.assertEqual(0,resumed.returncode,resumed.stdout+resumed.stderr)
        self.completed_fixture=f
        return f

    def test_native_v9_score_report_and_projection(self):
        f=self.complete_v9_fixture()
        projection=study.read(f.root/'scoring-v9/v9-canonical-projection/projection.v1.json')
        self.assertEqual('diagnostic_overlay_only',projection['score_views']['projection_adjustment_status'])
        self.assertIsNone(projection['correction_outcomes']['corrected_cross_reference_id'])
        from schema_validation import schema_errors
        adjusted=deepcopy(projection)
        alternate=deepcopy(adjusted['score_views']['views'][0]);alternate.update(view_id='representation_adjusted',view_kind='counterfactual')
        adjusted['score_views']['views'].append(alternate)
        self.assertTrue(schema_errors(adjusted,'web-projection-v9.schema.json'))
        overlay=study.read(f.root/'scoring-v9/v9-canonical-projection/data/correction-overlay.v1.json')
        self.assertFalse(schema_errors(overlay,'correction-overlay-v9.schema.json'))
        overlay['cross_reference_resolution']={}
        self.assertTrue(schema_errors(overlay,'correction-overlay-v9.schema.json'))

    def test_observed_only_comparison(self):
        first=self.complete_v9_fixture(with_overlay=False,evaluation_id='EVAL-FIRST')
        second=self.complete_v9_fixture(with_overlay=False,evaluation_id='EVAL-SECOND',source_fixture=first)
        assembled=first.root/'comparison'
        result=v9('study','assemble-comparison','--state',first.state_path,'--state',second.state_path,'--output-dir',assembled)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        manifest=study.read(assembled/'comparison.json')
        self.assertEqual(2,len(manifest['members']))
        self.assertTrue(all(row['web_report_path'].endswith('web-report.v11.json') for row in manifest['members']))
        projection=study.read(first.root/'scoring-v9/v9-canonical-projection/projection.v1.json')
        self.assertEqual('not_applicable',projection['score_views']['projection_adjustment_status'])
        report=study.read(second.root/'scoring-v9/web-report.v11.json')
        self.assertEqual(report['density']['density_fit_percentage'],report['density']['scoring_density_fit_percentage'])
        self.comparison_fixtures=(first,second,assembled)


    def test_substantive_target_policy_change_fails_before_state_mutation(self):
        f=prepare_v9(self);before=f.state_path.read_bytes()
        template=study.read(f.args.study_policy)
        template['policy_semantic_content']['audience']['label']='A different audience'
        self_hash(template,'template_sha256');Path(f.args.study_policy).write_text(json.dumps(template))
        f.lock['policy_semantic_sha256']=study.policy_semantic_hash(template);self_hash(f.lock,'lock_sha256');Path(f.args.study_lock).write_text(json.dumps(f.lock))
        approval=study.read(f.args.approval);approval.update(study_lock_sha256=f.lock['lock_sha256'],target_policy_semantic_sha256=f.lock['policy_semantic_sha256'],study_policy_template_sha256=study.file_digest(f.args.study_policy));Path(f.args.approval).write_text(json.dumps(approval))
        result=migrate(f)
        self.assertNotEqual(0,result.returncode)
        self.assertIn('substantive source settings',result.stdout+result.stderr)
        self.assertEqual(before,f.state_path.read_bytes())
        self.assertFalse((f.root/'migration').exists())

    def test_unknown_or_missing_source_provenance_fails_closed(self):
        f=prepare_v9(self);before=f.state_path.read_bytes()
        lock_bytes=Path(f.args.study_lock).read_bytes()
        approval_bytes=Path(f.args.approval).read_bytes()
        policy_path=f.args.release_policy
        source_bytes=Path(f.args.release_draft).read_bytes()
        cases=('unknown_field','wrong_profile','wrong_policy_hash','wrong_policy_file_hash','absent_policy','source_chain_mismatch')
        for case in cases:
            with self.subTest(case=case):
                lock=json.loads(lock_bytes);f.args.release_policy=policy_path
                Path(f.args.release_draft).write_bytes(source_bytes)
                if case=='unknown_field':lock['source_methodology']['unreviewed_extension']=True
                elif case=='wrong_profile':lock['source_methodology']['policy_profile']='subject-index-standard-policy-v8.1'
                elif case=='wrong_policy_hash':lock['source_methodology']['source_policy_sha256']='0'*64
                elif case=='wrong_policy_file_hash':lock['source_methodology']['source_policy_file_sha256']='0'*64
                elif case=='absent_policy':f.args.release_policy=None
                else:Path(f.args.release_draft).write_bytes(source_bytes+b' ')
                self_hash(lock,'lock_sha256');Path(f.args.study_lock).write_text(json.dumps(lock))
                approval=json.loads(approval_bytes);approval['study_lock_sha256']=lock['lock_sha256'];Path(f.args.approval).write_text(json.dumps(approval))
                result=migrate(f)
                self.assertNotEqual(0,result.returncode,result.stdout+result.stderr)
                self.assertEqual(before,f.state_path.read_bytes())
                self.assertFalse((f.root/'migration').exists())

    def test_candidate_normalization_keeps_v8_output_under_v9_identity(self):
        from test_candidate_preparation import layout
        f=prepare_v9(self)
        candidate=f.root/'synthetic-candidate.txt';candidate.write_text('Alpha, 1\n')
        source=layout([('Alpha, 1',0)])
        source['source_sha256']=completion.SOURCE_SHA
        source['candidate_sha256']=study.file_digest(candidate)
        source['pdf_metadata']['sha256']=source['candidate_sha256']
        layout_path=f.f.write('synthetic-layout.json',source)
        common=['normalize','--state',str(f.state_path),'--page-map',str(f.root/'page-map.json'),'--chunk-manifest',str(f.root/'chunk-manifest.json'),'--source-edition','synthetic-edition','--candidate-id',source['candidate_id'],'--candidate-file',str(candidate),'--layout',str(layout_path)]
        old=subprocess.run([sys.executable,str(SCRIPTS/'candidate_preparation_cli.py'),*common,'--policy',str(f.root/'evaluation-policy.json'),'--output-dir',str(f.root/'prep-v8')],capture_output=True,text=True)
        self.assertEqual(0,old.returncode,old.stdout+old.stderr)
        migrated=migrate(f);self.assertEqual(0,migrated.returncode,migrated.stdout+migrated.stderr)
        new=v9('prepare-candidate',*common,'--policy',f.root/'migration/selected-policy.json','--output-dir',f.root/'prep-v9')
        self.assertEqual(0,new.returncode,new.stdout+new.stderr)
        old_files={p.relative_to(f.root/'prep-v8'):p.read_bytes() for p in (f.root/'prep-v8').rglob('*.json')}
        new_files={p.relative_to(f.root/'prep-v9'):p.read_bytes() for p in (f.root/'prep-v9').rglob('*.json')}
        self.assertEqual(old_files,new_files)

    def test_source_policy_template_preserves_all_other_content(self):
        f=prepare_v9(self);output=f.root/'from-source.json'
        result=v9('study','policy-template','--input',f.args.release_policy,'--output',output,'--from-source-policy')
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        self.assertEqual(study.read(f.args.study_policy),study.read(output))

class V9GoldenTests(unittest.TestCase):
    def test_v8_and_v9_equal_the_pinned_v8_2_boundary_fixture(self):
        expected=json.loads((Path(__file__).parent/'fixtures/v9/v8.2-boundaries.json').read_text())
        for profile in ('v8','v9'):
            with self.subTest(profile=profile):
                result=subprocess.run([sys.executable,str(Path(__file__).with_name('v9_golden_probe.py')),profile],capture_output=True,text=True)
                self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                self.assertEqual(expected,json.loads(result.stdout))
        self.assertEqual(['0','20','40','60','80','100'],sorted(set(expected['density_bands'].values()),key=int))
        self.assertEqual(6.02,expected['rounding']['1.004999']['overall_percentage'])
        self.assertEqual(6.03,expected['rounding']['1.005']['overall_percentage'])
        self.assertEqual('5.833333333333333333333333334',expected['selectivity']['operation_order']['weighted_contribution'])

    def test_non_attempt_density_override_is_explicit_without_fake_full_report(self):
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('v9_density_override_probe.py'))],capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        fixture=json.loads(result.stdout)
        self.assertIs(fixture['publishable_full_evaluation'],False)
        density=fixture['density_collection']
        self.assertEqual('50',density['density_fit_percentage'])
        self.assertEqual('0',density['scoring_density_fit_percentage'])
        self.assertEqual({'percentage':'0','rule':'candidate_attempt:structurally_incomplete'},density['scoring_override'])
        self.assertEqual('0',fixture['editorial_selectivity']['density_points_out_of_5'])
        self.assertEqual('0',fixture['editorial_selectivity']['weighted_contribution'])

    def test_density_and_point_tampering_is_rejected_exactly(self):
        from v9_contract import contract_errors
        density={'chapter_measurements':[{'indexable_source_words':101,'path_fit_percentage':'100','occurrence_fit_percentage':'80','unit_fit_percentage':'90','weighted_percentage_numerator':'9090'}], 'total_indexable_source_words':101,'total_weighted_percentage_numerator':'9090','density_fit_percentage':'90'}
        self.assertEqual([],contract_errors(density))
        for key,value in [('density_fit_percentage','89.99999999999999999999999999'),('total_indexable_source_words',100),('total_weighted_percentage_numerator','9091')]:
            bad=deepcopy(density);bad[key]=value;self.assertTrue(contract_errors(bad))
        score={'dimension_percentage':'80','weight':15,'weighted_contribution':'12','awarded_points':'12','maximum_points':'15'}
        self.assertEqual([],contract_errors(score))
        score['awarded_points']='12.00000000000000000000001';self.assertTrue(contract_errors(score))
        self.assertTrue(contract_errors({'grade':{'rating':5,'score':100}}))
        self.assertEqual([],contract_errors({'keep_rating_credit':{'rating_credit':1}}))


if __name__ == "__main__":
    unittest.main()
