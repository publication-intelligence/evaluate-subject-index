"""Retrospective provenance is explicit, byte-bound, and arithmetically inert."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import policy_cli
import dimension_score_v8_cli as dimensions
from schema_validation import schema_errors
import test_v8_provenance as provenance
import test_v8_completion as completion

STAGES = ('page_mapping', 'chunk_definition', 'source_subject_discovery',
          'benchmark_synthesis', 'benchmark_review', 'benchmark_freeze', 'candidate_normalization')


def migration_input(original):
    source = provenance.PolicyIdentityTests().policy_input()
    source.update(schema_version='subject-index-policy-build-input-v1', policy_id='MIGRATED')
    source['source_scope'] = {k: original['source_scope'][k] for k in (
        'source_sha256', 'document_page_span', 'page_map_sha256', 'chunk_manifest_sha256', 'availability')}
    source['audience'] = deepcopy(original['audience'])
    source['audit_design'] = {k: original['audit_design'][k] for k in ('mode', 'candidate_blindness')}
    source['deviations'] = deepcopy(original['deviations'])
    ref = {'path': 'original.json', 'sha256': 'a'*64}
    source['retrospective_migration'] = {
        'original_policy': {'policy_id': original['policy_id'],
            'policy_profile_id': original['policy_profile']['id'],
            'policy_sha256': original['policy_sha256'], 'freeze': deepcopy(original['freeze']), 'artifact': ref},
        'migrated_at': '2026-09-16T16:30:00Z', 'candidate_seen': True,
        'authorization': {'authorized_by': 'User', 'reference': 'task:explicit-migration-request'},
        'change_ledger_reference': 'migration/change-ledger.json',
        'reused_stages': {s: {'rerun': False, 'evidence': [{'path': f'{s}.json', 'sha256': 'b'*64}]} for s in STAGES},
    }
    return source


class PolicyMigrationTests(unittest.TestCase):
    def setUp(self):
        with patch.object(policy_cli, 'now', return_value='2026-01-01T00:00:00Z'):
            self.original = policy_cli.build_policy(provenance.PolicyIdentityTests().policy_input())
        self.source = migration_input(self.original)

    def build(self, source=None, original=None, base=None):
        return policy_cli.build_policy(source or self.source, original_policy=original or self.original, base_policy=base)

    def test_fresh_policy_stays_blind_and_migration_is_optional(self):
        self.assertNotIn('retrospective_migration', self.original)
        self.assertEqual([], schema_errors(self.original, 'evaluation-policy-v4.schema.json'))
        self.original['freeze']['candidate_seen'] = True
        self.assertTrue(schema_errors(self.original, 'evaluation-policy-v4.schema.json'))

    def test_v8_and_v81_originals_preserve_freeze_and_custom_density(self):
        for profile in ('subject-index-standard-policy-v8', 'subject-index-standard-policy-v8.1', 'subject-index-standard-policy-v8.2'):
            original = deepcopy(self.original)
            original['policy_profile']['id'] = profile
            original['density_profile']['metrics'][0]['target'] = 7.5
            original['policy_sha256'] = policy_cli.canonical_hash(original, 'policy_sha256')
            before = deepcopy(original)
            result = self.build(migration_input(original), original)
            dimensions.validate_v8_policy(result)
            self.assertEqual(before, original)
            self.assertEqual(original['freeze'], result['retrospective_migration']['original_policy']['freeze'])
            self.assertTrue(result['freeze']['candidate_seen'])
            self.assertEqual(original['density_profile'], result['density_profile'])
            self.assertNotEqual(original['policy_sha256'], result['policy_sha256'])

    def test_cleanup_preserves_latest_base_except_provenance(self):
        base = deepcopy(self.original)
        base['policy_id'] = 'PRIOR-MIGRATION'
        base['policy_profile']['targeted_migration'] = {'candidate_seen': True}
        base['density_profile']['metrics'][0]['provenance'] = 'rebound-v8.1'
        base['policy_sha256'] = policy_cli.canonical_hash(base, 'policy_sha256')
        expected = deepcopy(base)
        result = self.build(base=base)
        for value in (expected, result):
            for field in ('policy_id', 'policy_sha256', 'freeze', 'retrospective_migration'):
                value.pop(field, None)
            value['policy_profile'].pop('targeted_migration', None)
        self.assertEqual(expected, result)

    def test_v81_base_upgrades_gate_identity_without_changing_scoring_settings(self):
        base = deepcopy(self.original)
        base['policy_id'] = 'BASE-V81'
        base['policy_profile']['id'] = 'subject-index-standard-policy-v8.1'
        base['critical_gates'] = [g for g in base['critical_gates'] if g['gate_id'] not in {'GATE-WRONG-LOCATOR', 'GATE-BROKEN-REFERENCE'}]
        base['policy_sha256'] = policy_cli.canonical_hash(base, 'policy_sha256')
        result = self.build(base=base)
        self.assertEqual('subject-index-standard-policy-v8.2', result['policy_profile']['id'])
        for field in ('source_scope', 'audience', 'audit_design', 'density_profile', 'deviations', 'content_policies'):
            self.assertEqual(base[field], result[field], field)
        self.assertTrue(all(g in result['critical_gates'] for g in base['critical_gates']))
        self.assertEqual(2, len(result['critical_gates']) - len(base['critical_gates']))

    def test_missing_and_inconsistent_migration_is_rejected(self):
        for field in self.source['retrospective_migration']:
            source = deepcopy(self.source)
            del source['retrospective_migration'][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build(source)
        for field, value in [('policy_id', 'WRONG'), ('policy_sha256', 'f'*64), ('policy_profile_id', 'subject-index-standard-policy-v8'), ('freeze', {'frozen_at':'2025-01-01T00:00:00Z', 'candidate_seen':False})]:
            source = deepcopy(self.source)
            source['retrospective_migration']['original_policy'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build(source)
        for stamp in ('2025-01-01T00:00:00Z', 'yesterday', '2026-09-16T16:30:00'):
            source = deepcopy(self.source)
            source['retrospective_migration']['migrated_at'] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                self.build(source)
        with self.assertRaises(ValueError):
            policy_cli.build_policy(self.source)

    def test_semantic_consistency_is_checked_by_all_schema_consumers(self):
        result = self.build()
        for change in ('visibility', 'time', 'identity', 'rerun', 'missing_review', 'workaround'):
            altered = deepcopy(result)
            if change == 'visibility': altered['freeze']['candidate_seen'] = False
            if change == 'time': altered['freeze']['frozen_at'] = '2026-01-01T00:00:00Z'
            if change == 'identity': altered['policy_id'] = self.original['policy_id']
            if change == 'rerun': altered['retrospective_migration']['reused_stages']['benchmark_review']['rerun'] = True
            if change == 'missing_review': del altered['retrospective_migration']['reused_stages']['benchmark_review']
            if change == 'workaround': altered['policy_profile']['targeted_migration'] = {}
            altered['policy_sha256'] = policy_cli.canonical_hash(altered, 'policy_sha256')
            with self.subTest(change=change):
                self.assertTrue(schema_errors(altered, 'evaluation-policy-v4.schema.json'))

    def test_cli_verifies_evidence_and_never_overwrites_preserved_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = deepcopy(self.source)
            refs = [source['retrospective_migration']['original_policy']['artifact']]
            refs += [row['evidence'][0] for row in source['retrospective_migration']['reused_stages'].values()]
            for ref in refs:
                content = json.dumps(self.original if ref['path']=='original.json' else {'archived':ref['path']}).encode()
                (root/ref['path']).write_bytes(content)
                ref['sha256'] = hashlib.sha256(content).hexdigest()
            (root/'input.json').write_text(json.dumps(source))
            command = [sys.executable, str(Path(policy_cli.__file__)), 'build', '--input', str(root/'input.json'), '--original-policy', str(root/'original.json'), '--output']
            good = subprocess.run(command+[str(root/'new.json')], capture_output=True, text=True)
            self.assertEqual(0, good.returncode, good.stdout+good.stderr)
            original_bytes = (root/'original.json').read_bytes()
            blocked = subprocess.run(command+[str(root/'original.json'),'--force'], capture_output=True, text=True)
            self.assertNotEqual(0, blocked.returncode)
            self.assertEqual(original_bytes, (root/'original.json').read_bytes())
            (root/'benchmark_review.json').write_text('{}')
            bad = subprocess.run(command+[str(root/'bad.json')], capture_output=True, text=True)
            self.assertNotEqual(0, bad.returncode)
            self.assertIn('evidence hash mismatch', bad.stdout)
            self.assertFalse((root/'bad.json').exists())

    def test_all_six_dimensions_gates_and_validity_are_invariant(self):
        fixture = completion.CurrentV8CompletionTests()
        fixture.setUp()
        try:
            registered = fixture.run_cli('register-structure', '--state', str(fixture.state_path), '--input', str(fixture.structure_path))
            self.assertEqual(0, registered.returncode, registered.stdout)
            state = json.loads(fixture.state_path.read_text())
            loaded, *_ = dimensions._calculation_loaded_from_state(state, fixture.state_path, fixture.root/'input.json')
            before = dimensions.calculate_loaded(loaded)
            original = json.loads((fixture.root/'evaluation-policy.json').read_text())
            source = migration_input(original)
            source['retrospective_migration']['migrated_at'] = '2099-01-01T00:00:00Z'
            migrated = self.build(source, original, original | {'policy_id':'BASE', 'policy_sha256': policy_cli.canonical_hash(original | {'policy_id':'BASE'}, 'policy_sha256')})
            old_hash, new_hash = original['policy_sha256'], migrated['policy_sha256']
            def rebind(value):
                if isinstance(value, dict): return {k: rebind(v) for k,v in value.items()}
                if isinstance(value, list): return [rebind(v) for v in value]
                return new_hash if value == old_hash else value
            revised = rebind(loaded)
            revised['policy'] = migrated
            after = dimensions.calculate_loaded(revised)
            for field in ('dimensions', 'overall_percentage', 'final_rounding', 'status', 'diagnostic_item_grades'):
                self.assertEqual(before[field], after[field], field)
            self.assertEqual(dimensions._critical_gate_outcomes(original, loaded['structure'], before), dimensions._critical_gate_outcomes(migrated, revised['structure'], after))
            self.assertEqual(dimensions._evaluation_validity(original, loaded['structure'], before), dimensions._evaluation_validity(migrated, revised['structure'], after))
        finally:
            fixture.tearDown()
