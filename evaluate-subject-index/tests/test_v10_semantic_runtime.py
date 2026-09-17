"""Synthetic explicit adoption and native successor output integration."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_v10_runtime as baseline
from test_v10_runtime import study,SCRIPTS
from v10_execution import BASELINE,CONTRACT,CONSTITUENTS,payload_fingerprint


def command(*args):
    return subprocess.run([sys.executable,str(SCRIPTS/'v10_cli.py'),*map(str,args)],capture_output=True,text=True)


def compatibility(f,revision=None):
    state=study.read(f.state_path);binding=state['study_comparison']['lock'];lock=study.read(f.root/binding['path'])
    release={'schema_version':'subject-index-successor-release-v3','methodology_commit':BASELINE,'artifacts':{'study_lock':{'path':'synthetic-lock.json','sha256':binding['sha256']}}}
    release['release_sha256']=study.digest(release);p=f.root/'synthetic-execution-release.json';p.write_text(json.dumps(release))
    document={'schema_version':'subject-index-v10-execution-compatibility-v1','compatibility_id':'COMPAT-SYNTHETIC','baseline_runtime_commit':BASELINE,'successor_runtime_commit':revision or '1'*40,'execution_contract_id':CONTRACT,'contract_constituents':CONSTITUENTS,'runtime_payload_sha256':payload_fingerprint(),'common_lock_file_sha256':binding['sha256'],'common_lock_sha256':lock['lock_sha256'],'source_release_file_sha256':study.file_digest(p),'source_release_sha256':release['release_sha256'],'authorized_by':'SYNTHETIC-REVIEWER','authorization_reference':'Synthetic compatibility test only','approved_at':'2026-09-17T00:00:00Z'}
    document['compatibility_sha256']=study.digest(document);q=f.root/'synthetic-compatibility.json';q.write_text(json.dumps(document));return q,p


class SemanticRuntimeTests(unittest.TestCase):
    def test_material_optional_failure_scores_and_builds_report(self):
        case=baseline.V10RuntimeTests();self.addCleanup(case.doCleanups);f=case.complete_fixture(amendment_style='none')
        approval,release=compatibility(f)
        adopted=command('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','semantic-execution')
        self.assertEqual(0,adopted.returncode,adopted.stdout+adopted.stderr)
        state=study.read(f.state_path)
        audit_record=next(r for r in state['artifacts'] if r.get('artifact_type')=='missing_access_audit')
        audit_path=f.root/audit_record['path'];audit=study.read(audit_path);subject=audit['subject_judgments'][0]
        subject.update(priority='optional',severity='major',stance_preserved='no',error_codes=['STA'])
        audit_path.write_text(json.dumps(audit))
        audit_record.update(sha256=study.file_digest(audit_path),artifact_id=baseline.completion.state_cli.artifact_id(audit_record['path'],study.file_digest(audit_path)))
        structure_record=next(r for r in state['artifacts'] if r.get('artifact_type')=='structure_audit')
        structure_path=f.root/structure_record['path'];structure=study.read(structure_path)
        structure['scoring_context']['optional_subject_scoring']=[{'subject_id':subject['subject_id'],'scored':False,'rule_id':'OPTIONAL-SYNTHETIC'}]
        structure_path.write_text(json.dumps(structure));structure_record.update(sha256=study.file_digest(structure_path),artifact_id=baseline.completion.state_cli.artifact_id(structure_record['path'],study.file_digest(structure_path)))
        f.state_path.write_text(json.dumps(state))
        scored=command('score','score','--state',f.state_path,'--output-dir','scoring-optional')
        self.assertEqual(0,scored.returncode,scored.stdout+scored.stderr)
        reported=command('score','build-report','--state',f.state_path)
        self.assertEqual(0,reported.returncode,reported.stdout+reported.stderr)
        report=study.read(f.root/'scoring-optional/web-report.v13.json')
        coverage=next(r for r in report['presentation_summary']['metrics'] if r['metric_id']=='weighted_concept_access_partial_credit')
        self.assertEqual('1',coverage['denominator_weight'])

    def test_public_v8_four_family_migration_then_decision_v3_adoption(self):
        f=baseline.prepare_v10(self)
        template=f.root/'release/public-v7-policy-template.json'
        generated=command('study','policy-template','--input',f.args.release_policy,'--output',template,'--from-source-policy')
        self.assertEqual(0,generated.returncode,generated.stdout+generated.stderr)
        f.args.study_policy=str(template)
        f.lock['policy_semantic_sha256']=study.policy_semantic_hash(study.read(template))
        baseline.rebind(f)
        arguments=['study','migrate-benchmark']
        for name,value in vars(f.args).items():
            if value is not None:arguments += ['--'+name.replace('_','-'),value]
        migrated=command(*arguments)
        self.assertEqual(0,migrated.returncode,migrated.stdout+migrated.stderr)
        pending=study.read(f.state_path)
        self.assertEqual('subject-index-evaluation-state-v9',pending['schema_version'])
        self.assertNotIn('execution_compatibility',pending)
        blocked=command('study','preflight','--state',f.state_path)
        self.assertNotEqual(0,blocked.returncode);self.assertIn('explicit compatibility adoption',blocked.stdout+blocked.stderr)
        approval,release=compatibility(f)
        adopted=command('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','semantic-execution')
        self.assertEqual(0,adopted.returncode,adopted.stdout+adopted.stderr)
        current=study.read(f.state_path)
        self.assertEqual(CONTRACT,study.read(f.root/current['execution_compatibility']['approval']['path'])['execution_contract_id'])
        ready=command('study','preflight','--state',f.state_path)
        self.assertEqual(0,ready.returncode,ready.stdout+ready.stderr)

    def test_completed_semantic_architecture_review_is_neutral_and_complete(self):
        code='''
import json
from runtime_profile import select_v10_semantic
select_v10_semantic()
from test_structure_audit import audit,component,triggered_review,SCHEMAS
from schema_validation import schema_errors
from structure_audit import materialize_structure_records,validate_structure_audit_semantics
from scoring_core import NODE_CREDIT,node_component
d=audit();d['schema_version']='structure-audit-v6';r=triggered_review();r.update(review_status='semantic_unresolved',meaningful_subheadings_or_access_routes=None,evidence_ids=['EVID-ARCH-0001'],semantic_uncertainties=[{'field':'meaningful_subheadings_or_access_routes','reason_category':'unresolved_scope','evidence_ids':['EVID-ARCH-0001']}]);d['locator_architecture'].update(triggered_path_ids=['PATH-00001'],triggered_reviews=[r]);h=component('semantic_unresolved');h.update(evidence_ids=['EVID-ARCH-0001'],causal_findings=[],semantic_uncertainties=r['semantic_uncertainties']);d['node_judgments']=[{'node_id':'NODE-00001','component_judgments':{'conceptual_stance_fidelity':component('passes'),'heading_access_architecture':h,'mechanics_consistency':component('passes')},'summary':'Semantic architecture premise unresolved.','confidence':'high','evidence_ids':['EVID-ARCH-0001']}];assert not schema_errors(d,'structure-audit-v6.schema.json',profile='v10s');validate_structure_audit_semantics(d);nodes,_,missing,_=materialize_structure_records(d);_,unknown,_,_,denom=node_component({'nodes':nodes,'node_not_measured':missing,'node_original':3},'heading_access_architecture',NODE_CREDIT,'heading_access_architecture');assert len(unknown)==1 and denom['semantic_unresolved']==1 and denom['uninspectable']==0
'''
        result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],env={**__import__('os').environ,'PYTHONPATH':'tests:scripts'},capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stdout+result.stderr)

    def test_native_semantic_parent_axes_are_typed_and_neutral(self):
        case=baseline.V10RuntimeTests();self.addCleanup(case.doCleanups);f=case.complete_fixture()
        state=study.read(f.state_path)
        audit_record=next(r for r in state['artifacts'] if r.get('schema_version')=='missing-access-audit-v1')
        audit_path=f.root/audit_record['path'];audit=study.read(audit_path);audit['schema_version']='missing-access-audit-v2'
        subject=audit['subject_judgments'][0]
        subject.update(coverage=None,stance_preserved=None,realistic_first_lookup_success=None,axis_resolution={'coverage':'unresolved','stance_preserved':'unresolved','realistic_first_lookup_success':'unresolved'},semantic_uncertainties=[{'field':field,'reason_category':'unresolved_relationship','rationale':f'PRIVATE-PARENT-TEST {field} depends on inspected unresolved semantics.','evidence_ids':subject['evidence_ids'],'locator_ids':['LOC-001']} for field in ('coverage','stance_preserved','realistic_first_lookup_success')])
        task=audit['reader_task_results'][0]
        task.update(result=None,axis_resolution={'result':'unresolved'},semantic_uncertainties=[{'field':'result','reason_category':'dependent_semantic_uncertainty','rationale':'PRIVATE-PARENT-TEST Task result depends on unresolved parent coverage.','evidence_ids':task['evidence_ids'],'locator_ids':['LOC-001']}])
        audit['completion']['semantic_unresolved']=1;audit['reader_task_completion']['semantic_unresolved']=1
        audit_path.write_text(json.dumps(audit));audit_record.update(sha256=study.file_digest(audit_path),schema_version='missing-access-audit-v2')
        audit_record['artifact_id']=baseline.completion.state_cli.artifact_id(audit_record['path'],audit_record['sha256'])
        review_record=next(r for r in state['artifacts'] if r.get('artifact_type')=='candidate_benchmark_access_review')
        review_path=f.root/review_record['path'];review=study.read(review_path);review['audit_bindings']=[{'path':audit_record['path'],'sha256':audit_record['sha256']}]
        for row in review['requirements']:
            row.update(disposition='unresolved',factual_status='partially_satisfied',resulting_parent_judgment=deepcopy(subject),judgment_fields=['coverage'])
        review_path.write_text(json.dumps(review));review_record['sha256']=study.file_digest(review_path);review_record['artifact_id']=baseline.completion.state_cli.artifact_id(review_record['path'],review_record['sha256'])
        f.state_path.write_text(json.dumps(state))
        approval,release=compatibility(f);adopted=command('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','semantic-execution')
        self.assertEqual(0,adopted.returncode,adopted.stdout+adopted.stderr)
        output=command('score','score','--state',f.state_path,'--output-dir','scoring-semantic')
        self.assertEqual(0,output.returncode,output.stdout+output.stderr)
        calculation=study.read(f.root/'scoring-semantic/dimension-calculations.v9.json');dimensions={r['dimension_id']:r for r in calculation['dimensions']}
        coverage=dimensions['meaningful_coverage']['denominators']['components'][0];tasks=dimensions['findability_navigation']['denominators']['components'][0]
        self.assertEqual(1,coverage['semantic_unresolved']);self.assertEqual(0,coverage['uninspectable'])
        self.assertEqual(1,tasks['semantic_unresolved']);self.assertEqual(0,tasks['uninspectable'])
        result=study.read(f.root/'scoring-semantic/evaluation-result.v15.json');self.assertEqual('indeterminate',result['authoritative_evaluation']['status'])
        parent_blocker=next(row for row in result['gate_assessment']['blockers'] if row['blocker_id']=='GATE-ASSESSMENT-ACCESS-PARENT-UNCERTAIN')
        self.assertEqual(['coverage','realistic_first_lookup_success','result','stance_preserved'],parent_blocker['semantic_unknown_axes'])
        report=command('score','build-report','--state',f.state_path);self.assertEqual(0,report.returncode,report.stdout+report.stderr)
        public=''.join(p.read_text() for p in (f.root/'scoring-semantic/v10-canonical-projection').rglob('*.json'))
        self.assertNotIn('PRIVATE-PARENT-TEST',public);self.assertIn('semantically unresolved after inspection',public.lower())

    def test_decision_v1_state_adopts_decision_v3_policy_and_preserves_source(self):
        case=baseline.V10RuntimeTests();self.addCleanup(case.doCleanups);f=case.complete_fixture()
        before=study.read(f.state_path);prior=study.read(f.root/'scoring-v10/dimension-calculations.v8.json')
        prior_policy_record=next(r for r in before['artifacts'] if r['stage']=='define_policy')
        self.assertEqual('subject-index-evaluation-policy-v6',prior_policy_record['schema_version'])
        active_template=f.root/'decision-v3-policy-template.json'
        generated=command('study','policy-template','--input',f.args.release_policy,'--output',active_template,'--from-source-policy')
        self.assertEqual(0,generated.returncode,generated.stdout+generated.stderr)
        self.assertEqual('subject-index-evaluation-policy-v7',study.read(active_template)['policy_semantic_content']['schema_version'])
        approval,release=compatibility(f)
        adopted=command('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','semantic-execution')
        self.assertEqual(0,adopted.returncode,adopted.stdout+adopted.stderr)
        after=study.read(f.state_path)
        self.assertEqual('subject-index-evaluation-state-v9',after['schema_version'])
        self.assertEqual(CONTRACT,after['execution_compatibility'] and study.read(f.root/'semantic-execution/compatibility.json')['execution_contract_id'])
        for key in ('candidate','source','study_comparison','configuration'):self.assertEqual(before[key],after[key])
        self.assertEqual(before,study.read(f.root/'semantic-execution/previous-state.json'))
        output=command('score','score','--state',f.state_path,'--output-dir','scoring-semantic')
        self.assertEqual(0,output.returncode,output.stdout+output.stderr)
        current=study.read(f.root/'scoring-semantic/dimension-calculations.v9.json')
        self.assertEqual('subject-index-dimension-calculations-v9',current['schema_version'])
        self.assertEqual(prior['overall_percentage'],current['overall_percentage'])
        self.assertEqual(prior['dimensions'],current['dimensions'])
        self.assertNotEqual(prior['calculation_id'],current['calculation_id'])
        self.assertEqual(CONSTITUENTS,current['execution_contract']['contract_constituents'])
        baseline_check=baseline.v10('study','preflight','--state',f.state_path)
        self.assertNotEqual(0,baseline_check.returncode)
        old=study.read(f.root/'scoring-v10/evaluation-result.v14.json')['comparison_key']['study_identity']
        new=study.read(f.root/'scoring-semantic/evaluation-result.v15.json')['comparison_key']['study_identity']
        with self.assertRaisesRegex(ValueError,'cannot mix'):study.compare_identities([old,new])
        report=command('score','build-report','--state',f.state_path)
        self.assertEqual(0,report.returncode,report.stdout+report.stderr)

    def test_native_semantic_known_treatment_unknown_fit_and_keep(self):
        self.native_semantic_case()

    def test_native_semantic_unknown_treatment_known_fit_and_keep(self):
        self.native_semantic_case(unknown_treatment=True)

    def test_native_known_nonkeep_unresolved_subtype(self):
        self.native_semantic_case(aggregate=True)

    def test_native_semantic_without_independent_gate(self):
        self.native_semantic_case(unknown_treatment=True,broken_reference=False)

    def native_semantic_case(self,unknown_treatment=False,aggregate=False,broken_reference=True,source_fixture=None,evaluation_id=None,runtime_revision=None):
        case=baseline.V10RuntimeTests();self.addCleanup(case.doCleanups);f=case.complete_fixture(broken_reference=broken_reference,source_fixture=source_fixture,evaluation_id=evaluation_id)
        # Synthetic fixture surgery prepares one newly audited row. Native raw
        # schema, ledger, scoring, result and projection validators all run.
        state=study.read(f.state_path)
        for record in state['artifacts']:
            if record.get('schema_version')!='locator-audit-v2':continue
            path=f.root/record['path'];audit=study.read(path);audit['schema_version']='locator-audit-v3'
            row=audit['judgments'][0];row.update(complete_path_fit=None,judgment='semantic_unresolved')
            row['axis_resolution']={'treatment':'known','complete_path_fit':'unresolved','keep':'unresolved','inspection_completed':True,'reason_category':'unresolved_relationship','rationale':'PRIVATE-SEMANTIC-TEST Synthetic inspected relationship remains unresolved.'}
            if unknown_treatment:
                row.update(treatment_class=None,complete_path_fit='exact_fit',judgment='supported')
                row['axis_resolution'].update(treatment='unresolved',complete_path_fit='known',keep='known')
            if aggregate:
                row.update(treatment_class='passing_mention',complete_path_fit=None,judgment='not_kept_subtype_unresolved',keep_decision='not_kept')
                row['axis_resolution'].update(treatment='known',complete_path_fit='unresolved',keep='known',judgment_subtype='unresolved')
            path.write_text(json.dumps(audit));record['sha256']=study.file_digest(path);record['schema_version']=audit['schema_version']
            record['artifact_id']=baseline.completion.state_cli.artifact_id(record['path'],record['sha256'])
        f.state_path.write_text(json.dumps(state))
        approval,release=compatibility(f,runtime_revision)
        adopted=command('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','semantic-execution')
        self.assertEqual(0,adopted.returncode,adopted.stdout+adopted.stderr)
        output=command('score','score','--state',f.state_path,'--output-dir','scoring-semantic')
        self.assertEqual(0,output.returncode,output.stdout+output.stderr)
        current=study.read(f.root/'scoring-semantic/dimension-calculations.v9.json')
        dimensions={r['dimension_id']:r for r in current['dimensions']}
        provenance=dimensions['page_reference_reliability']['reliability_provenance']
        if unknown_treatment:
            self.assertIsNone(provenance['mean_treatment_score']);self.assertEqual('1',provenance['mean_fit_score'])
            self.assertEqual(0,provenance['semantic_unresolved_keep_count'])
            self.assertIsNone(dimensions['editorial_selectivity']['substantive_selectivity_percentage'])
        elif aggregate:
            self.assertEqual('0.25',provenance['mean_treatment_score']);self.assertEqual('0',provenance['keep_precision'])
            self.assertEqual(0,provenance['semantic_unresolved_keep_count'])
            self.assertEqual({'lower':'0','central':'0','upper':'0'},provenance['keep_precision_uncertainty'])
        else:
            self.assertEqual('0.7',provenance['mean_treatment_score']);self.assertIsNone(provenance['mean_fit_score'])
            self.assertEqual(1,provenance['semantic_unresolved_keep_count'])
        self.assertEqual(0,provenance['uninspectable_locator_count'])
        from schema_validation import schema_errors
        self.assertEqual([],schema_errors(current,'dimension-calculations-v9.schema.json',profile='v10s'))
        tampered=deepcopy(current);utility=tampered['dimensions'][3]['reliability_provenance']['locator_utility_assignments'][0]
        utility['rating_credit']='1' if utility['rating_credit']!='1' else '0'
        self.assertTrue(schema_errors(tampered,'dimension-calculations-v9.schema.json',profile='v10s'))
        result=study.read(f.root/'scoring-semantic/evaluation-result.v15.json')
        self.assertEqual('indeterminate',result['authoritative_evaluation']['status'])
        self.assertEqual('not_ready' if broken_reference else 'indeterminate',result['method_readiness']['status'])
        if aggregate:
            blocker=next(r for r in result['gate_assessment']['blockers'] if 'semantic_unknown_axes' in r)
            self.assertEqual(['complete_path_fit','judgment_subtype'],blocker['semantic_unknown_axes'])
        report=command('score','build-report','--state',f.state_path)
        self.assertEqual(0,report.returncode,report.stdout+report.stderr)
        public=''.join(p.read_text() for p in (f.root/'scoring-semantic/v10-canonical-projection').rglob('*.json'))
        self.assertNotIn('PRIVATE-SEMANTIC-TEST',public)
        self.assertIn('Semantically unresolved after inspection',public)
        self.assertTrue(result['audit_scope']['complete'])

        return f

    def test_adoption_rejects_wrong_bindings_without_mutation(self):
        case=baseline.V10RuntimeTests();self.addCleanup(case.doCleanups);f=case.complete_fixture()
        approval,release=compatibility(f);original=study.read(approval);before=f.state_path.read_bytes()
        for field,value in [('baseline_runtime_commit','2'*40),('runtime_payload_sha256','0'*64),('common_lock_sha256','0'*64),('source_release_file_sha256','0'*64),('contract_constituents',{}),('approved_at','2999-01-01T00:00:00Z')]:
            bad=deepcopy(original);bad[field]=value;bad['compatibility_sha256']=study.digest({k:v for k,v in bad.items() if k!='compatibility_sha256'});approval.write_text(json.dumps(bad))
            outcome=command('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','semantic-execution')
            self.assertNotEqual(0,outcome.returncode,field);self.assertEqual(before,f.state_path.read_bytes());self.assertFalse((f.root/'semantic-execution').exists())
        approval.write_text(json.dumps(original))
        outcome=command('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','semantic-execution')
        self.assertEqual(0,outcome.returncode,outcome.stdout+outcome.stderr)
        adopted=f.state_path.read_bytes()
        again=command('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','second-adoption')
        self.assertNotEqual(0,again.returncode);self.assertEqual(adopted,f.state_path.read_bytes());self.assertFalse((f.root/'second-adoption').exists())

if __name__=='__main__':unittest.main()
