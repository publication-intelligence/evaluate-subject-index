"""Conserve major/critical findings across unchanged-candidate V10 revisions."""
import study_comparison as study
from schema_validation import schema_errors


def material_ids(structure):
    return sorted(row['defect_id'] for row in structure.get('defects',[])
                  if row.get('severity') in {'major','critical'})


def validate(document, prior_structure, candidate_sha256, prior_structure_file_sha256):
    study.require(not schema_errors(document,'prior-defect-reconciliation-v10.schema.json',profile='v10'),
                  'Invalid prior-defect reconciliation')
    study.require(document['candidate_sha256']==candidate_sha256==prior_structure['candidate_sha256'],
                  'Prior-defect reconciliation requires an unchanged candidate fingerprint')
    study.require(document['prior_structure_file_sha256']==prior_structure_file_sha256,
                  'Prior-defect reconciliation binds different prior structure bytes')
    expected=material_ids(prior_structure);rows=document['findings'];ids=[row['prior_defect_id'] for row in rows]
    study.require(len(ids)==len(set(ids)) and sorted(ids)==expected,
                  'Every prior major/critical finding requires exactly one disposition')
    for row in rows:
        if row['disposition']=='retained':
            study.require(row['successor_finding_ids'],'Retained findings require successor finding IDs')
        else:
            study.require(row['evidence_ids'] and row['rationale'].strip(),
                          'Rebutted or superseded findings require explicit evidence and rationale')
    study.require(document['reconciliation_sha256']==study.digest({k:v for k,v in document.items() if k!='reconciliation_sha256'}),
                  'Prior-defect reconciliation self-hash mismatch')
    return {'prior_material_finding_count':len(expected),
            'disposition_counts':{name:sum(row['disposition']==name for row in rows)
                                  for name in ('retained','evidence_rebutted','superseded')}}
