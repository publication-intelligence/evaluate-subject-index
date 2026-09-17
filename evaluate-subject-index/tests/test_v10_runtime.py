"""V10 semantic migration and separated outcomes; real preserved V8 source proof."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_v8_completion as completion
from test_study_comparison import StudyFixture, self_hash
import study_comparison as study
from runtime_profile import V10_IDENTITIES
from v10_migration import policy_content, SOURCE_IDENTITIES
from v10_access import population, preserved_evidence_rows, apply_overlay

SCRIPTS = completion.SCRIPTS


def v10(*args):
    return subprocess.run([sys.executable,str(SCRIPTS/'v10_cli.py'),*map(str,args)],capture_output=True,text=True)


def rebind(f):
    self_hash(f.lock,'lock_sha256');Path(f.args.study_lock).write_text(json.dumps(f.lock))
    approval=study.read(f.args.approval)
    approval.update(target_benchmark_sha256=f.lock['release']['benchmark_sha256'],previous_state_sha256=study.file_digest(f.state_path),study_lock_sha256=f.lock['lock_sha256'],target_policy_semantic_sha256=f.lock['policy_semantic_sha256'],study_policy_template_sha256=study.file_digest(f.args.study_policy))
    Path(f.args.approval).write_text(json.dumps(approval))


def prepare_v10(case, *, evaluation_id=None, amendment_style="facet"):
    f=StudyFixture(case,evaluation_id=evaluation_id);case.addCleanup(f.f.tearDown)
    f.current_source_release(revised=True)
    f.args.release_policy=str(Path(f.args.release_state).parent/'evaluation-policy.json')
    source_policy=study.read(f.args.release_policy)
    template={'schema_version':'subject-index-study-policy-template-v1','policy_semantic_content':policy_content(source_policy)}
    self_hash(template,'template_sha256');f.args.study_policy=str(f.f.write('release/v10-policy-template.json',template))
    for key in ('schema_version','policy_profile','rubric_version','calculation_profile'):f.lock[key]=V10_IDENTITIES[f.lock[key]]
    f.lock['policy_semantic_sha256']=study.policy_semantic_hash(template)
    f.lock['source_methodology']={**SOURCE_IDENTITIES,'source_policy_sha256':source_policy['policy_sha256'],'source_policy_file_sha256':study.file_digest(f.args.release_policy)}
    f.lock['source_benchmark_semantic_sha256']=f.lock['benchmark_semantic_sha256']
    base=study.read(f.args.release_benchmark)
    overlay={'schema_version':'subject-index-benchmark-access-overlay-v10','overlay_id':'ACCESS-SYNTHETIC','author_id':'AUTHOR-SYNTHETIC','prepared_at':'2026-09-16T00:00:00Z','candidate_seen':False,'source_scope':deepcopy(f.lock['source_scope']),'source_methodology':deepcopy(f.lock['source_methodology']),'base_benchmark_sha256':base['benchmark_sha256'],'base_benchmark_file_sha256':study.file_digest(f.args.release_benchmark),'base_review_file_sha256':study.file_digest(f.args.release_review),'before_population':population(base),'after_population':population(base),'deltas':[]}
    self_hash(overlay,'overlay_sha256');overlay_path=f.f.write('release/access-overlay.json',overlay)
    review={'schema_version':'subject-index-benchmark-access-review-v10','reviewer_id':'REVIEWER-SYNTHETIC','reviewed_at':'2026-09-16T00:01:00Z','candidate_seen':False,'decision':'approved','overlay_sha256':overlay['overlay_sha256'],'overlay_file_sha256':study.file_digest(overlay_path),'population_sha256':study.digest({'before':overlay['before_population'],'after':overlay['after_population']}),'reviewed_delta_ids':[],'source_evidence_verified':True,'no_source_scope_change':True,'rationale':'Synthetic independent no-change access review.'}
    review_path=f.f.write('release/access-review.json',review)
    f.lock['benchmark_access']={'overlay':{'path':'access-overlay.json','sha256':study.file_digest(overlay_path)},'review':{'path':'access-review.json','sha256':study.file_digest(review_path)},'overlay_sha256':overlay['overlay_sha256'],'effective_benchmark_semantic_sha256':f.lock['benchmark_semantic_sha256'],'frozen_at':'2026-09-16T00:02:00Z'}
    rebind(f)
    parent=deepcopy(base['subjects'][0]);rows=preserved_evidence_rows(parent)
    original_parent=deepcopy(parent)
    parent['required_access_facets']=[{'facet_id':'FACET-SYNTHETIC','label':'Synthetic lookup','meaning':'Preserved source-supported access.','acceptable_access':['Alpha'],'document_pages':[rows[0]['document_page']],'independently_weighted':False}]
    set_deltas(f,[{'delta_id':'DELTA-SYNTHETIC','clause_ids':['IPDF-VOC-02'],'family':'subjects','item_id':parent['subject_id'],'operation':'update','weight_treatment':'unweighted_facets','reason':'Preserved evidence warrants an explicit lookup facet.','distinct_obligation_rationale':'','evidence_ids':[row['evidence_id'] for row in rows],'replacement':parent}])
    if amendment_style=='none':set_deltas(f,[])
    elif amendment_style=='terms':
        original_parent['acceptable_access'].append('Synthetic synonym')
        delta=study.read(f.root/'release/access-overlay.json')['deltas'][0]
        delta.update(delta_id='DELTA-TERM',weight_treatment='updated_parent',replacement=original_parent)
        set_deltas(f,[delta])
    elif amendment_style=='question':
        task=deepcopy(base['reader_tasks'][0]);task['question']+=' Use a source-supported equivalent lookup term.'
        delta=study.read(f.root/'release/access-overlay.json')['deltas'][0]
        delta.update(delta_id='DELTA-QUESTION',family='reader_tasks',item_id=task['task_id'],weight_treatment='updated_parent',replacement=task)
        set_deltas(f,[delta])
    return f


def set_deltas(f,deltas):
    op=f.root/'release/access-overlay.json';rp=f.root/'release/access-review.json'
    overlay=study.read(op);review=study.read(rp);base=study.read(f.args.release_benchmark)
    effective=deepcopy(base)
    for delta in deltas:
        rows=effective[delta['family']];key='subject_id' if delta['family']=='subjects' else 'task_id'
        if delta['operation']=='add':rows.append(delta['replacement'])
        elif delta['operation']=='retire':rows[:]=[row for row in rows if row[key]!=delta['item_id']]
        else:rows[:]=[delta['replacement'] if row[key]==delta['item_id'] else row for row in rows]
    overlay.update(deltas=deltas,after_population=population(effective));self_hash(overlay,'overlay_sha256');op.write_text(json.dumps(overlay))
    review.update(overlay_sha256=overlay['overlay_sha256'],overlay_file_sha256=study.file_digest(op),reviewed_delta_ids=[row['delta_id'] for row in deltas],population_sha256=study.digest({'before':overlay['before_population'],'after':overlay['after_population']}));rp.write_text(json.dumps(review))
    f.lock['benchmark_semantic_sha256']=study.benchmark_semantic_hash(effective)
    f.lock['benchmark_access'].update(overlay={'path':op.name,'sha256':study.file_digest(op)},review={'path':rp.name,'sha256':study.file_digest(rp)},overlay_sha256=overlay['overlay_sha256'],effective_benchmark_semantic_sha256=f.lock['benchmark_semantic_sha256'])
    rebind(f)


def migrate(f):
    args=['study','migrate-benchmark']
    for name,value in vars(f.args).items():
        if value is not None:args+=['--'+name.replace('_','-'),value]
    return v10(*args)


def create_access_review(f, *, unresolved=False):
    from v10_candidate_access import requirements,bound_amendment
    state=study.read(f.state_path);benchmark=study.read(f.root/'migration/selected-benchmark.json')
    lock=study.read(f.root/state['study_comparison']['lock']['path'])
    records=[r for r in state['artifacts'] if r['stage']=='missing_access_audit' and r.get('schema_version')=='missing-access-audit-v1']
    parents={}
    for r in records:
        audit=study.read(f.root/r['path'])
        parents.update({('subject',row['subject_id']):row for row in audit['subject_judgments']})
        parents.update({('reader_task',row['task_id']):row for row in audit['reader_task_results']})
    rows=[]
    expected=requirements(benchmark,bound_amendment(state,f.state_path,lock))
    if not expected:return None
    for (kind,parent,requirement_kind,identity),sha in expected.items():
        rows.append({'parent_kind':kind,'parent_id':parent,'requirement_kind':requirement_kind,'requirement_id':identity,'requirement_sha256':sha,'disposition':'unresolved' if unresolved else 'reviewed','factual_status':'uninspectable' if unresolved else 'satisfied','judgment_fields':['coverage'] if kind=='subject' else ['result'],'tested_path_ids':['PATH-001'],'evidence_ids':['EVID-TREAT-001'],'structure_finding_ids':['NODE-001'],'rationale':'Synthetic factual inspection of the required access, existing parent judgment and structure evidence.','resulting_parent_judgment':deepcopy(parents[(kind,parent)])})
    receipt={'schema_version':'subject-index-v10-candidate-access-review-v1','review_id':'ACCESS-REVIEW-SYNTHETIC','reviewer_id':'REVIEWER-SYNTHETIC','reviewed_at':'2026-09-16T00:03:00Z','candidate_seen':True,'evaluation_id':state['evaluation_id'],'candidate_sha256':state['candidate']['candidate_sha256'],'benchmark_sha256':benchmark['benchmark_sha256'],'study_lock_sha256':lock['lock_sha256'],'benchmark_access_sha256':lock['benchmark_access']['overlay_sha256'],'audit_bindings':[{'path':r['path'],'sha256':r['sha256']} for r in records],'structure_binding':{'path':f.f.structure_path.relative_to(f.root).as_posix(),'sha256':study.file_digest(f.f.structure_path)},'requirements':rows}
    path=f.f.write('candidate/v10-access-review.json',receipt)
    result=v10('access-review','--state',f.state_path,'--input',path)
    if result.returncode:raise AssertionError(result.stdout+result.stderr)
    return path


def add_broken_reference(f):
    from structure_audit import id_set_hash
    from test_wrong_destination_gates import evidence
    f.f.add_cross_reference_record_for_existing_heading()
    structure=study.read(f.f.structure_path)
    structure['candidate_denominator'].update(cross_reference_ids=['XREF-001'],cross_reference_count=1,cross_reference_id_set_sha256=id_set_hash(['XREF-001']))
    structure['metrics']['cross_references']=1
    structure['scoring_context']['cross_reference_applicability']={'status':'applicable','basis_code':'delivered_references','delivered_reference_count':1,'warranted_reference_obligation_count':0,'warranted_reference_obligation_ids':[],'reference_defect_ids':[]}
    row=evidence()[0]['cross_reference_judgments'][0];row['reference_id']='XREF-001';row['target_resolution']['target_display']='Missing target'
    structure['cross_reference_judgments']=[row];f.f.structure_path.write_text(json.dumps(structure))
    state=study.read(f.state_path)
    for record in state['artifacts']:
        kind=record['artifact_type']
        if kind not in {'candidate_index','item_inventory','structure_audit'}:continue
        path=f.root/record['path'];document=study.read(path)
        if kind=='candidate_index':document['records'][-1]['cross_references'][0].update(target='Missing target',target_path_id=None)
        elif kind=='item_inventory':document['cross_references'][0].update(target_display='Missing target',target_path_id=None)
        path.write_text(json.dumps(document));record['sha256']=study.file_digest(path);record['artifact_id']=completion.state_cli.artifact_id(record['path'],record['sha256'])
        if kind=='candidate_index':state['candidate']['normalized_sha256']=record['sha256']
    f.state_path.write_text(json.dumps(state))


class V10RuntimeTests(unittest.TestCase):
    def complete_fixture(self, *, evaluation_id=None, source_fixture=None, broken_reference=False, unresolved_access=False, amendment_style="facet"):
        f=prepare_v10(self,evaluation_id=evaluation_id,amendment_style=amendment_style)
        if source_fixture is not None:
            for key in ('release_policy','release_state','release_draft','release_review','release_benchmark','release_descriptor','release_review_inventory','study_lock','study_policy'):
                setattr(f.args,key,getattr(source_fixture.args,key))
            f.lock=deepcopy(source_fixture.lock)
            rebind(f)
        if broken_reference:
            add_broken_reference(f)
        before={Path(getattr(f.args,k)):Path(getattr(f.args,k)).read_bytes() for k in ('release_policy','release_state','release_draft','release_review','release_benchmark')}
        prior=study.read(f.state_path)
        result=f.f.run_cli('score','--state',str(f.state_path));self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        original=study.read(f.root/'scoring/dimension-calculations.v6.json')
        rebind(f);migrated=migrate(f);self.assertEqual(0,migrated.returncode,migrated.stdout+migrated.stderr)
        state=study.read(f.state_path);policy=study.read(f.root/'migration/selected-policy.json');benchmark=study.read(f.root/'migration/selected-benchmark.json')
        self.assertEqual('subject-index-evaluation-state-v8',state['schema_version'])
        self.assertTrue(state['study_comparison']['methodology_migration']['scoring_semantics_changed'])
        for stage in ('locator_chunk_preparation','locator_audit','missing_access_audit','structure_audit','scoring','web_report'):
            self.assertEqual('not_started',state['stages'][stage]['status'])
        # Re-create synthetic audit inputs, never transfer a production ledger.
        for path in (f.root/'candidate').glob('*.json'):
            path.write_text(path.read_text().replace(f.policy['policy_sha256'],policy['policy_sha256']).replace(prior['candidate']['benchmark_sha256'],benchmark['benchmark_sha256']))
        f.f.structure_path.write_text(f.f.structure_path.read_text().replace(f.policy['policy_sha256'],policy['policy_sha256']))
        for stage in ('locator_chunk_preparation','locator_audit','missing_access_audit'):
            state['stages'][stage]=deepcopy(prior['stages'][stage])
            state['artifacts'] += [f.f.record(f.root/r['path'],stage,r['artifact_type'],r.get('schema_version')) for r in prior['artifacts'] if r['stage']==stage]
        f.state_path.write_text(json.dumps(state))
        create_access_review(f,unresolved=unresolved_access)
        for command,extra in [('register-structure',['--input',f.f.structure_path]),('score',['--output-dir','scoring-v10']),('build-report',[])]:
            result=v10('score',command,'--state',f.state_path,*extra);self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        calculation=study.read(f.root/'scoring-v10/dimension-calculations.v8.json')
        self.assertEqual(original['overall_percentage'],calculation['overall_percentage'])
        self.assertEqual(original['final_rounding'],calculation['final_rounding'])
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.completed_fixture=f;return f

    def test_complete_native_v10_and_portable_checkpoint(self):
        f=self.complete_fixture()
        projection=study.read(f.root/'scoring-v10/v10-canonical-projection/projection.v1.json')
        self.assertEqual('ready',projection['method_readiness']['status'])
        self.assertEqual({'status':'authoritative'},projection['authoritative_evaluation'])
        self.assertEqual({'status':'not_recorded'},projection['human_release_decision'])
        subjects=study.read(f.root/'scoring-v10/v10-canonical-projection/data/source-subjects.v1.json')
        self.assertIn('FACET-SYNTHETIC',json.dumps(subjects))
        from v10_release import machine_facts, validate_decision
        result_path=f.root/'scoring-v10/evaluation-result.v14.json';result=study.read(result_path)
        decision={'schema_version':'subject-index-human-release-decision-v10','decision_id':'DECISION-SYNTHETIC','evaluation_id':result['evaluation_id'],'result_file_sha256':study.file_digest(result_path),'machine_facts_sha256':study.digest(machine_facts(result)),'status':'approved','decided_by':'REVIEWER-SYNTHETIC','decided_at':'2026-09-16T00:00:00Z','authorization_reference':'Synthetic test only','rationale':'Synthetic release decision.','acknowledged_gate_ids':[],'machine_outcomes_changed':False}
        before=result_path.read_bytes();validate_decision(decision,result,study.file_digest(result_path))
        decision['machine_facts_sha256']='0'*64
        with self.assertRaises(ValueError):validate_decision(decision,result,study.file_digest(result_path))
        self.assertEqual(before,result_path.read_bytes())
        from schema_validation import schema_errors
        for bad_validity in (None,{}, {'status':'valid','blockers':[{'blocker_id':'VALIDITY-UNINSPECTABLE'}],'used_as_publication_gate':False}, {'status':'valid','blockers':[{'blocker_id':'VALIDITY-UNINSPECTABLE','outcome':'indeterminate','count':1,'denominator':1,'rate':'1','threshold':'0.01','reason':'Synthetic blocker contradicts status.'}],'used_as_publication_gate':False}):
            invalid=deepcopy(result)
            if bad_validity is None:invalid.pop('evaluation_validity')
            else:invalid['evaluation_validity']=bad_validity
            self.assertTrue(schema_errors(invalid,'evaluation-result-v14.schema.json',profile='v10'))
        invalid=deepcopy(result);invalid['gate_assessment']={'status':'sufficient','blockers':[{'blocker_id':'GATE-ASSESSMENT-TEST','affected_item_ids':['LOC-001'],'reason':'Synthetic blocker contradicts sufficiency.'}]}
        self.assertTrue(schema_errors(invalid,'evaluation-result-v14.schema.json',profile='v10'))
        bundle=f.root/'exports/v10.zip'
        result=v10('bundle','checkpoint','--state',f.state_path,'--output',bundle);self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        result=v10('bundle','import-bundle','--input',bundle,'--output-dir',f.root/'restored');self.assertEqual(0,result.returncode,result.stdout+result.stderr)
        result=v10('study','preflight','--state',f.root/'restored/evaluation-state.json','--require-density');self.assertEqual(0,result.returncode,result.stdout+result.stderr)

    def test_confirmed_gate_native_report_and_separate_deviation(self):
        f=self.complete_fixture(broken_reference=True)
        path=f.root/'scoring-v10/evaluation-result.v14.json';result=study.read(path)
        self.assertEqual('not_ready',result['method_readiness']['status'])
        self.assertEqual(['GATE-BROKEN-REFERENCE'],result['method_readiness']['triggered_gate_ids'])
        from v10_release import validate_decision,machine_facts
        decision={'schema_version':'subject-index-human-release-decision-v10','decision_id':'DECISION-DEVIATION','evaluation_id':result['evaluation_id'],'result_file_sha256':study.file_digest(path),'machine_facts_sha256':study.digest(machine_facts(result)),'status':'approved_with_deviation','decided_by':'SYNTHETIC','decided_at':'2026-09-16T00:00:00Z','authorization_reference':'Synthetic only','rationale':'Explicit deviation leaves the gate reported.','acknowledged_gate_ids':['GATE-BROKEN-REFERENCE'],'machine_outcomes_changed':False}
        before=path.read_bytes();validate_decision(decision,result,study.file_digest(path));self.assertEqual(before,path.read_bytes())
        decision['status']='approved'
        with self.assertRaises(ValueError):validate_decision(decision,result,study.file_digest(path))

    def test_factual_access_review_exact_set_bindings_and_parent_agreement(self):
        from v10_candidate_access import validate_review,requirements
        f=self.complete_fixture();state=study.read(f.state_path);benchmark=study.read(f.root/'migration/selected-benchmark.json');lock=study.read(f.root/state['study_comparison']['lock']['path'])
        receipt=study.read(f.root/'candidate/v10-access-review.json')
        before=f.state_path.read_bytes()
        for mutation in ('omitted','omit_delta','duplicate','foreign','stale_content','old_audit','old_amendment','parent_disagrees','foreign_path','foreign_evidence','unsatisfied','partial'):
            with self.subTest(mutation=mutation):
                bad=deepcopy(receipt)
                if mutation=='omitted':bad['requirements']=[]
                elif mutation=='omit_delta':bad['requirements']=[r for r in bad['requirements'] if r['requirement_kind']!='amendment_delta']
                elif mutation=='duplicate':bad['requirements'].append(deepcopy(bad['requirements'][0]))
                elif mutation=='foreign':bad['requirements'][0]['parent_id']='SUBJ-FOREIGN'
                elif mutation=='stale_content':bad['requirements'][0]['requirement_sha256']='0'*64
                elif mutation=='old_audit':bad['audit_bindings'][0]['sha256']='0'*64
                elif mutation=='old_amendment':bad['benchmark_access_sha256']='0'*64
                elif mutation=='parent_disagrees':bad['requirements'][0]['resulting_parent_judgment']['coverage']='missing'
                elif mutation=='foreign_path':bad['requirements'][0]['tested_path_ids']=['PATH-FOREIGN']
                elif mutation=='foreign_evidence':bad['requirements'][0]['evidence_ids']=['EVID-FOREIGN']
                else:bad['requirements'][0]['factual_status']='not_satisfied' if mutation=='unsatisfied' else 'partially_satisfied'
                with self.assertRaises(ValueError):validate_review(bad,state=state,state_path=f.state_path,benchmark=benchmark,lock=lock,structure_path=f.f.structure_path)
        self.assertEqual(before,f.state_path.read_bytes())
        missing=deepcopy(state);missing['artifacts']=[r for r in missing['artifacts'] if r.get('artifact_type')!='candidate_benchmark_access_review']
        from v10_candidate_access import bound_review
        with self.assertRaises(ValueError):bound_review(missing,f.state_path,benchmark,lock)
        missing_path=f.root/'state-without-access-review.json';missing_path.write_text(json.dumps(missing))
        rejected=v10('study','preflight','--state',missing_path,'--require-density')
        self.assertNotEqual(0,rejected.returncode);self.assertIn('GATE-ASSESSMENT-ACCESS-REVIEW',rejected.stdout)
        empty=deepcopy(benchmark)
        for row in empty['subjects']:row.pop('required_access_facets',None)
        self.assertEqual({},requirements(empty))
        amended=deepcopy(benchmark);amended['subjects'][0]['access_scope_rule']='A new frozen scope requirement.'
        self.assertEqual(len(requirements(benchmark))+1,len(requirements(amended)))
        with self.assertRaises(ValueError):validate_review(receipt,state=state,state_path=f.state_path,benchmark=amended,lock=lock,structure_path=f.f.structure_path)

    def test_adverse_access_requires_adverse_component_and_reference_uncertainty_is_explicit(self):
        from v10_candidate_access import validate_review
        from test_v10_consequences import defect, outcomes
        from test_wrong_destination_gates import evidence
        from v10_consequences import gate_outcomes
        from policy_cli import CRITICAL_GATES
        import dimension_score_v8_cli as scoring
        f=self.complete_fixture(unresolved_access=True,broken_reference=True)
        state=study.read(f.state_path);benchmark=study.read(f.root/'migration/selected-benchmark.json');lock=study.read(f.root/state['study_comparison']['lock']['path'])
        receipt=study.read(f.root/'candidate/v10-access-review.json')
        def validate(document):
            return validate_review(document,state=state,state_path=f.state_path,benchmark=benchmark,lock=lock,structure_path=f.f.structure_path)
        # Generic node/path uncertainty leaves independent broken-target proof intact.
        result=study.read(f.root/'scoring-v10/evaluation-result.v14.json')
        self.assertTrue(next(r for r in result['critical_gates'] if r['gate_id']=='GATE-BROKEN-REFERENCE')['triggered'])
        structure=study.read(f.f.structure_path)
        finding=defect('DEFECT-XREF','unsupported_reference','XREF-001')
        structure['defects'].append(finding);f.f.structure_path.write_text(json.dumps(structure))
        receipt['structure_binding']['sha256']=study.file_digest(f.f.structure_path)
        receipt['requirements'][0]['structure_finding_ids'].append('DEFECT-XREF')
        assessment=validate(receipt)
        self.assertIn('XREF-001',{x for b in assessment['blockers'] for x in b['affected_item_ids']})
        data=evidence(fit='exact_fit',judgment='supported',treatment='substantive')
        data[0]['cross_reference_judgments'][0]['reference_id']='XREF-001'
        data[0]['candidate_denominator']['cross_reference_ids']=['XREF-001']
        data[3]['cross_references'][0]['reference_id']='XREF-001'
        self.assertTrue(outcomes(data)[0]['GATE-BROKEN-REFERENCE']['triggered'])
        proof=scoring._destination_gate_evidence(*data)
        proof[2]['status']='indeterminate';proof[2]['blockers'].extend(assessment['blockers'])
        policy={'critical_gates':[{'gate_id':k,'description':v} for k,v in CRITICAL_GATES]}
        after={r['gate_id']:r for r in gate_outcomes(policy,data[0],data[1],proof,scoring._legacy_critical_gate_outcomes)}
        self.assertFalse(after['GATE-BROKEN-REFERENCE']['triggered'])
        # A negative parent judgment cannot use a passing node as adverse support.
        audit_record=next(r for r in state['artifacts'] if r.get('schema_version')=='missing-access-audit-v1')
        audit_path=f.root/audit_record['path'];audit=study.read(audit_path)
        parent=audit['subject_judgments'][0]
        parent['stance_preserved']='no';parent['realistic_first_lookup_success']='no'
        audit_path.write_text(json.dumps(audit));audit_record['sha256']=study.file_digest(audit_path)
        for binding in receipt['audit_bindings']:
            if binding['path']==audit_record['path']:binding['sha256']=audit_record['sha256']
        for row in receipt['requirements']:row['resulting_parent_judgment']=deepcopy(parent)
        row=receipt['requirements'][0]
        row.update(disposition='reviewed',factual_status='not_satisfied',structure_finding_ids=['NODE-001'])
        for field,component in [('stance_preserved','conceptual_stance_fidelity'),('realistic_first_lookup_success','heading_access_architecture')]:
            row['judgment_fields']=[field]
            for status in ('passes','uninspectable','minor_issues','major_issues','fails'):
                structure['node_judgments'][0]['component_judgments'][component]['status']=status
                f.f.structure_path.write_text(json.dumps(structure));receipt['structure_binding']['sha256']=study.file_digest(f.f.structure_path)
                with self.subTest(field=field,status=status):
                    if status in {'passes','uninspectable'}:
                        with self.assertRaisesRegex(ValueError,'relevant bound structure evidence'):validate(receipt)
                    else:validate(receipt)

    def test_parent_access_delta_requires_review_without_facets_and_empty_requirements_preserve_results(self):
        from v10_candidate_access import requirements,bound_amendment
        terms=self.complete_fixture(amendment_style='terms')
        state=study.read(terms.state_path);benchmark=study.read(terms.root/'migration/selected-benchmark.json');lock=study.read(terms.root/state['study_comparison']['lock']['path'])
        expected=requirements(benchmark,bound_amendment(state,terms.state_path,lock))
        self.assertEqual({'amendment_delta'},{key[2] for key in expected})
        self.assertEqual(len(expected),len(study.read(terms.root/'candidate/v10-access-review.json')['requirements']))
        question=self.complete_fixture(amendment_style='question')
        qstate=study.read(question.state_path);qbenchmark=study.read(question.root/'migration/selected-benchmark.json');qlock=study.read(question.root/qstate['study_comparison']['lock']['path']);qreceipt=study.read(question.root/'candidate/v10-access-review.json')
        qreceipt['requirements'][0]['factual_status']='not_satisfied'
        from v10_candidate_access import validate_review
        with self.assertRaises(ValueError):validate_review(qreceipt,state=qstate,state_path=question.state_path,benchmark=qbenchmark,lock=qlock,structure_path=question.f.structure_path)
        empty=self.complete_fixture(amendment_style='none')
        self.assertFalse((empty.root/'candidate/v10-access-review.json').exists())
        result=study.read(empty.root/'scoring-v10/evaluation-result.v14.json')
        self.assertEqual('ready',result['method_readiness']['status'])
        self.assertEqual(0,result['comparison_key']['study_identity']['candidate_access_review']['requirement_count'])

    def test_unresolved_access_review_blocks_authority_without_inventing_quality_failure(self):
        f=self.complete_fixture(unresolved_access=True)
        result=study.read(f.root/'scoring-v10/evaluation-result.v14.json')
        self.assertEqual('indeterminate',result['gate_assessment']['status'])
        self.assertEqual('indeterminate',result['authoritative_evaluation']['status'])
        self.assertEqual('indeterminate',result['method_readiness']['status'])
        self.assertFalse(any(row['triggered'] for row in result['critical_gates']))
        parent=study.read(f.root/'candidate/v10-access-review.json')['requirements'][0]['resulting_parent_judgment']
        self.assertEqual('complete',parent['coverage'])
        blocked={x for row in result['gate_assessment']['blockers'] for x in row['affected_item_ids']}
        self.assertTrue({'SUBJ-001','PATH-001','NODE-001'} <= blocked)

    def test_fresh_policy_and_unbound_v10_lineage_are_rejected(self):
        f=prepare_v10(self);output=f.root/'unbound-v10.json'
        result=v10('state','init','--output',output,'--evaluation-id','EVAL-UNBOUND','--source-title','Synthetic','--source-file',f.root/'source.pdf','--page-start','1','--page-end','1','--intended-readership','Synthetic reader')
        self.assertNotEqual(0,result.returncode);self.assertIn('v10_migration_required',result.stdout);self.assertFalse(output.exists())
        self.assertNotEqual(0,v10('policy','--help').returncode)
        direct=subprocess.run([sys.executable,'-c',"import runtime_profile; runtime_profile.select_v10(); import policy_cli; policy_cli.build_policy({})"],cwd=SCRIPTS,capture_output=True,text=True)
        self.assertNotEqual(0,direct.returncode);self.assertIn('explicit migration',direct.stderr)
        from v10_migration import migrate_state_identity
        unbound=study.read(f.state_path);migrate_state_identity(unbound);output.write_text(json.dumps(unbound));before=output.read_bytes()
        for command in [('state','validate'),('study','preflight'),('score','score'),('state','adopt-standard-policy')]:
            result=v10(*command,'--state',output);self.assertNotEqual(0,result.returncode,result.stdout+result.stderr);self.assertEqual(before,output.read_bytes())
        self.assertFalse((f.root/'scoring').exists())

    def test_access_proof_tampering_rejects_before_mutation(self):
        for change in ('missing_review','same_author','candidate_exposure','wrong_scope','wrong_population'):
            with self.subTest(change=change):
                f=prepare_v10(self);before=f.state_path.read_bytes()
                op=f.root/'release/access-overlay.json';rp=f.root/'release/access-review.json'
                overlay=study.read(op);review=study.read(rp)
                if change=='same_author':review['reviewer_id']=overlay['author_id']
                elif change=='candidate_exposure':overlay['candidate_seen']=True
                elif change=='wrong_scope':overlay['source_scope']['document_page_span']=[1,2]
                elif change=='wrong_population':overlay['after_population']['subjects']=[]
                self_hash(overlay,'overlay_sha256');op.write_text(json.dumps(overlay));review.update(overlay_sha256=overlay['overlay_sha256'],overlay_file_sha256=study.file_digest(op));rp.write_text(json.dumps(review))
                f.lock['benchmark_access']['overlay'].update(sha256=study.file_digest(op));f.lock['benchmark_access']['review'].update(sha256=study.file_digest(rp));f.lock['benchmark_access']['overlay_sha256']=overlay['overlay_sha256'];rebind(f)
                if change=='missing_review':rp.unlink()
                result=migrate(f);self.assertNotEqual(0,result.returncode,result.stdout+result.stderr)
                self.assertEqual(before,f.state_path.read_bytes());self.assertFalse((f.root/'migration').exists())

    def test_overlay_facets_weights_and_declared_evidence(self):
        f=prepare_v10(self);base=study.read(f.args.release_benchmark)
        initial=study.read(f.root/'release/access-overlay.json')
        parent=deepcopy(base['subjects'][0]);evidence=preserved_evidence_rows(parent)
        added=deepcopy(parent);added['subject_id']='SUBJ-NEW-V10'
        delta={'delta_id':'DELTA-NEW','clause_ids':['IPDF-ANA-06'],'family':'subjects','item_id':added['subject_id'],'operation':'add','weight_treatment':'new_weighted_parent','reason':'Distinct synthetic source-supported access obligation.','distinct_obligation_rationale':'This separately represented obligation cannot be a facet of the existing parent.','evidence_ids':[row['evidence_id'] for row in evidence],'replacement':added}
        set_deltas(f,[delta]);overlay=study.read(f.root/'release/access-overlay.json')
        result=apply_overlay(base,overlay)
        self.assertEqual(len(base['subjects'])+1,len(result['subjects']))
        self.assertEqual(overlay['after_population'],population(result))
        migrated=migrate(f);self.assertEqual(0,migrated.returncode,migrated.stdout+migrated.stderr)
        self.assertEqual(overlay['after_population'],population(study.read(f.root/'migration/selected-benchmark.json')))
        for mutation in ('priority','duplicate_facet','unknown_task_subject','undeclared_evidence'):
            with self.subTest(mutation=mutation):
                bad=deepcopy(initial)
                if mutation=='priority':
                    bad['deltas'][0]['weight_treatment']='updated_parent';bad['deltas'][0]['replacement']['priority']='optional'
                elif mutation=='duplicate_facet':
                    facets=bad['deltas'][0]['replacement']['required_access_facets'];facets.append(deepcopy(facets[0]))
                elif mutation=='unknown_task_subject':
                    task=deepcopy(base['reader_tasks'][0]);task['required_access_facets']=[{'facet_id':'FACET-TASK','question':'Synthetic lookup?','required_subject_ids':['SUBJ-NOT-A-PARENT'],'weight':'unweighted_access_facet'}]
                    bad['deltas'][0].update(family='reader_tasks',item_id=task['task_id'],replacement=task)
                else:
                    bad['deltas'][0]['evidence_ids']=['EVID-UNDECLARED']
                self_hash(bad,'overlay_sha256')
                with self.assertRaises(ValueError):apply_overlay(base,bad)

    def test_v9_numeric_boundaries_are_unchanged(self):
        probe=Path(__file__).with_name('v9_golden_probe.py')
        old=subprocess.run([sys.executable,str(probe),'v9'],capture_output=True,text=True)
        new=subprocess.run([sys.executable,str(probe),'v10'],capture_output=True,text=True)
        self.assertEqual(0,old.returncode,old.stderr);self.assertEqual(0,new.returncode,new.stderr)
        previous=json.loads(old.stdout);current=json.loads(new.stdout)
        previous.pop('gates');current.pop('gates')
        self.assertEqual(previous,current)

    def test_confirmed_quality_gate_precedes_assessment_gap(self):
        from v10_consequences import outcome_fields
        result={'critical_gates':[{'gate_id':'GATE-WRONG-LOCATOR','triggered':True}], 'evaluation_validity':{'status':'indeterminate'}, 'gate_assessment':{'status':'indeterminate','blockers':[]}}
        fields=outcome_fields(result);self.assertEqual('not_ready',fields['method_readiness']['status']);self.assertEqual('indeterminate',fields['authoritative_evaluation']['status'])
        result['critical_gates'][0]['triggered']=False
        self.assertEqual('indeterminate',outcome_fields(result)['method_readiness']['status'])

if __name__=='__main__':unittest.main()
