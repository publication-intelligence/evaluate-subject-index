"""Validate and apply a separately reviewed, candidate-blind benchmark access delta.

This module never writes source proof or infers approval from a self-hash.
Review binds exact overlay proposal bytes, changed IDs and population accounting.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import study_comparison as study
from schema_validation import schema_errors

CLAUSES = ('IPDF-GOV-02', 'IPDF-ANA-06', 'IPDF-VOC-01', 'IPDF-VOC-02')


def population(benchmark):
    subjects = [{'id': row['subject_id'], 'weight': row.get('priority')} for row in benchmark['subjects']]
    tasks = [{'id': row['task_id'], 'weight': 1} for row in benchmark['reader_tasks']]
    treatments = []
    for subject in benchmark['subjects']:
        seen = set()
        for evidence in subject['evidence']:
            locator_class = evidence.get('locator_class', 'supporting')
            unit = (evidence['document_page'], locator_class)
            if locator_class == 'incidental' or unit in seen:
                continue
            seen.add(unit)
            payload = json.dumps({'subject_id': subject['subject_id'], 'document_page': unit[0],
                                  'locator_class': unit[1]}, sort_keys=True, separators=(',', ':')).encode()
            treatments.append({'id': 'TREAT-' + hashlib.sha256(payload).hexdigest()[:12].upper(), 'weight': 1})
    obligations = ([{'id': 'SUBJECT:' + row['id'], 'weight': row['weight']} for row in subjects]
                   + [{'id': 'TASK:' + row['id'], 'weight': row['weight']} for row in tasks]
                   + [{'id': 'TREATMENT:' + row['id'], 'weight': row['weight']} for row in treatments])
    return {'subjects': subjects, 'reader_tasks': tasks, 'treatments': treatments,
            'weighted_access_obligations': obligations}


def reconciliation(before, after):
    rows = []
    for family in before:
        old = {row['id'] for row in before[family]}; new = {row['id'] for row in after[family]}
        rows.append({'family': family, 'before_count': len(old), 'after_count': len(new),
                     'delta': len(new) - len(old), 'retained_ids': sorted(old & new),
                     'added_ids': sorted(new - old), 'retired_ids': sorted(old - new)})
    return rows


def evidence_ids(value):
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get('evidence_id'), str): found.add(value['evidence_id'])
        for item in value.values(): found |= evidence_ids(item)
    elif isinstance(value, list):
        for item in value: found |= evidence_ids(item)
    return found


def apply_overlay(base, overlay):
    """Apply only declared subject/task deltas; all other source content is fixed."""
    study.require(not schema_errors(overlay, 'benchmark-access-overlay-v10.schema.json', profile='v10'), 'Invalid V10 access overlay schema')
    study.require(overlay['overlay_sha256'] == study.digest({k:v for k,v in overlay.items() if k != 'overlay_sha256'}), 'Access overlay self-hash mismatch')
    study.require(overlay['base_benchmark_sha256'] == base['benchmark_sha256'], 'Access overlay base identity mismatch')
    study.require(overlay['before_population'] == population(base), 'Access overlay before population differs')
    result = deepcopy(base)
    seen = set()
    source_evidence = evidence_ids(base)
    for delta in overlay['deltas']:
        key = (delta['family'], delta['item_id'])
        study.require(delta['delta_id'] not in seen and key not in seen, 'Duplicate access delta or parent')
        seen.update((delta['delta_id'], key))
        study.require(set(delta['evidence_ids']) <= source_evidence, 'Overlay introduces evidence outside preserved discovery')
        allowed_pages = {row['document_page'] for row in preserved_evidence_rows(base)
                         if row.get('evidence_id') in delta['evidence_ids'] and 'document_page' in row}
        def check_pages(value):
            if isinstance(value, dict):
                pages = value.get('document_pages', [])
                if 'document_page' in value: pages = [*pages, value['document_page']]
                study.require(set(pages) <= allowed_pages, 'Replacement cites pages outside its declared preserved evidence')
                for child in value.values(): check_pages(child)
            elif isinstance(value, list):
                for child in value: check_pages(child)
        if delta['replacement'] is not None: check_pages(delta['replacement'])
        family = delta['family']; id_key = 'subject_id' if family == 'subjects' else 'task_id'
        rows = result[family]; matches = [i for i,row in enumerate(rows) if row[id_key] == delta['item_id']]
        operation = delta['operation']
        study.require(len(matches) == (0 if operation == 'add' else 1), 'Access delta parent existence mismatch')
        if operation == 'retire':
            study.require(delta['replacement'] is None and delta['weight_treatment'] == 'retired_parent', 'Retirement must explicitly retire its parent')
            rows.pop(matches[0]); continue
        new = deepcopy(delta['replacement'])
        study.require(new is not None and new.get(id_key) == delta['item_id'], 'Access delta changes stable parent identity')
        study.require(evidence_ids(new) <= set(delta['evidence_ids']), 'Replacement uses undeclared source evidence')
        # Existing evidence entries cannot be edited while retaining their IDs.
        def check_evidence(value):
            if isinstance(value, dict):
                if 'evidence_id' in value:
                    study.require(value in preserved_evidence_rows(base), 'Replacement rewrites preserved source evidence')
                for child in value.values(): check_evidence(child)
            elif isinstance(value, list):
                for child in value: check_evidence(child)
        check_evidence(new)
        if operation == 'add':
            study.require(delta['weight_treatment'] == 'new_weighted_parent' and delta['distinct_obligation_rationale'].strip(), 'New parent requires a distinct source-supported obligation')
            rows.append(new)
        else:
            if delta['weight_treatment'] == 'unweighted_facets':
                old = rows[matches[0]]
                allowed = {'access_scope_rule','required_access_facets','retained_source_distinctions'}
                study.require({k:v for k,v in old.items() if k not in allowed} == {k:v for k,v in new.items() if k not in allowed}, 'Unweighted facet delta changes parent content or weight')
                study.require(not any(row.get('independently_weighted', False) for row in new.get('required_access_facets', [])), 'Overlay facets must remain unweighted')
            else:
                study.require(delta['weight_treatment'] == 'updated_parent', 'Invalid updated parent treatment')
                old = rows[matches[0]]
                semantic_fields = {'label', 'aliases', 'acceptable_access', 'scope_note', 'stance', 'question',
                    'access_scope_rule', 'required_access_facets', 'retained_source_distinctions'}
                study.require({k:v for k,v in old.items() if k not in semantic_fields} ==
                              {k:v for k,v in new.items() if k not in semantic_fields},
                              'Updated parent changes weight or content outside the access profile')
            rows[matches[0]] = new
    validate_facets(result)
    study.require(overlay['after_population'] == population(result), 'Access overlay after population differs')
    expected_reconciliation = reconciliation(overlay['before_population'], overlay['after_population'])
    supplied = overlay['denominator_reconciliation']
    study.require([{k:v for k,v in row.items() if k != 'explanation'} for row in supplied] == expected_reconciliation,
                  'Access overlay denominator reconciliation does not reconstruct')
    for row in supplied:
        if row['before_count'] and row['after_count'] * 100 < row['before_count'] * 85:
            study.require(row['explanation'].strip(), 'A population reduction of more than 15% requires an explanation')
    # Existing benchmark validators enforce subject/task structure, unique IDs,
    # source spans and relationship references after retirement/addition.
    from benchmark_review_cli import final_benchmark_structure_errors
    study.require(not final_benchmark_structure_errors(result), 'Effective access benchmark has invalid structure')
    return result


def preserved_evidence_rows(value):
    result = []
    if isinstance(value, dict):
        if 'evidence_id' in value: result.append(value)
        for child in value.values(): result.extend(preserved_evidence_rows(child))
    elif isinstance(value, list):
        for child in value: result.extend(preserved_evidence_rows(child))
    return result


def validate_access(lock, base, root):
    access = lock['benchmark_access']
    overlay = study.bound_document(Path(root), access['overlay'])
    review = study.bound_document(Path(root), access['review'])
    study.require(not schema_errors(review, 'benchmark-access-review-v10.schema.json', profile='v10'), 'Invalid independent access review schema')
    study.require(overlay['source_scope'] == lock['source_scope'], 'Access overlay changes source scope/page map')
    study.require(overlay['source_methodology'] == lock['source_methodology'], 'Access overlay changes preserved policy proof')
    study.require(overlay['base_benchmark_file_sha256'] == lock['release']['benchmark_file_sha256'], 'Access overlay base bytes differ')
    study.require(overlay['base_review_file_sha256'] == lock['release']['lineage']['review_file_sha256'], 'Access overlay base review differs')
    study.require(overlay['overlay_sha256'] == access['overlay_sha256'], 'Access overlay identity differs')
    study.require(review['overlay_file_sha256'] == access['overlay']['sha256'] and review['overlay_sha256'] == overlay['overlay_sha256'], 'Independent review does not bind exact access overlay')
    study.require(review['reviewer_id'] != overlay['author_id'], 'Access overlay requires an independent reviewer')
    study.require(sorted(review['reviewed_delta_ids']) == sorted(row['delta_id'] for row in overlay['deltas']), 'Independent review does not cover every delta')
    study.require(review['population_sha256'] == study.digest({'before': overlay['before_population'], 'after': overlay['after_population'],
                  'reconciliation': overlay['denominator_reconciliation']}), 'Independent review population accounting differs')
    dates = [datetime.fromisoformat(x.replace('Z','+00:00')) for x in (overlay['prepared_at'], review['reviewed_at'], access['frozen_at'])]
    study.require(all(x.utcoffset() is not None for x in dates) and dates == sorted(dates), 'Invalid overlay review/freeze chronology')
    result = apply_overlay(base, overlay)
    study.require(study.benchmark_semantic_hash(result) == lock['benchmark_semantic_sha256'] == access['effective_benchmark_semantic_sha256'], 'Effective access benchmark fingerprint differs')
    return result


def validate_facets(benchmark):
    """Validate successor nested access obligations within each parent unit."""
    for family in ('subjects','reader_tasks'):
        for parent in benchmark[family]:
            facets = parent.get('required_access_facets', [])
            study.require(isinstance(facets,list), 'Access facets must be a list')
            parent_ids = set()
            for facet in facets:
                study.require(isinstance(facet,dict), 'Access facet must be an object')
                facet_id = facet.get('facet_id')
                study.require(isinstance(facet_id,str) and facet_id.strip() and facet_id not in parent_ids, 'Malformed or duplicate facet ID')
                parent_ids.add(facet_id)
                if family == 'subjects':
                    study.require(all(isinstance(facet.get(k),str) and facet[k].strip() for k in ('label','meaning')), 'Subject facet requires label and meaning')
                    study.require(isinstance(facet.get('acceptable_access'),list) and facet['acceptable_access'] and all(isinstance(x,str) and x.strip() for x in facet['acceptable_access']), 'Subject facet requires access language')
                    study.require(facet.get('independently_weighted') is False, 'Subject facet must be unweighted')
                    study.require(isinstance(facet.get('document_pages'),list) and facet['document_pages'] and all(isinstance(x,int) and not isinstance(x,bool) and x > 0 for x in facet['document_pages']), 'Subject facet requires valid source pages')
                else:
                    study.require(isinstance(facet.get('question'),str) and facet['question'].strip(), 'Task facet requires a question')
                    ids = facet.get('required_subject_ids')
                    study.require(isinstance(ids,list) and ids and all(isinstance(x,str) for x in ids) and len(ids)==len(set(ids)) and set(ids)<=set(parent['subject_ids']), 'Task facet cites an unknown or non-parent required subject')
                    study.require(facet.get('weight') == 'unweighted_access_facet', 'Task facet must be unweighted')
