"""Explicit candidate execution compatibility; immutable source bindings stay fixed."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import study_comparison as study
from schema_validation import schema_errors

BASELINE='815bcb66d3319d2f730a9645800b304bcbd4b2e9'
CONTRACT='subject-index-v10-semantic-execution-v1'
CONSTITUENTS={
 'subject-index-evaluation-v10-decision-v1':'f812eae0d09b60a4c1e74b1b6b9e6dd5850e088f9f9bb583152e9559f6ee07a9',
 'subject-index-evaluation-v10-semantic-uncertainty-addendum-v1':'e0f0e91a23274a94e292409b17df53d1b403bd0a52b26e6e7ae84809430c5f76',
 'subject-index-evaluation-v10-semantic-uncertainty-addendum-v2':'fea2a5b87f9e063d28135895fdb7d3637dfe4d2edd294fb7a50fd3aff7009277',
 'subject-index-evaluation-v10-semantic-uncertainty-addendum-v3':'4031abef00cb37508f30c8c89ec5e12592ce89369f144c1473ebc43bf9503a7d',
 'subject-index-evaluation-v10-semantic-uncertainty-addendum-v4':'b5d51033cb03093ca242841f8d9a5aac510915cfedad800614078e5199220a64'}


def payload_fingerprint():
    root=Path(__file__).resolve().parents[1]
    files={p.relative_to(root).as_posix():study.file_digest(p) for p in sorted(root.rglob('*'))
           if p.is_file() and '__pycache__' not in p.parts and p.name!='installation-receipt.json'}
    return study.digest(files)


def validate_compatibility(document,state,state_path,release):
    study.require(not schema_errors(document,'v10-execution-compatibility.schema.json',profile='v10'),'Invalid semantic execution compatibility')
    study.require(document['baseline_runtime_commit']==BASELINE and document['successor_runtime_commit']!=BASELINE,'Execution correction requires its own reviewed successor pin')
    study.require(document['execution_contract_id']==CONTRACT and document['contract_constituents']==CONSTITUENTS,'Execution contract differs from approved constituents')
    study.require(document['runtime_payload_sha256']==payload_fingerprint(),'Corrected runtime payload differs from reviewed compatibility binding')
    receipt=Path(__file__).resolve().parents[1]/'installation-receipt.json'
    if receipt.exists():
        installed=study.read(receipt)
        study.require(installed['tested_revision']==document['successor_runtime_commit'],'Installed runtime revision differs from compatibility binding')
    study.require(release.get('schema_version')=='subject-index-successor-release-v3' and release.get('methodology_commit')==BASELINE,'Source release must retain its preserved815 validator identity')
    study.require(release['release_sha256']==study.digest({k:v for k,v in release.items() if k!='release_sha256'}),'Source release self-hash mismatch')
    binding=state['study_comparison']['lock'];lock=study.bound_document(state_path.parent,binding)
    study.require(document['common_lock_file_sha256']==binding['sha256'] and document['common_lock_sha256']==lock['lock_sha256'],'Execution compatibility binds a different common lock')
    study.require(document['source_release_sha256']==release['release_sha256'] and document['source_release_file_sha256']==study.file_digest(release_path_from_state(state,state_path)),'Execution compatibility source release differs')
    study.require(release['artifacts']['study_lock']['sha256']==binding['sha256'],'Source release selects a different common lock')
    stamp=datetime.fromisoformat(document['approved_at'].replace('Z','+00:00'))
    study.require(stamp.utcoffset() is not None and stamp<=datetime.now(timezone.utc),'Execution approval must be timezone-aware and not in the future')
    study.require(document['compatibility_sha256']==study.digest({k:v for k,v in document.items() if k!='compatibility_sha256'}),'Execution compatibility self-hash mismatch')
    return {'execution_contract_id':CONTRACT,'contract_constituents':CONSTITUENTS,'successor_runtime_commit':document['successor_runtime_commit'],
            'runtime_payload_sha256':document['runtime_payload_sha256'],'compatibility_sha256':document['compatibility_sha256'],
            'source_release_file_sha256':document['source_release_file_sha256']}


def release_path_from_state(state,state_path):
    return state_path.parent/state['execution_compatibility']['source_release']['path']


def bound_execution(state,state_path):
    binding=state.get('execution_compatibility')
    study.require(isinstance(binding,dict),'Corrected V10 execution requires explicit compatibility adoption')
    document=study.bound_document(state_path.parent,binding['approval'])
    release=study.bound_document(state_path.parent,binding['source_release'])
    identity=validate_compatibility(document,state,state_path,release)
    study.bound_document(state_path.parent,binding['previous_state'])
    inventory=study.bound_document(state_path.parent,binding['requirement_inventory'])
    from v10_candidate_access import bound_amendment,requirement_inventory_provenance
    benchmark,_=study.registered_document(state,state_path,'benchmark_freeze','source-subject-benchmark-v2')
    lock=study.load_study_binding(state,state_path)
    study.require(inventory==requirement_inventory_provenance(benchmark,bound_amendment(state,state_path,lock)),'Derived requirement inventory provenance differs')
    return identity


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',required=True);parser.add_argument('--compatibility',required=True)
    parser.add_argument('--source-release',required=True);parser.add_argument('--output-dir',required=True)
    args=parser.parse_args()
    from state_cli import evaluation_mutation_lock,save_state,validate_state,now
    from study_cli import record
    try:
        path=Path(args.state).resolve();root=path.parent;out=(root/args.output_dir).resolve()
        with evaluation_mutation_lock(path):
            state=study.read(path)
            study.require(not state.get('execution_compatibility'),'Execution compatibility already adopted; do not replace it in place')
            errors,_=validate_state(state,state_path=path,profile='v10')
            study.require(not errors,'Adoption requires a valid preserved V10 state')
            study.load_study_binding(state,path)
            study.require(out.is_relative_to(root) and out!=root and not out.exists(),'Adoption output must be new inside the evaluation')
            approval=Path(args.compatibility).resolve();release_path=Path(args.source_release).resolve()
            document=study.read(approval);release=study.read(release_path)
            # Validate against input bindings before writing anything.
            updated=deepcopy(state)
            updated['schema_version']='subject-index-evaluation-state-v9'
            updated['execution_compatibility']={'approval':{'path':str(approval),'sha256':study.file_digest(approval)},
                'source_release':{'path':str(release_path),'sha256':study.file_digest(release_path)}}
            validate_compatibility(document,updated,path,release)
            files={'compatibility.json':approval.read_bytes(),'source-release.json':release_path.read_bytes(),'previous-state.json':path.read_bytes()}
            from v10_candidate_access import bound_amendment,requirement_inventory_provenance
            benchmark,_=study.registered_document(state,path,'benchmark_freeze','source-subject-benchmark-v2')
            lock=study.load_study_binding(state,path)
            files['requirement-inventory-provenance.json']=(json.dumps(requirement_inventory_provenance(benchmark,bound_amendment(state,path,lock)),indent=2)+'\n').encode()
            updated['execution_compatibility']={key:{'path':(out/name).relative_to(root).as_posix(),'sha256':hashlib.sha256(files[name]).hexdigest()} for key,name in [('approval','compatibility.json'),('source_release','source-release.json'),('previous_state','previous-state.json'),('requirement_inventory','requirement-inventory-provenance.json')]}
            stamp=now();removed={'scoring','web_report'}
            updated['artifacts']=[r for r in updated['artifacts'] if r['stage'] not in removed]
            for name,payload in files.items():updated['artifacts'].append(record(root,out/name,payload,'initialize','study_execution_compatibility'))
            for stage in removed:updated['stages'][stage]={'status':'not_started','updated_at':stamp,'notes':['Execution contract adoption invalidated derived outputs; original files remain preserved.']}
            updated['updated_at']=stamp
            out.mkdir()
            try:
                for name,payload in files.items():(out/name).write_bytes(payload)
                errors,_=validate_state(updated,state_path=path)
                study.require(not errors,'Adopted state fails validation: '+str(errors))
                bound_execution(updated,path)
                save_state(path,updated)
            except Exception:
                for name in files:(out/name).unlink(missing_ok=True)
                out.rmdir();raise
        print(json.dumps({'ok':True,'execution_contract_id':CONTRACT,'candidate_and_source_unchanged':True,'invalidated_stages':sorted(removed)}))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}));raise SystemExit(1)

if __name__=='__main__':main()
