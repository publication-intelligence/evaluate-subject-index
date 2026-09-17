"""Export native synthetic correction bundles pinned to the current review head."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import test_v10_runtime as baseline
from test_v10_semantic_runtime import SemanticRuntimeTests,compatibility,command
from v10_execution import payload_fingerprint,CONSTITUENTS
study=baseline.study


def main():
    output=Path(sys.argv[1]).resolve()
    if output.exists():raise SystemExit('Output must be new')
    repo=Path(__file__).resolve().parents[2]
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=repo,text=True).strip():
        raise SystemExit('Seal fixtures only from a clean tracked runtime')
    output.mkdir(parents=True)
    baseline_case=baseline.V10RuntimeTests();semantic_case=SemanticRuntimeTests()
    try:
        first=baseline_case.complete_fixture(evaluation_id='EVAL-V10S-FIRST')
        second=baseline_case.complete_fixture(evaluation_id='EVAL-V10S-SECOND',source_fixture=first)
        for f in (first,second):
            approval,release=compatibility(f,head)
            for args in [('adopt','--state',f.state_path,'--compatibility',approval,'--source-release',release,'--output-dir','semantic-execution'),('score','score','--state',f.state_path,'--output-dir','scoring-semantic'),('score','build-report','--state',f.state_path)]:
                r=command(*args)
                if r.returncode:raise RuntimeError(r.stdout+r.stderr)
        unknown=semantic_case.native_semantic_case(unknown_treatment=True,broken_reference=False,source_fixture=first,evaluation_id='EVAL-V10S-SEMANTIC',runtime_revision=head)
        gated=semantic_case.native_semantic_case(source_fixture=first,evaluation_id='EVAL-V10S-GATED',runtime_revision=head)
        nonkeep=semantic_case.native_semantic_case(aggregate=True,source_fixture=first,evaluation_id='EVAL-V10S-NONKEEP',runtime_revision=head)
        fixtures=[('native-first',first),('native-second',second),('native-semantic',unknown),('native-gated-semantic',gated),('native-known-nonkeep',nonkeep)]
        for name,f in fixtures:shutil.copytree(f.root/'scoring-semantic',output/name)
        r=command('study','assemble-comparison','--state',first.state_path,'--state',second.state_path,'--output-dir',output/'comparison')
        if r.returncode:raise RuntimeError(r.stdout+r.stderr)
        shutil.copytree(first.root,output/'synthetic-evaluation')
        files=[{'path':p.relative_to(output).as_posix(),'sha256':study.file_digest(p)} for p in sorted(output.rglob('*')) if p.is_file()]
        manifest={'schema_version':'subject-index-v10-semantic-consumer-fixture-manifest-v1','runtime_commit':head,'runtime_payload_sha256':payload_fingerprint(),'contract_constituents':CONSTITUENTS,'synthetic_only':True,'native_bundles':[name+'/v10-canonical-projection' for name,_ in fixtures],'assembled_comparison':'comparison/comparison.json','files':files}
        target=output/'fixture-manifest.json';target.write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps({'manifest':str(target),'sha256':study.file_digest(target),'files':len(files)}))
    finally:
        baseline_case.doCleanups();semantic_case.doCleanups()

if __name__=='__main__':main()
