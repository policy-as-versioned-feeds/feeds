"""Synthetic CLI/contract regressions; no actual parameters, authority, draws or outcomes."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('recovery_pilot_test_subject', HERE / 'pilot.py')
pilot = importlib.util.module_from_spec(spec); spec.loader.exec_module(pilot)
NIST = None
CONTRACT = HERE / 'contracts'


class RecoveryPilotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.parameters = {p: {'lef': [0, 1, 2], 'lm_gbp': [10, 20, 30],
            'lef_basis': {'kind': 'normative-planning-unvalidated', 'statement': 'SYNTHETIC TEST ONLY frequency', 'as_of': '2026-10-23'},
            'lm_basis': {'kind': 'normative-planning-unvalidated', 'statement': 'SYNTHETIC TEST ONLY cost severity', 'as_of': '2026-10-23'},
            'cost_centres': [p + '-test-centre'], 'parameter_source': 'institution-level-owner-planning'} for p in pilot.PARTIES}
        self.policy = {'schema': 'recovery-expense/accounting-policy-v1', 'unit': {'currency': 'GBP', 'basis': pilot.BASIS},
            'cost_centres': {p: self.parameters[p]['cost_centres'] for p in pilot.PARTIES},
            'labour_rates_gbp_per_hour': {p: '10' for p in pilot.PARTIES}, 'operator_control_disclosure': 'SYNTHETIC TEST ONLY shared operator, no world independence proof'}
        self.contexts = {}
        for party in pilot.PARTIES:
            f = self.root / (party + '.yaml')
            f.write_text(yaml.safe_dump({'party': party, 'reporting_currency': 'GBP', 'inherits': [{'party': 'feeds', 'kind': 'feed', 'name': 'threat-register', 'version': 'v4'}, {'party': 'ico', 'kind': 'feed', 'name': 'penalty-schema', 'version': 'v3'}, {'party': 'feeds', 'kind': 'feed', 'name': 'recovery-expense', 'version': 'v1'}]}))
            self.contexts[party] = {'source': {'party': party, 'tag': 'TEST-ONLY-UNSIGNED/v1.0.0', 'commit': 'a' * 40,
                'path': 'party.yaml', 'git_blob': pilot.blob(f.read_bytes())}, 'document_path': str(f)}
        u = json.loads((CONTRACT / 'PRICE-UPSTREAM.json').read_text())
        self.engine = {'party': 'platform', 'tag': u['tag'], 'commit': u['commit'], 'path': 'fair/fair.py',
                       'git_blob': next(f['git_blob'] for f in u['files'] if f['path'] == 'fair/fair.py')}

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self):
        return pilot.candidate_bundle(parameters=self.parameters, version='1.0.0', published_at='2026-10-23T00:00:00Z',
            contexts=self.contexts, engine=self.engine, discovery=yaml.safe_load((HERE.parent / 'party.yaml').read_text()),
            resolver_evidence_prefix='https://github.com/policy-as-versioned-platform/platform/', collection_policy=self.policy)

    def save_bundle(self, files):
        out = self.root / 'bundle'
        for name, raw in files.items():
            f = out / name; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(raw)
        return out

    def test_complete_cli_bundle_and_standalone_converter(self):
        paths = {}
        for name, value in [('parameters', self.parameters), ('contexts', self.contexts), ('engine', self.engine), ('collection-policy', self.policy)]:
            f = self.root / (name + '.json'); f.write_text(json.dumps(value)); paths[name] = f
        args = [sys.executable, '-B', str(HERE / 'pilot.py'), 'bundle', '--version', '1.0.0', '--published-at', '2026-10-23T00:00:00Z',
                '--discovery', str(HERE.parent / 'party.yaml'), '--resolver-evidence-prefix',
                'https://github.com/policy-as-versioned-platform/platform/', '--output', str(self.root / 'bundle')]
        for name, path in paths.items(): args.extend(['--' + name, str(path)])
        call = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(call.returncode, 0, call.stderr)
        self.assertEqual(json.loads(call.stdout)['state'], 'unsigned-unregistered-candidate-only')
        root = self.root / 'bundle'; payload = json.loads((root / 'recovery-expense/v1/feed.json').read_text())['payload']
        context = {'schema': 'publisher-reliability/generator-context-v1', 'source': self.contexts['driftwood']['source'],
                   'document': yaml.safe_load(Path(self.contexts['driftwood']['document_path']).read_text())}
        (self.root / 'payload.json').write_text(json.dumps(payload)); (self.root / 'context.json').write_text(json.dumps(context))
        # Exact SDK execution closure: only converter.py, payload and context are supplied.
        (self.root / 'converter.py').write_bytes((HERE / 'to_fair_scenario.py').read_bytes())
        call = subprocess.run([sys.executable, '-I', str(self.root / 'converter.py'), 'forecast-base', str(self.root / 'payload.json'), str(self.root / 'context.json')], capture_output=True, text=True)
        self.assertEqual(call.returncode, 0, call.stderr)
        scenario = json.loads(call.stdout)
        self.assertEqual(scenario['warn'], scenario['deny'])
        self.assertEqual(scenario['warn'], {'lef': [0, 1, 2], 'lm': [10, 20, 30]})
        self.assertIn('No empirical calibration or control-effectiveness credit', scenario['note'])

    def test_required_parameters_and_collection_boundary_refuse(self):
        del self.parameters['ludlow']['lm_gbp']
        with self.assertRaises(ValueError): self.bundle()

    def test_signed_context_selection_and_bytes_are_not_substitutable(self):
        f = Path(self.contexts['driftwood']['document_path']); f.write_text(f.read_text() + '# changed\n')
        with self.assertRaisesRegex(ValueError, 'context bytes'): self.bundle()

    def test_wrong_model_scope_or_currency_or_inferred_workload_parameters_refuse(self):
        self.parameters['driftwood']['parameter_source'] = 'summed-workload-contingencies'
        with self.assertRaisesRegex(ValueError, 'summed workload'): self.bundle()

    def test_schema_discovery_and_accounting_tampering_refuse(self):
        root = self.save_bundle(self.bundle())
        party = yaml.safe_load((root / 'party.yaml').read_text()); next(p for p in party['publishes'] if p['name'] == 'recovery-expense')['payload_schema'] = 'threat-register/payload.schema.v4.json'
        (root / 'party.yaml').write_text(yaml.safe_dump(party))
        with self.assertRaisesRegex(ValueError, 'discovery mismatch'): pilot.check_bundle(root, NIST)

    def test_collector_policy_change_refuses_complete_bundle(self):
        root = self.save_bundle(self.bundle()); f = root / pilot.COLLECTION_PATH
        policy = json.loads(f.read_text()); policy['labour_rates_gbp_per_hour']['driftwood'] = '11'; f.write_text(json.dumps(policy))
        with self.assertRaisesRegex(ValueError, 'accounting definition|policy identity'): pilot.check_bundle(root, NIST)

    def test_help_and_named_missing_instrument_without_optional_dependencies(self):
        call = subprocess.run([sys.executable, '-S', '-B', str(HERE / 'pilot.py'), '--help'], capture_output=True, text=True)
        self.assertEqual(call.returncode, 0, call.stderr)
        call = subprocess.run([sys.executable, '-S', '-B', str(HERE / 'pilot.py'), 'check-bundle', str(self.root)], capture_output=True, text=True)
        self.assertEqual(call.returncode, 3); self.assertIn('SKIP: missing instrument:', call.stderr)

    def test_actual_all_legacy_headline_outputs_are_unchanged(self):
        vectors = json.loads((CONTRACT / 'LEGACY-VECTORS.json').read_text())
        for row in vectors['vectors']:
            with self.subTest(path=row['path'], institution=row['institution']):
                payload = json.loads((HERE.parent / row['path']).read_text())['payload']
                spec = importlib.util.spec_from_file_location('unchanged_threat_converter', HERE.parent / 'threat-register/to_fair_scenario.py')
                legacy = importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
                self.assertEqual(legacy.threat_scenario(payload, row['institution']), row['scenario'])

    def test_full_widening_cli_doubles_only_severity_and_preserves_identity(self):
        payload = self.bundle()['recovery-expense/v1/feed.json']
        payload = json.loads(payload)['payload']
        base = pilot.converter.recovery_scenario(payload, 'driftwood')
        declaration = pilot.widening_declaration(base, profile_id='TEST-ONLY-profile', identifier='TEST-ONLY-widening',
            release_cage={'path': 'TEST-ONLY-cage.json', 'git_blob': 'd' * 40}, citation='SYNTHETIC TEST ONLY no native proof')
        raw = pilot.canonical(declaration); (self.root / 'widening.json').write_bytes(raw)
        reference = {'party': 'feeds', 'tag': 'recovery-expense/v1.0.0', 'commit': 'a' * 40,
                     'path': 'recovery-expense/v1/feed.json', 'git_blob': 'b' * 40}
        context = {'schema': 'publisher-reliability/widen-context-v1', 'target': reference,
            'profile': {**reference, 'path': 'profile.json'},
            'widening': {**reference, 'path': 'widening.json', 'git_blob': pilot.blob(raw)},
            'adopter_party': 'driftwood', 'adopter_context': self.contexts['driftwood']['source'],
            'base_scenario': base, 'state': 'warn', 'financial_as_of': '2026-10-23'}
        (self.root / 'payload.json').write_text(json.dumps(payload)); (self.root / 'context.json').write_text(json.dumps(context))
        call = subprocess.run([sys.executable, '-I', str(HERE / 'to_fair_scenario.py'), 'widen-to', 'payload.json', 'context.json'],
            cwd=self.root, capture_output=True, text=True)
        self.assertEqual(call.returncode, 0, call.stderr)
        actual = json.loads(call.stdout)['scenario']
        self.assertEqual(actual['name'], base['name']); self.assertEqual(actual['version'], base['version'])
        for state in ('warn', 'deny'):
            self.assertEqual(actual[state]['lef'], base[state]['lef'])
            self.assertEqual(actual[state]['lm'], [2*x for x in base[state]['lm']])

    def test_profile_cannot_relabel_outcome_accounting(self):
        root = self.save_bundle(self.bundle()); f = root / pilot.PROFILE_PATH
        profile = json.loads(f.read_text()); profile['definition']['loss_categories'] = ['missed sales']
        f.write_text(json.dumps(profile))
        with self.assertRaisesRegex(ValueError, 'outcome accounting boundaries'):
            pilot.check_bundle(root)

    def test_nonfinite_boolean_or_unordered_model_parameters_refuse(self):
        for triple in [[False, 1, 2], [2, 1, 3], [0, 1, float('inf')]]:
            with self.subTest(triple=triple):
                self.parameters['driftwood']['lef'] = triple
                with self.assertRaises(ValueError): self.bundle()

    def test_full_publisher_widening_preserves_identity_and_frequency(self):
        payload = pilot.model_payload(self.parameters, '1.0.0', self.policy)
        base = pilot.converter.recovery_scenario(payload, 'tuppence')
        wide = pilot.widening_declaration(base, profile_id='direct-security-recovery-2027', identifier='TEST-ONLY-target',
            release_cage={'path': 'TEST-ONLY-no-native-claim.json', 'git_blob': 'b' * 40}, citation='SYNTHETIC TEST ONLY')
        self.assertEqual(wide['target']['name'], base['name']); self.assertEqual(wide['target']['warn']['lef'], base['warn']['lef'])
        self.assertEqual(wide['target']['warn']['lm'], [20, 40, 60]); self.assertEqual(base['warn']['lm'], [10, 20, 30])
        stage = self.root / 'publisher'; stage.mkdir()
        declaration_path = 'widening.json'; raw = pilot.canonical(wide); (stage / declaration_path).write_bytes(raw)
        def ref(party, path, git_blob='c' * 40):
            return {'party': party, 'tag': 'TEST-ONLY-UNSIGNED/v1.0.0', 'commit': 'a' * 40, 'path': path, 'git_blob': git_blob}
        context = {'schema': 'publisher-reliability/widen-context-v1', 'target': ref('feeds', 'recovery-expense/v1/feed.json'),
            'profile': ref('feeds', 'profile.json'), 'widening': ref('feeds', declaration_path, pilot.blob(raw)),
            'adopter_party': 'tuppence', 'adopter_context': {'path': 'party.yaml', 'git_blob': 'd' * 40},
            'base_scenario': base, 'state': 'warn', 'financial_as_of': '2026-10-23'}
        (stage / 'payload.json').write_text(json.dumps(payload)); (stage / 'context.json').write_text(json.dumps(context))
        call = subprocess.run([sys.executable, '-I', str(HERE / 'to_fair_scenario.py'), 'widen-to', 'payload.json', 'context.json'],
                              cwd=stage, capture_output=True, text=True)
        self.assertEqual(call.returncode, 0, call.stderr)
        self.assertEqual(json.loads(call.stdout)['scenario'], wide['target'])

        with self.assertRaisesRegex(ValueError, 'actual release-cage'):
            pilot.widening_declaration(base, profile_id='x', identifier='x', release_cage={'path': 'x', 'git_blob': '0' * 40}, citation='x')


if __name__ == '__main__':
    unittest.main()
