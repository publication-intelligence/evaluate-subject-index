"""Factual candidate review of every frozen access requirement; no score roll-up."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import study_comparison as study
from schema_validation import schema_errors

SCHEMA = 'subject-index-v10-candidate-access-review-v1'
ARTIFACT = 'candidate_benchmark_access_review'


def requirements(benchmark, amendment=None):
    result = {}
    for kind, family, id_key in (('subject','subjects','subject_id'),('reader_task','reader_tasks','task_id')):
        for parent in benchmark[family]:
            entries=[('facet',row['facet_id'],row) for row in parent.get('required_access_facets',[])]
            if parent.get('access_scope_rule'):
                entries.append(('scope_rule','SCOPE',parent['access_scope_rule']))
            for row in parent.get('retained_source_distinctions',[]):
                entries.append(('retained_distinction',row['source_local_subject_id'],row))
            for requirement_kind, identity, value in entries:
                key=(kind,parent[id_key],requirement_kind,identity)
                from runtime_profile import semantic_uncertainty
                value_hash=study.digest(value)
                if key in result:
                    study.require(semantic_uncertainty() and requirement_kind=='retained_distinction' and result[key]==value_hash,
                                  'Duplicate parent-qualified access requirement conflicts or is not an identical retained distinction')
                result[key]=value_hash
    for delta in (amendment or {}).get('deltas',[]):
        if delta['operation']=='retire':continue
        kind='subject' if delta['family']=='subjects' else 'reader_task'
        result[(kind,delta['item_id'],'amendment_delta',delta['delta_id'])]=study.digest(delta)
    return result



def requirement_inventory_provenance(benchmark,amendment=None):
    expected=requirements(benchmark,amendment)
    duplicates=[]
    for kind,family,id_key in [('subject','subjects','subject_id'),('reader_task','reader_tasks','task_id')]:
        for parent in benchmark[family]:
            occurrences={}
            for index,row in enumerate(parent.get('retained_source_distinctions',[])):
                occurrences.setdefault(row['source_local_subject_id'],[]).append(index)
            for identity,positions in sorted(occurrences.items()):
                if len(positions)>1:
                    key=(kind,parent[id_key],'retained_distinction',identity)
                    duplicates.append(dict(zip(('parent_kind','parent_id','requirement_kind','requirement_id'),key)) |
                                      {'requirement_sha256':expected[key],'multiplicity':len(positions),'source_occurrence_indices':positions})
    entries=[dict(zip(('parent_kind','parent_id','requirement_kind','requirement_id'),key)) | {'requirement_sha256':value} for key,value in sorted(expected.items())]
    return {'canonical_requirement_count':len(entries),'source_requirement_occurrence_count':len(entries)+sum(r['multiplicity']-1 for r in duplicates),
            'inventory_sha256':study.digest(entries),'duplicate_occurrences':duplicates}

def bound_amendment(state,state_path,lock):
    root=(state_path.parent/state['study_comparison']['lock']['path']).parent
    return study.bound_document(root,lock['benchmark_access']['overlay'])


def evidence_universe(value):
    result=set()
    if isinstance(value,dict):
        if isinstance(value.get('evidence_id'),str):result.add(value['evidence_id'])
        result.update(x for x in value.get('evidence_ids',[]) if isinstance(x,str))
        for child in value.values():result.update(evidence_universe(child))
    elif isinstance(value,list):
        for child in value:result.update(evidence_universe(child))
    return result


def key(row):
    return tuple(row[k] for k in ('parent_kind','parent_id','requirement_kind','requirement_id'))


def validate_review(document, *, state, state_path, benchmark, lock, structure_path):
    """Check exact factual provenance and recorded judgment agreement only."""
    from runtime_profile import semantic_uncertainty
    schema='candidate-access-review-v10-semantic.schema.json' if document.get('schema_version')=='subject-index-v10-candidate-access-review-v2' and semantic_uncertainty() else 'candidate-access-review-v10.schema.json'
    study.require(not schema_errors(document,schema,profile='v10'), 'GATE-ASSESSMENT-ACCESS-REVIEW: invalid factual review receipt')
    root=state_path.parent
    study.require(document['evaluation_id']==state['evaluation_id'] and document['candidate_sha256']==state['candidate']['candidate_sha256'], 'Access review candidate/evaluation differs')
    study.require(document['benchmark_sha256']==benchmark['benchmark_sha256'] and document['study_lock_sha256']==lock['lock_sha256'] and document['benchmark_access_sha256']==lock['benchmark_access']['overlay_sha256'], 'Access review benchmark/amendment binding is stale')
    amendment=bound_amendment(state,state_path,lock)
    expected=requirements(benchmark,amendment)
    if semantic_uncertainty():
        provenance=requirement_inventory_provenance(benchmark,amendment)
        if schema=='candidate-access-review-v10-semantic.schema.json' or provenance['duplicate_occurrences']:
            study.require(document.get('requirement_inventory_provenance')==provenance,'Derived access inventory requires exact multiplicity/provenance without source mutation')
    rows=document['requirements'];keys=[key(row) for row in rows]
    study.require(len(keys)==len(set(keys)) and set(keys)==set(expected), 'Access review requires the exact parent-qualified requirement set without omissions, foreign IDs or duplicates')
    allowed_audits={'missing-access-audit-v1','missing-access-audit-v2'} if semantic_uncertainty() else {'missing-access-audit-v1'}
    audits=[r for r in state['artifacts'] if r['stage']=='missing_access_audit' and r.get('schema_version') in allowed_audits]
    expected_bindings=sorted([{'path':r['path'],'sha256':r['sha256']} for r in audits],key=lambda r:r['path'])
    study.require(sorted(document['audit_bindings'],key=lambda r:r['path'])==expected_bindings, 'Access review does not bind the exact registered audit bytes')
    subjects={};tasks={};known_evidence=evidence_universe(benchmark)
    for record in audits:
        audit=study.bound_document(root,record)
        known_evidence.update(evidence_universe(audit))
        for target, collection, field in ((subjects,'subject_judgments','subject_id'),(tasks,'reader_task_results','task_id')):
            for row in audit[collection]:
                study.require(row[field] not in target,'Duplicate parent audit judgment')
                target[row[field]]=row
    bound_structure=study.bound_document(root,document['structure_binding'])
    study.require((root/document['structure_binding']['path']).resolve()==structure_path.resolve() and document['structure_binding']['sha256']==study.file_digest(structure_path), 'Access review binds a different structure audit')
    inventory,_=study.registered_document(state,state_path,'candidate_normalization','subject-index-item-inventory-v2')
    paths={row['path_id'] for row in inventory['paths']}
    known_evidence.update(evidence_universe(bound_structure))
    defects={row['defect_id']:row for row in bound_structure['defects']}
    nodes={row['node_id']:row for row in bound_structure['node_judgments']}
    finding_ids={row['defect_id'] for row in bound_structure['defects']} | {row['node_id'] for row in bound_structure['node_judgments']}
    unresolved=[]
    for row in rows:
        study.require(row['requirement_sha256']==expected[key(row)],'Access review requirement content is stale')
        parent=(subjects if row['parent_kind']=='subject' else tasks).get(row['parent_id'])
        study.require(parent is not None and row['resulting_parent_judgment']==parent,'Access review parent judgment differs from registered audit')
        study.require(set(row['tested_path_ids'])<=paths,'Access review cites foreign candidate paths')
        study.require(set(row['structure_finding_ids'])<=finding_ids,'Access review cites foreign structure judgments')
        study.require(set(row['evidence_ids'])<=known_evidence,'Access review cites evidence outside the bound source/audit/structure universe')
        fields=set(row['judgment_fields'])
        allowed={'coverage','stance_preserved','realistic_first_lookup_success'} if row['parent_kind']=='subject' else {'result'}
        study.require(fields<=allowed,'Access review declares an incompatible parent judgment aspect')
        unresolved_row=row['disposition']=='unresolved' or row['factual_status']=='uninspectable'
        if not unresolved_row and row['factual_status'] in {'partially_satisfied','not_satisfied'}:
            positive={'coverage':'complete','stance_preserved':'yes','realistic_first_lookup_success':'yes','result':'succeeds'}
            study.require(not any(parent[field]==positive[field] for field in fields),'Unsatisfied reviewed requirement contradicts its declared positive parent judgment aspect')
            for field,component,owner in [('stance_preserved','conceptual_stance_fidelity','conceptual_stance_fidelity'),('realistic_first_lookup_success','heading_access_architecture','findability_navigation')]:
                if field in fields:
                    study.require(any((fid in nodes and nodes[fid]['component_judgments'].get(component,{}).get('status') in {'minor_issues','major_issues','fails'}) or (fid in defects and defects[fid]['dimension_owner']==owner) for fid in row['structure_finding_ids']), 'A claimed fidelity/navigation finding requires relevant bound structure evidence')
        if row['factual_status']=='satisfied':
            study.require(bool(row['tested_path_ids']),'Satisfied access requires concrete tested candidate paths')
        # The reviewer records what was checked, including unresolved evidence.
        # No facet status is converted into numerical credit or a quality defect.
        if unresolved_row:
            affected={row['parent_id'],*row['tested_path_ids'],*row['structure_finding_ids']}
            for fid in row['structure_finding_ids']:
                if fid in defects:affected.update(defects[fid]['affected_item_ids'])
                if fid in nodes:
                    affected.update(p['path_id'] for p in inventory['paths'] if fid in p.get('node_ids',[]))
            unresolved.append({'blocker_id':'GATE-ASSESSMENT-ACCESS-REVIEW','affected_item_ids':sorted(affected),
                               'reason':f"Unresolved factual review of {row['requirement_kind']} {row['requirement_id']} under {row['parent_id']}; private review rationale retained in the bound receipt."})
    stamp=datetime.fromisoformat(document['reviewed_at'].replace('Z','+00:00'))
    freeze=datetime.fromisoformat(lock['benchmark_access']['frozen_at'].replace('Z','+00:00'))
    study.require(stamp.utcoffset() is not None and freeze<=stamp<=datetime.now(timezone.utc),'Access review must follow the frozen amendment and not be in the future')
    return {'status':'indeterminate' if unresolved else 'sufficient','blockers':unresolved,'requirement_count':len(expected)}


def bound_review(state,state_path,benchmark,lock,*,structure_path=None):
    expected=requirements(benchmark,bound_amendment(state,state_path,lock))
    records=[r for r in state['artifacts'] if r.get('artifact_type')==ARTIFACT]
    if not expected and not records:
        return {'status':'sufficient','blockers':[],'requirement_count':0,'receipt_file_sha256':None}
    study.require(len(records)==1 and records[0].get('schema_version') in ({SCHEMA,'subject-index-v10-candidate-access-review-v2'} if __import__('runtime_profile').semantic_uncertainty() else {SCHEMA}),'GATE-ASSESSMENT-ACCESS-REVIEW: one registered factual access review is required before an authoritative V10 evaluation')
    document=study.bound_document(state_path.parent,records[0])
    if structure_path is None:
        _,record=study.registered_document(state,state_path,'structure_audit','structure-audit-v6')
        structure_path=state_path.parent/record['path']
    result=validate_review(document,state=state,state_path=state_path,benchmark=benchmark,lock=lock,structure_path=structure_path)
    return {**result,'receipt_file_sha256':records[0]['sha256']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',required=True);parser.add_argument('--input',required=True)
    args=parser.parse_args()
    from state_cli import evaluation_mutation_lock,save_state,validate_state,now
    from study_cli import record
    try:
        path=Path(args.state).resolve();source=Path(args.input).resolve()
        with evaluation_mutation_lock(path):
            state=study.read(path);errors,_=validate_state(state,state_path=path)
            study.require(not errors,'Invalid V10 state')
            study.require(state['stages']['missing_access_audit']['status']=='completed' and state['stages']['structure_audit']['status']=='not_started','Register factual access review after missing-access audit and before structure registration')
            study.require(source.is_relative_to(path.parent) and not any(r['path']==source.relative_to(path.parent).as_posix() or r.get('artifact_type')==ARTIFACT for r in state['artifacts']),'Access review must be a new in-evaluation artifact')
            lock=study.preflight_state(state,path)
            benchmark,_=study.registered_document(state,path,'benchmark_freeze','source-subject-benchmark-v2')
            document=study.read(source)
            outcome=validate_review(document,state=state,state_path=path,benchmark=benchmark,lock=lock,structure_path=path.parent/document['structure_binding']['path'])
            updated=deepcopy(state);updated['artifacts'].append(record(path.parent,source,source.read_bytes(),'missing_access_audit',ARTIFACT,document['schema_version']))
            updated['updated_at']=now()
            save_state(path,updated)
        print(json.dumps({'ok':True,'review_status':outcome['status'],'requirement_count':outcome['requirement_count'],'quality_failure_inferred':False},indent=2))
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}));raise SystemExit(1)

if __name__=='__main__':main()
