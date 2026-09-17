"""Synthetic axis-scoped blockers preserve independent known predicates."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from test_wrong_destination_gates import evidence
from test_v10_consequences import outcomes
from test_v10_semantic_utility import semantic
import runtime_profile


class SemanticGateTests(unittest.TestCase):
    def test_independent_known_fit_and_keep_survive_unknown_treatment(self):
        data=evidence(fit='no_fit',judgment='unsupported',treatment='absent')
        original=data[2][0]['judgments'][0]
        s=semantic(None,'no_fit','unsupported');s.update({k:original[k] for k in ('locator_id','path_id','complete_heading_path','document_page','source_page_label')})
        data[2][0]['judgments'][0]=s
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            gates,assessment=outcomes(data)
        self.assertTrue(gates['GATE-WRONG-LOCATOR']['triggered'])
        self.assertTrue(gates['GATE-BROKEN-REFERENCE']['triggered'])
        self.assertEqual('indeterminate',assessment['status'])
        self.assertEqual(['treatment'],assessment['blockers'][0]['semantic_unknown_axes'])

    def test_unknown_fit_withholds_only_dependent_gate(self):
        data=evidence();original=data[2][0]['judgments'][0]
        s=semantic('substantive',None);s.update({k:original[k] for k in ('locator_id','path_id','complete_heading_path','document_page','source_page_label')})
        data[2][0]['judgments'][0]=s
        with patch.object(runtime_profile,'ACTIVE','v10s'):
            gates,assessment=outcomes(data)
        self.assertFalse(gates['GATE-WRONG-LOCATOR']['triggered']);self.assertTrue(gates['GATE-BROKEN-REFERENCE']['triggered'])
        s['axis_resolution']['dependent_reference_ids']=['XREF-ONE']
        with patch.object(runtime_profile,'ACTIVE','v10s'):gates,_=outcomes(data)
        self.assertFalse(gates['GATE-BROKEN-REFERENCE']['triggered'])

if __name__=='__main__':unittest.main()
