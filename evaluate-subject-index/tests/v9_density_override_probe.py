"""Synthetic component/collection fixture; not a valid full-evaluation report."""
from pathlib import Path
import sys
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import runtime_profile
runtime_profile.select_v9()
import scoring_core as core
import web_projection
import policy_cli
from test_v8_sensitivity_adversarial import reliability_ledgers, state

ledger=reliability_ledgers([state('supported','substantive',locator_id='LOC-A'),state('unsupported','passing_mention',locator_id='LOC-B'),state('unsupported','passing_mention',locator_id='LOC-C')],attempt='structurally_incomplete')
for i,row in enumerate(ledger['locators']):row['path_id']=f'PATH-{i}'
structure={'density':{'policy_status':'scored','measurement_level':'chapter_or_approved_intellectual_unit','targets':policy_cli.DENSITY_METRICS,'maximum_score_contribution':5,'chapter_measurements':[{'chunk_id':'CHUNK-001','indexable_source_words':120,'locator_bearing_heading_paths':3,'locator_occurrences':3}]}}
ledger['structure']=structure
selectivity=core.calculate_selectivity(ledger,'full')
manifest={'chunks':[{'chunk_id':'CHUNK-001','title':'Synthetic unit','source_units':['Synthetic'],'owned_document_page_ranges':[[1,1]]}]}
density=web_projection.build_density(structure,manifest,{'dimensions':[selectivity]})
core.validate_schema_document(density,'web-collection-v1.schema.json','Synthetic density collection')
print(json.dumps({'fixture_kind':'arithmetic_and_collection_unit_only','publishable_full_evaluation':False,'reason':'Full-audit validity rejects structurally incomplete ledgers; this isolates the preserved component override.','editorial_selectivity':selectivity,'density_collection':density},indent=2))
