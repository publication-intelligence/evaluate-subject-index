from copy import deepcopy
import unittest
from unittest.mock import patch
import runtime_profile
from v10_candidate_access import requirements,requirement_inventory_provenance

class SemanticRequirementsTests(unittest.TestCase):
    def test_only_exact_retained_distinctions_canonicalize_with_multiplicity(self):
        row={'source_local_subject_id':'SUBJ-SYNTHETIC','meaning':'Synthetic distinct access','evidence_ids':['EVID-SYNTHETIC']}
        benchmark={'subjects':[{'subject_id':'SUBJ-PARENT','retained_source_distinctions':[row,deepcopy(row)]}],'reader_tasks':[]}
        before=deepcopy(benchmark)
        for profile in ['v8','v9','v10']:
            with patch.object(runtime_profile,'ACTIVE',profile):
                with self.assertRaises(ValueError):requirements(benchmark)
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            self.assertEqual(1,len(requirements(benchmark)))
            inventory=requirement_inventory_provenance(benchmark)
            self.assertEqual(2,inventory['source_requirement_occurrence_count']);self.assertEqual(1,inventory['canonical_requirement_count'])
            self.assertEqual([0,1],inventory['duplicate_occurrences'][0]['source_occurrence_indices'])
            bad=deepcopy(benchmark);bad['subjects'][0]['retained_source_distinctions'][1]['meaning']='Different'
            with self.assertRaises(ValueError):requirements(bad)
            bad=deepcopy(benchmark);bad['subjects'][0]['required_access_facets']=[{'facet_id':'FACET-SYNTHETIC'},{'facet_id':'FACET-SYNTHETIC'}]
            with self.assertRaises(ValueError):requirements(bad)
        self.assertEqual(before,benchmark)
