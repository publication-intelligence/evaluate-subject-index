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
    return subprocess.run([sys.executable,str(SCRIPTS/'v10_semantic_cli.py'),*map(str,args)],capture_output=True,text=True)


def compatibility(f,revision=None):
    state=study.read(f.state_path);binding=state['study_comparison']['lock'];lock=study.read(f.root/binding['path'])
    release={'schema_version':'subject-index-successor-release-v3','methodology_commit':BASELINE,'artifacts':{'study_lock':{'path':'synthetic-lock.json','sha256':binding['sha256']}}}
    release['release_sha256']=study.digest(release);p=f.root/'synthetic-execution-release.json';p.write_text(json.dumps(release))
    document={'schema_version':'subject-index-v10-execution-compatibility-v1','compatibility_id':'COMPAT-SYNTHETIC','baseline_runtime_commit':BASELINE,'successor_runtime_commit':revision or '1'*40,'execution_contract_id':CONTRACT,'contract_constituents':CONSTITUENTS,'runtime_payload_sha256':payload_fingerprint(),'common_lock_file_sha256':binding['sha256'],'common_lock_sha256':lock['lock_sha256'],'source_release_file_sha256':study.file_digest(p),'source_release_sha256':release['release_sha256'],'authorized_by':'SYNTHETIC-REVIEWER','authorization_reference':'Synthetic compatibility test only','approved_at':'2026-09-17T00:00:00Z'}
    document['compatibility_sha256']=study.digest(document);q=f.root/'synthetic-compatibility.json';q.write_text(json.dumps(document));return q,p


class SemanticRuntimeTests(unittest.TestCase):
    def test_native_adoption_preserves_source_and_resolved_scores(self):
        case=baseline.V10RuntimeTests();self.addCleanup(case.doCleanups);f=case.complete_fixture()
        before=study.read(f.state_path);prior=study.read(f.root/'scoring-v10/dimension-calculations.v8.json')
        approval,release=compatibility(f)
        adopted=command('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','semantic-execution')
        self.assertEqual(0,adopted.returncode,adopted.stdout+adopted.stderr)
        after=study.read(f.state_path)
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
