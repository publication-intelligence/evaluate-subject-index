"""Conserve material findings across unchanged-candidate V10 revisions."""
import study_comparison as study
from schema_validation import schema_errors


def material_ids(structure):
    warranted=set(structure.get('scoring_context',{}).get('cross_reference_applicability',{}).get('reference_defect_ids',[]))
    return sorted(row['defect_id'] for row in structure.get('defects',[])
                  if row.get('severity') in {'major','critical'} or row['defect_id'] in warranted)


def validate(document, prior_structure, candidate_sha256, prior_structure_file_sha256, successor_structure=None):
    study.require(not schema_errors(document,'prior-defect-reconciliation-v10.schema.json',profile='v10'),
                  'Invalid prior-defect reconciliation')
    study.require(document['candidate_sha256']==candidate_sha256==prior_structure['candidate_sha256'],
                  'Prior-defect reconciliation requires an unchanged candidate fingerprint')
    study.require(document['prior_structure_file_sha256']==prior_structure_file_sha256,
                  'Prior-defect reconciliation binds different prior structure bytes')
    expected=material_ids(prior_structure);rows=document['findings'];ids=[row['prior_defect_id'] for row in rows]
    study.require(len(ids)==len(set(ids)) and sorted(ids)==expected,
                  'Every prior major/critical finding requires exactly one disposition')
    successor_ids=None;successor_evidence=None
    if successor_structure is not None:
        successor_ids={row['defect_id'] for row in successor_structure.get('defects',[])} | {row['node_id'] for row in successor_structure.get('node_judgments',[])}
        def evidence(value):
            found=set()
            if isinstance(value,dict):
                found.update(x for x in value.get('evidence_ids',[]) if isinstance(x,str))
                for child in value.values():found.update(evidence(child))
            elif isinstance(value,list):
                for child in value:found.update(evidence(child))
            return found
        successor_evidence=evidence(successor_structure)
    for row in rows:
        if row['disposition'] in {'retained','superseded'}:
            study.require(row['successor_finding_ids'],'Retained findings require successor finding IDs')
        else:
            study.require(not row['successor_finding_ids'],'Resolved/rebutted findings cannot cite live successor findings')
        if row['disposition']!='retained':
            study.require(row['evidence_ids'] and row['rationale'].strip(),
                          'Resolved, rebutted or superseded findings require explicit evidence and rationale')
        if successor_ids is not None:
            study.require(set(row['successor_finding_ids'])<=successor_ids,
                          'Reconciliation cites successor findings absent from the current structure audit')
            study.require(set(row['evidence_ids'])<=successor_evidence,
                          'Reconciliation cites evidence absent from the current structure audit')
    study.require(document['reconciliation_sha256']==study.digest({k:v for k,v in document.items() if k!='reconciliation_sha256'}),
                  'Prior-defect reconciliation self-hash mismatch')
    return {'prior_material_finding_count':len(expected),
            'disposition_counts':{name:sum(row['disposition']==name for row in rows)
                                  for name in ('retained','resolved','evidence_rebutted','superseded')}}
if __name__ == "__main__":
    __import__("runtime_profile").require_public_cli()
