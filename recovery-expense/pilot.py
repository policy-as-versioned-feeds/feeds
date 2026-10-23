"""Build/check unsigned prospective recovery model bundles from explicit inputs only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

jsonschema = None
yaml = None


class MissingInstrument(RuntimeError):
    pass


def dependencies():
    global jsonschema, yaml
    try:
        import jsonschema as schema_module
        import yaml as yaml_module
    except ImportError as error:
        raise MissingInstrument("bundle validation requires pinned PyYAML and jsonschema; install requirements.txt") from error
    jsonschema, yaml = schema_module, yaml_module

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('_recovery_publisher_converter', HERE / 'to_fair_scenario.py')
converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(converter)
PARTIES = ('driftwood', 'tuppence', 'ludlow')
BASIS = 'nominal direct security-incident recovery expense per registered subject-year'
ACCOUNTING = converter.ACCOUNTING
SCHEMA_PATH = 'recovery-expense/payload.schema.json'
PROFILE_PATH = 'recovery-expense/recovery-2027/profile.json'
CASES_PATH = 'recovery-expense/recovery-2027/cases.json'
COLLECTION_PATH = 'recovery-expense/recovery-2027/collection-policy.json'


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def read(path):
    return converter._adapter_json(Path(path).read_bytes())


def policy_digest(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_collection_policy(parameters, policy):
    from decimal import Decimal
    converter._adapter_object(policy, ('schema', 'unit', 'cost_centres', 'labour_rates_gbp_per_hour', 'operator_control_disclosure'), where='collection policy')
    if policy['schema'] != 'recovery-expense/accounting-policy-v1' or policy['unit'] != {'currency': 'GBP', 'basis': BASIS}:
        raise ValueError('matching direct recovery collection unit is required')
    converter._adapter_object(policy['cost_centres'], PARTIES, where='collection cost centres')
    converter._adapter_object(policy['labour_rates_gbp_per_hour'], PARTIES, where='pre-agreed rates')
    converter._adapter_text(policy['operator_control_disclosure'], 'shared operator/control disclosure')
    for party in PARTIES:
        if parameters[party]['cost_centres'] != policy['cost_centres'][party]:
            raise ValueError('model and collector institutional cost-centre boundaries differ')
        rate = policy['labour_rates_gbp_per_hour'][party]
        if not isinstance(rate, str) or not re.fullmatch(r'(0|[1-9][0-9]{0,15})(\.[0-9]{1,8})?', rate) or Decimal(rate) <= 0:
            raise ValueError('explicit positive exact-decimal charge-out rates are required')
    return policy


def model_payload(parameters, version, collection_policy):
    """All institution-level frequency/severity/basis/centres must be supplied."""
    dependencies()
    if not re.fullmatch(r'1\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('the separate recovery model requires an explicit canonical major-1 version')
    validate_collection_policy(parameters, collection_policy)
    payload = {'model': 'direct-security-recovery-expense/v1', 'scope': 'shadow-collection-only', 'feed_version': 'v1',
               'published_by': 'feeds', 'currency': 'GBP',
               'note': 'Prospective normative institution-year planning model; unvalidated parameters, no observed expense or effectiveness claim.',
               'accounting': copy.deepcopy(ACCOUNTING), 'institutions': copy.deepcopy(parameters)}
    payload['accounting']['collection_policy_sha256'] = policy_digest(collection_policy)
    for party in PARTIES:
        converter.recovery_scenario(payload, party)
    schema = json.loads((HERE / 'payload.schema.json').read_text())
    jsonschema.Draft7Validator(schema).validate(payload)
    return payload


def _source_ref(value, party=None):
    converter._adapter_ref(value, 'required actual source reference')
    if party is not None and value['party'] != party:
        raise ValueError('source reference belongs to the wrong party')
    if value['commit'] == '0' * 40 or value['git_blob'] == '0' * 40:
        raise ValueError('placeholder source references refuse')
    return copy.deepcopy(value)


def candidate_bundle(*, parameters, version, published_at, contexts, engine, discovery, resolver_evidence_prefix, collection_policy):
    """Construct artifacts, never authenticate, register, simulate, sign or publish them."""
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', published_at):
        raise ValueError('published_at is an explicit UTC assertion, not an inferred current clock')
    from datetime import datetime
    datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%SZ')
    if published_at >= '2027-01-01T00:00:00Z':
        raise ValueError('the 2027 profile requires genuine registration before its horizon; choose a separately reviewed later horizon')
    payload = model_payload(parameters, version, collection_policy)
    if set(contexts) != set(PARTIES):
        raise ValueError('all three actual institution party.yaml references are required')
    if not resolver_evidence_prefix.startswith('https://github.com/policy-as-versioned-platform/platform/'):
        raise ValueError('resolver evidence must use the declared canonical platform authority')
    cases = {'schema': 'publisher-reliability/price-cases-v1', 'profile_id': 'direct-security-recovery-2027', 'cases': []}
    for party in PARTIES:
        context = contexts[party]
        converter._adapter_object(context, ('source', 'document_path'), where='actual signed context input')
        ref = _source_ref(context['source'], party)
        raw = Path(context['document_path']).read_bytes()
        if blob(raw) != ref['git_blob']:
            raise ValueError('context bytes differ from the actual referenced Git blob')
        document = yaml.safe_load(raw)
        if document.get('party') != party or document.get('reporting_currency') != 'GBP':
            raise ValueError('context must be the complete matching GBP institution party document')
        edges = [e for e in document.get('inherits', []) if e.get('party') == 'feeds' and e.get('kind') == 'feed' and e.get('name') == 'recovery-expense']
        if len(edges) != 1 or edges[0].get('version') not in ('v1', '1', version, 'v' + version):
            raise ValueError('context does not actually select this separate recovery model major')
        if ref['path'] != 'party.yaml':
            raise ValueError('each context must be the actual complete party document')
        cases['cases'].append({'case_id': party + '/2027', 'subject': party, 'perspective': party,
            'horizon': {'starts_at': '2027-01-01T00:00:00Z', 'ends_at': '2028-01-01T00:00:00Z', 'boundary': '[start,end)'},
            'context_ref': ref})
    profile = {'schema': 'publisher-reliability/price-profile-v1', 'id': cases['profile_id'],
        'criterion': 'money-empirical-crps/v1', 'outcome_kind': 'annual-aggregate-loss/v1',
        'target_feed': {'publisher': 'feeds', 'name': 'recovery-expense'}, 'unit': {'currency': 'GBP', 'basis': BASIS},
        'definition': {'loss_categories': ACCOUNTING['included'],
                       'accounting_rule': ACCOUNTING['allocation'] + ' Recognition: ' + ACCOUNTING['recognition'] + ' Excluded: ' + '; '.join(ACCOUNTING['excluded']) + ' Collection-policy-sha256=' + policy_digest(collection_policy),
                       'completeness_rule': ACCOUNTING['completeness'], 'finality_rule': ACCOUNTING['finality']},
        'horizon_rule': {'duration': 'P1Y', 'boundary': '[start,end)', 'calendar': 'UTC-Gregorian'},
        'resolver_rule': {'party': 'platform', 'source_schema': 'recovery-expense/resolution-source-v1',
                          'amount_pointer': '/amount', 'finality_pointer': '/final', 'completeness_pointer': '/complete',
                          'evidence_uri_prefix': resolver_evidence_prefix},
        'population': {'case_inventory': {'path': CASES_PATH, 'git_blob': blob(canonical(cases))},
                       'registration_deadline': 'strictly-before-horizon-start', 'aggregation': 'equal-case-mean',
                       'overlap_rule': 'distinct-case-subject-horizon-no-overlap'},
        'generator': {'kind': 'pinned-fair-annual-empirical/v1', 'engine': _source_ref(engine, 'platform'),
                      'state': 'warn', 'parameter_policy': 'explicit-per-registration-recorded-not-inferred'}}
    if discovery != yaml.safe_load((HERE.parent / 'party.yaml').read_text()):
        raise ValueError('bundle must conserve the actual complete publisher discovery source')
    party = copy.deepcopy(discovery)
    if party.get('party') != 'feeds':
        raise ValueError('publisher discovery must be the actual complete feeds party document')
    selected = [p for p in party.get('publishes', []) if p.get('kind') == 'feed' and p.get('name') == 'recovery-expense']
    if (len(selected) != 1 or selected[0].get('path') != 'recovery-expense'
            or selected[0].get('payload_schema') != SCHEMA_PATH):
        raise ValueError('discovery must expose the existing exact recovery-expense family')
    envelope = {'kind': 'feed', 'name': 'recovery-expense', 'version': version, 'published_by': 'feeds',
                'published_at': published_at, 'payload_schema': SCHEMA_PATH, 'payload': payload}
    return {f'recovery-expense/v1/feed.json': canonical(envelope), SCHEMA_PATH: (HERE / 'payload.schema.json').read_bytes(),
            'recovery-expense/to_fair_scenario.py': (HERE / 'to_fair_scenario.py').read_bytes(),
            'recovery-expense/rule.yaml': (HERE / 'rule.yaml').read_bytes(),
            'recovery-expense/bump.yaml': (HERE / 'bump.yaml').read_bytes(),
            'party.yaml': yaml.safe_dump(party, sort_keys=False).encode(), CASES_PATH: canonical(cases), PROFILE_PATH: canonical(profile),
            COLLECTION_PATH: canonical(collection_policy)}


def contracts(nist_root=None):
    pinned = HERE / 'contracts'
    manifest = json.loads((pinned / 'UPSTREAM.json').read_text())
    supplied = Path(nist_root) / 'publisher-reliability' if nist_root is not None else pinned
    for file in manifest['files']:
        actual = supplied / file['vendored_path']
        raw = actual.read_bytes()
        if hashlib.sha256(raw).hexdigest() != file['sha256'] or blob(raw) != file['git_blob']:
            raise ValueError('supplied SDK contracts differ from the exact pinned NIST source')
    return supplied


def check_bundle(root, nist_root=None):
    """Check complete same-tree artifact coupling; genuine SDK authority remains separate."""
    dependencies()
    root = Path(root)
    contract = contracts(nist_root)
    envelope = read(root / 'recovery-expense/v1/feed.json')
    if not re.fullmatch(r'1\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', envelope.get('version', '')):
        raise ValueError('bundle must carry the separate canonical major-1 envelope')
    jsonschema.Draft7Validator(json.loads((contract / 'envelope.schema.json').read_text())).validate(envelope)
    if (envelope['kind'] != 'feed' or envelope['payload_schema'] != SCHEMA_PATH
            or envelope['name'] != 'recovery-expense' or envelope['published_by'] != 'feeds'):
        raise ValueError('bundle envelope target/schema mismatch')
    if root.joinpath('recovery-expense/to_fair_scenario.py').read_bytes() != (HERE / 'to_fair_scenario.py').read_bytes():
        raise ValueError('bundle converter is not the actual matching publisher source')
    schema = read(root / SCHEMA_PATH)
    if schema != read(HERE / 'payload.schema.json'):
        raise ValueError('bundle recovery schema differs from the implemented contract')
    jsonschema.Draft7Validator(schema).validate(envelope['payload'])
    discovery = yaml.safe_load((root / 'party.yaml').read_text())
    if discovery != yaml.safe_load((HERE.parent / 'party.yaml').read_text()):
        raise ValueError('bundle discovery mismatch with the complete implemented publisher source')
    for sidecar in ('rule.yaml', 'bump.yaml'):
        if (root / 'recovery-expense' / sidecar).read_bytes() != (HERE / sidecar).read_bytes():
            raise ValueError('bundle release sidecar differs from the source; no comparison is claimed')
    publication = [x for x in discovery['publishes'] if x.get('kind') == 'feed' and x.get('name') == 'recovery-expense']
    if len(publication) != 1 or publication[0]['payload_schema'] != envelope['payload_schema'] or publication[0]['path'] != 'recovery-expense':
        raise ValueError('bundle target/schema/discovery mismatch')
    shapes = json.loads((contract / 'price-payload.schema.json').read_text())
    profile = read(root / PROFILE_PATH)
    cases = read(root / CASES_PATH)
    collection_policy = read(root / COLLECTION_PATH)
    validate_collection_policy(envelope['payload']['institutions'], collection_policy)
    digest = policy_digest(collection_policy)
    if envelope['payload']['accounting'] != {**ACCOUNTING, 'collection_policy_sha256': digest}:
        raise ValueError('payload substitutes the accepted direct-expense accounting definition')
    if envelope['payload']['accounting']['collection_policy_sha256'] != digest or ('Collection-policy-sha256=' + digest) not in profile['definition']['accounting_rule']:
        raise ValueError('model/profile/collector accounting-policy identity differs')
    for name, value in [('profile', profile), ('case_inventory', cases)]:
        validator = jsonschema.Draft202012Validator({**shapes, '$ref': '#/$defs/' + name})
        validator.validate(value)
    if profile['population']['case_inventory'] != {'path': CASES_PATH, 'git_blob': blob((root / CASES_PATH).read_bytes())}:
        raise ValueError('case inventory same-tree identity mismatch')
    if (profile['id'] != 'direct-security-recovery-2027' or profile['id'] != cases['profile_id']
            or {x['subject'] for x in cases['cases']} != set(PARTIES) or len(cases['cases']) != 3):
        raise ValueError('the complete three-case population is required')
    upstream = json.loads((contract / 'PRICE-UPSTREAM.json').read_text())
    expected_engine = {'party': 'platform', 'tag': upstream['tag'], 'commit': upstream['commit'],
                       'path': 'fair/fair.py', 'git_blob': next(f['git_blob'] for f in upstream['files'] if f['path'] == 'fair/fair.py')}
    if profile['generator']['engine'] != expected_engine:
        raise ValueError('profile does not name the existing SDK fixed released engine')
    if profile['target_feed'] != {'publisher': 'feeds', 'name': 'recovery-expense'} or profile['unit'] != {'currency': 'GBP', 'basis': BASIS}:
        raise ValueError('profile does not preserve the exact direct-recovery target/unit')
    if (profile['resolver_rule'] != {'party': 'platform', 'source_schema': 'recovery-expense/resolution-source-v1',
            'amount_pointer': '/amount', 'finality_pointer': '/final', 'completeness_pointer': '/complete',
            'evidence_uri_prefix': profile['resolver_rule']['evidence_uri_prefix']}
            or not profile['resolver_rule']['evidence_uri_prefix'].startswith(
                'https://github.com/policy-as-versioned-platform/platform/')):
        raise ValueError('profile differs from the independent collector resolution interface')
    expected_definition = {'loss_categories': ACCOUNTING['included'],
        'accounting_rule': ACCOUNTING['allocation'] + ' Recognition: ' + ACCOUNTING['recognition'] + ' Excluded: ' + '; '.join(ACCOUNTING['excluded']) + ' Collection-policy-sha256=' + digest,
        'completeness_rule': ACCOUNTING['completeness'], 'finality_rule': ACCOUNTING['finality']}
    if profile['definition'] != expected_definition:
        raise ValueError('profile and collector outcome accounting boundaries differ')
    if profile['criterion'] != 'money-empirical-crps/v1' or profile['horizon_rule'] != {
            'duration': 'P1Y', 'boundary': '[start,end)', 'calendar': 'UTC-Gregorian'}:
        raise ValueError('profile criterion or annual horizon differs')
    for case in cases['cases']:
        if (case['subject'] != case['perspective'] or case['case_id'] != case['subject'] + '/2027'
                or case['context_ref']['party'] != case['subject'] or case['context_ref']['path'] != 'party.yaml'
                or case['horizon'] != {'starts_at': '2027-01-01T00:00:00Z', 'ends_at': '2028-01-01T00:00:00Z', 'boundary': '[start,end)'}):
            raise ValueError('case identity/context/annual horizon mismatch')
        _source_ref(case['context_ref'], case['subject'])
        converter.recovery_scenario(envelope['payload'], case['subject'])
    return {'state': 'unsigned-unregistered-candidate-only', 'artifacts_coupled': True,
            'cases': 3, 'minimum_final_complete_cases': 3, 'adopter_bar': '-1000',
            'no_forecast_registration_engine_or_outcome_created': True,
            'still_required': ['actual signed model/profile/context/engine authority and SDK admission',
                               'genuine pre-horizon immutable forecast registration with explicit seed/iterations',
                               'publisher-owned full widening target and genuine native release cage',
                               'independent final/complete worklogs/invoices and resolution source']}


def widening_target(scenario):
    """Publisher-owned full target; no consumer multiplier and no proof assertion."""
    converter._adapter_scenario(scenario)
    if scenario['version'] != 'v1' or not scenario['name'].startswith('recovery-expense:v1 direct-security-recovery '):
        raise ValueError('widening must belong to the separate direct-recovery model')
    result = copy.deepcopy(scenario)
    for state in ('warn', 'deny'):
        result[state]['lm'] = [2 * value for value in scenario[state]['lm']]
    converter._adapter_scenario(result)
    return result


def widening_declaration(scenario, *, profile_id, identifier, release_cage, citation):
    converter._adapter_object(release_cage, ('path', 'git_blob'), where='actual same-tree release cage')
    converter._adapter_path(release_cage['path'])
    if not isinstance(release_cage['git_blob'], str) or not re.fullmatch('[0-9a-f]{40}', release_cage['git_blob']) or release_cage['git_blob'] == '0' * 40:
        raise ValueError('an actual release-cage Git blob is required; this constructor supplies no native proof')
    for value in (profile_id, identifier, citation):
        converter._adapter_text(value, 'widening identity/citation')
    return {'schema': 'publisher-reliability/widening-v1', 'id': identifier, 'profile_id': profile_id,
            'unit': {'currency': 'GBP', 'basis': BASIS}, 'authority': 'publisher-loss-model',
            'authoritative_value_action': 'preserve', 'affected_sources': ['/warn/lm', '/deny/lm'],
            'citation': citation, 'release_cage': copy.deepcopy(release_cage), 'target': widening_target(scenario)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('bundle', help='build/check a new private unsigned candidate, never enroll it')
    for name in ['parameters', 'contexts', 'engine', 'discovery', 'output', 'version', 'published-at', 'resolver-evidence-prefix', 'collection-policy']:
        b.add_argument('--' + name, required=True)
    b.add_argument('--nist-root')
    c = sub.add_parser('check-bundle')
    c.add_argument('root'); c.add_argument('--nist-root')
    a = p.parse_args(argv)
    try:
        dependencies()
        if a.command == 'bundle':
            files = candidate_bundle(parameters=read(a.parameters), version=a.version, published_at=a.published_at,
                contexts=read(a.contexts), engine=read(a.engine), discovery=yaml.safe_load(Path(a.discovery).read_text()),
                resolver_evidence_prefix=a.resolver_evidence_prefix, collection_policy=read(a.collection_policy))
            out = Path(a.output)
            out.mkdir(exist_ok=False)
            for name, raw in files.items():
                f = out / name; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(raw)
            result = check_bundle(out, a.nist_root)
            result['same_tree_artifacts'] = [{'path': n, 'git_blob': blob(raw)} for n, raw in files.items()]
            (out / 'BUNDLE.json').write_bytes(canonical(result))
        else:
            result = check_bundle(a.root, a.nist_root)
        print(json.dumps(result, indent=2))
    except MissingInstrument as error:
        print('SKIP: missing instrument: ' + str(error), file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyError, TypeError, jsonschema.ValidationError) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
