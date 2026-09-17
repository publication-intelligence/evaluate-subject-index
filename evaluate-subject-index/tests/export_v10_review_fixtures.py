"""Export clearly labeled synthetic native bundles and independent outcome units.

Usage: python tests/export_v10_review_fixtures.py NEW_OUTPUT_DIRECTORY
Never invokes a real candidate or installs/selects a runtime for other tasks.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
from test_v10_runtime import V10RuntimeTests, v10, study
from test_v10_consequences import outcomes
from test_wrong_destination_gates import evidence
from v10_consequences import outcome_fields
from v10_release import machine_facts, validate_decision


def emit(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    output=Path(sys.argv[1]).resolve()
    if output.exists():raise SystemExit('Output must be new')
    output.mkdir(parents=True)
    case=V10RuntimeTests()
    try:
        first=case.complete_fixture(evaluation_id='EVAL-V10-FIRST')
        second=case.complete_fixture(evaluation_id='EVAL-V10-SECOND',source_fixture=first)
        gated=case.complete_fixture(evaluation_id='EVAL-V10-GATED',source_fixture=first,broken_reference=True)
        for label,f in [('native-first',first),('native-second',second),('native-gated',gated)]:
            shutil.copytree(f.root/'scoring-v10',output/label)
        result=v10('study','assemble-comparison','--state',first.state_path,'--state',second.state_path,'--output-dir',output/'comparison')
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        shutil.copytree(first.root,output/'synthetic-evaluation')
        gates,assessment=outcomes(evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='valid_destination'))
        baseline={'critical_gates':list(gates.values()),'evaluation_validity':{'status':'valid','blockers':[],'used_as_publication_gate':False},'gate_assessment':assessment}
        invalid={'status':'invalid','used_as_publication_gate':False,'blockers':[{'blocker_id':'VALIDITY-SOURCE-SPAN','outcome':'invalid','reason':'Synthetic mismatch in evaluated source identity.','evidence':[{'binding_role':'source_identity','expected':'a'*64,'observed':'b'*64,'evidence_ids':['EVID-SYNTHETIC-SOURCE']}]}]}
        unknown={'status':'indeterminate','blockers':[{'blocker_id':'GATE-ASSESSMENT-LOCATOR-UNCERTAIN','affected_item_ids':['LOC-ONE'],'reason':'Synthetic unresolved destination evidence.'}]}
        confirmed,_=outcomes(evidence(fit='exact_fit',judgment='supported',treatment='substantive',resolution='no_valid_destination'))
        cases={}
        for label in ('ready','gate-and-invalid','invalid-only','assessment-only','uninspectable-only'):
            value=deepcopy(baseline)
            if label=='gate-and-invalid':value.update(critical_gates=list(confirmed.values()),evaluation_validity=invalid)
            elif label=='invalid-only':value['evaluation_validity']=invalid
            elif label=='assessment-only':value['gate_assessment']=unknown
            elif label=='uninspectable-only':value['evaluation_validity']={'status':'indeterminate','used_as_publication_gate':False,'blockers':[{'blocker_id':'VALIDITY-UNINSPECTABLE','outcome':'indeterminate','count':2,'denominator':100,'rate':'0.02','threshold':'0.01','reason':'Synthetic inspectability tolerance exceeded.'}]}
            value.update(outcome_fields(value));cases[label]=value
        emit(output/'outcome-matrix.unit.json',{'schema_version':'subject-index-v10-outcome-fixture-v1','synthetic_only':True,'native_evaluation_claim':False,'cases':cases})
        native=study.read(output/'native-gated/evaluation-result.v14.json')
        decision={'schema_version':'subject-index-human-release-decision-v10','decision_id':'DECISION-SYNTHETIC','evaluation_id':native['evaluation_id'],'result_file_sha256':study.file_digest(output/'native-gated/evaluation-result.v14.json'),'machine_facts_sha256':study.digest(machine_facts(native)),'status':'approved_with_deviation','decided_by':'SYNTHETIC-HUMAN','decided_at':'2026-09-16T00:00:00Z','authorization_reference':'Synthetic consumer review only; not real release approval.','rationale':'Demonstrates a separate human record without changing machine facts.','acknowledged_gate_ids':native['method_readiness']['triggered_gate_ids'],'machine_outcomes_changed':False}
        validate_decision(decision,native,decision['result_file_sha256']);emit(output/'human-decision.separate.json',decision)
        files=[{'path':p.relative_to(output).as_posix(),'sha256':study.file_digest(p)} for p in sorted(output.rglob('*')) if p.is_file()]
        head=subprocess.run(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,check=True).stdout.strip()
        emit(output/'fixture-manifest.json',{'schema_version':'subject-index-v10-consumer-review-fixture-manifest-v1','runtime_commit':head,'synthetic_only':True,'native_bundles':['native-first/v10-canonical-projection','native-second/v10-canonical-projection','native-gated/v10-canonical-projection'],'assembled_comparison':'comparison/comparison.json','outcome_units':'outcome-matrix.unit.json','separate_human_decision':'human-decision.separate.json','files':files})
        print(json.dumps({'manifest':str(output/'fixture-manifest.json'),'sha256':study.file_digest(output/'fixture-manifest.json'),'files':len(files)}))
    finally:case.doCleanups()

if __name__=='__main__':main()
