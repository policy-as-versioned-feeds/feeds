"""Standalone shadow direct recovery-expense converter; no institutional threat/fine pricing."""
import argparse
import json
import sys


ACCOUNTING = {
    'unit_basis': 'nominal direct security-incident recovery expense per registered subject-year',
    'included': ['Incremental incident-response and restoration labour at an agreed charge-out rule, supported by worklogs',
                 'Actual incremental restoration/vendor invoices allocated once to a registered cost centre'],
    'excluded': ['Routine controls and already-budgeted operating cost',
                 'Missed sales, fines, premiums, customer/patient losses',
                 'Double-counted shared incident costs, forecast-generated outcomes and synthetic tests'],
    'allocation': 'Allocate each independently evidenced source cost once across registered cost centres; disclose shared incidents and dependence.',
    'recognition': 'Recognize eligible expense by incurred UTC date in the registered subject-year, not incident onset, payment or recording date. Annual frequency counts incidents with eligible recovery activity in that year, including carry-in; severity is only their eligible within-year incremental direct expense, excluding carry-out.',
    'completeness': 'Complete cost-centre incident ledger plus attributable invoices/worklogs and an independent final completeness attestation; an empty log is not zero.',
    'finality': 'Year-end independent reconciliation and signed final/complete record; unresolved or disputed amounts are ineligible. Closing within 31 days is a process target.'}


class _AdapterRefused(ValueError):
    pass


def _adapter_object(value, required, optional=(), where='object'):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or not set(required) <= set(value):
        raise _AdapterRefused(f'{where}: missing or unknown fields')
    return value


def _adapter_text(value, where):
    if not isinstance(value, str) or not value.strip():
        raise _AdapterRefused(f'{where}: a nonempty string is required')
    return value


def _adapter_path(value):
    import re
    value = _adapter_text(value, 'source path')
    parts = value.split('/')
    if any(part in ('', '.', '..', '.git') for part in parts) or '\\' in value or '\x00' in value or re.match(r'^[A-Za-z]:', value):
        raise _AdapterRefused('source path: a strict relative publisher path is required')
    return parts


def _adapter_ref(value, where):
    import re
    value = _adapter_object(value, ('party', 'tag', 'commit', 'path', 'git_blob'), where=where)
    for field in ('party', 'tag'):
        _adapter_text(value[field], where + '.' + field)
    _adapter_path(value['path'])
    for field in ('commit', 'git_blob'):
        if not isinstance(value[field], str) or not re.fullmatch('[0-9a-f]{40}', value[field]):
            raise _AdapterRefused(where + '.' + field + ': exact Git object required')
    return value


def _adapter_read(path, publisher_relative=False):
    import os
    import stat
    if publisher_relative:
        parts = _adapter_path(path)
        descriptor = os.open('.', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in parts[:-1]:
                next_descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            file_descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        finally:
            os.close(descriptor)
    else:
        file_descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(file_descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise _AdapterRefused('input is not a regular file')
        if info.st_size > 33554432:
            raise _AdapterRefused('resource-limit: JSON record exceeds 32 MiB')
        raw = stream.read(33554433)
        if len(raw) > 33554432:
            raise _AdapterRefused('resource-limit: JSON record exceeds 32 MiB')
        return raw


def _adapter_json(raw):
    import math
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise _AdapterRefused('duplicate JSON key')
            out[key] = value
        return out
    def integer(text):
        if len(text.lstrip('-')) > 2500:
            raise _AdapterRefused('resource-limit: JSON integer')
        if text == '-0':
            raise _AdapterRefused('negative zero is not a monetary value')
        return int(text)
    def decimal(text):
        mantissa, _, exponent = text.lower().partition('e')
        if len(mantissa.replace('.', '').lstrip('-0')) > 128 or (exponent and (len(exponent.lstrip('+-0')) > 3 or abs(int(exponent)) > 128)):
            raise _AdapterRefused('resource-limit: JSON decimal')
        number = float(text)
        if not math.isfinite(number) or (number == 0 and text.startswith('-')):
            raise _AdapterRefused('nonfinite or negative-zero JSON number')
        return number
    def constant(text):
        raise _AdapterRefused('nonfinite JSON literal')
    value = json.loads(raw, object_pairs_hook=pairs, parse_int=integer, parse_float=decimal, parse_constant=constant)
    def depth(item, level=0):
        if level > 32:
            raise _AdapterRefused('resource-limit: JSON depth')
        if isinstance(item, dict):
            for child in item.values():
                depth(child, level + 1)
        elif isinstance(item, list):
            for child in item:
                depth(child, level + 1)
    depth(value)
    return value


def _adapter_number(value):
    import math
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise _AdapterRefused('scenario requires finite nonnegative numbers, not booleans')


def _adapter_triple(value):
    if not isinstance(value, list) or len(value) != 3:
        raise _AdapterRefused('only bounded PERT triples are supported')
    for number in value:
        _adapter_number(number)
    if not value[0] <= value[1] <= value[2]:
        raise _AdapterRefused('PERT triple must be ordered min <= mode <= max')


def _adapter_scenario(value):
    _adapter_object(value, ('version', 'name', 'warn', 'deny'), ('note',), 'scenario')
    for field in ('version', 'name'):
        _adapter_text(value[field], 'scenario.' + field)
    if 'note' in value and not isinstance(value['note'], str):
        raise _AdapterRefused('scenario.note must be text')
    for state in ('warn', 'deny'):
        half = _adapter_object(value[state], ('lef', 'lm'), where='scenario.' + state)
        _adapter_triple(half['lef'])
        lm = half['lm']
        if not isinstance(lm, list) or not lm:
            raise _AdapterRefused('scenario must have a nonempty bounded PERT source arrangement')
        for triple in lm if isinstance(lm[0], list) else [lm]:
            _adapter_triple(triple)
    return value


def _publisher_widen(payload, context, publisher, version_key, authority):
    import hashlib
    import re
    from datetime import date
    _adapter_object(context, ('schema', 'target', 'profile', 'widening', 'adopter_party',
                             'adopter_context', 'base_scenario', 'state', 'financial_as_of'), where='widen context')
    if context['schema'] != 'publisher-reliability/widen-context-v1' or context['state'] != 'warn':
        raise _AdapterRefused('unsupported widening context or state')
    for field in ('target', 'profile', 'widening'):
        _adapter_ref(context[field], field)
    adopter = context['adopter_context']
    if isinstance(adopter, dict) and set(adopter) == {'path', 'git_blob'}:
        _adapter_path(adopter['path'])
        if not isinstance(adopter['git_blob'], str) or not re.fullmatch('[0-9a-f]{40}', adopter['git_blob']):
            raise _AdapterRefused('adopter_context requires an exact same-tree Git blob')
    else:
        _adapter_ref(adopter, 'adopter_context')
        if adopter['party'] != context['adopter_party']:
            raise _AdapterRefused('adopter_context party differs from adopter_party')
    _adapter_text(context['adopter_party'], 'adopter_party')
    if context['target']['party'] != publisher or context['widening']['party'] != publisher:
        raise _AdapterRefused('widening and target must belong to this publisher')
    day = context['financial_as_of']
    if not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise _AdapterRefused('financial_as_of requires an exact Gregorian date')
    date.fromisoformat(day)
    raw = _adapter_read(context['widening']['path'], publisher_relative=True)
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if blob != context['widening']['git_blob']:
        raise _AdapterRefused('widening declaration Git blob differs from its source reference')
    declaration = _adapter_json(raw)
    _adapter_object(declaration, ('schema', 'id', 'profile_id', 'unit', 'authority',
                    'authoritative_value_action', 'affected_sources', 'citation', 'release_cage', 'target'), where='widening declaration')
    if (declaration['schema'] != 'publisher-reliability/widening-v1' or declaration['authority'] != authority
            or declaration['authoritative_value_action'] != 'preserve'):
        raise _AdapterRefused('widening cannot change publisher authority or authoritative values')
    for field in ('id', 'profile_id', 'citation'):
        _adapter_text(declaration[field], 'widening.' + field)
    unit = _adapter_object(declaration['unit'], ('currency', 'basis'), where='unit')
    if not isinstance(unit['currency'], str) or not re.fullmatch('[A-Z]{3}', unit['currency']):
        raise _AdapterRefused('unit requires an explicit currency')
    _adapter_text(unit['basis'], 'unit.basis')
    cage = _adapter_object(declaration['release_cage'], ('path', 'git_blob'), where='release_cage')
    _adapter_path(cage['path'])
    if not isinstance(cage['git_blob'], str) or not re.fullmatch('[0-9a-f]{40}', cage['git_blob']):
        raise _AdapterRefused('release_cage requires an exact Git blob')
    base, target = _adapter_scenario(context['base_scenario']), _adapter_scenario(declaration['target'])
    if not isinstance(payload, dict) or 'payload' in payload or payload.get(version_key) != base['version']:
        raise _AdapterRefused('unwrapped publisher payload does not match the base scenario version')
    if any(target[key] != base[key] for key in ('version', 'name')):
        raise _AdapterRefused('widening must preserve scenario identity and version')
    affected = declaration['affected_sources']
    if not isinstance(affected, list) or any(not isinstance(path, str) for path in affected) or len(set(affected)) != len(affected):
        raise _AdapterRefused('affected_sources must be unique LM source paths')
    allowed, changed = set(), set()
    for state in ('warn', 'deny'):
        if target[state]['lef'] != base[state]['lef']:
            raise _AdapterRefused('widening must preserve each state LEF')
        old, new = base[state]['lm'], target[state]['lm']
        nested = isinstance(old[0], list)
        if nested != isinstance(new[0], list) or len(old) != len(new):
            raise _AdapterRefused('widening must preserve the LM source arrangement')
        prefix = '/' + state + '/lm'
        allowed.add(prefix)
        for index, (before, after) in enumerate(zip(old, new)) if nested else [(None, (old, new))]:
            pointer = prefix + '/' + str(index) if nested else prefix
            allowed.add(pointer)
            if any(a < b for a, b in zip(after, before)):
                raise _AdapterRefused('widening LM cannot narrow any base component')
            if after != before:
                changed.add(pointer)
    if not set(affected) <= allowed or any(path not in affected and path.rsplit('/', 1)[0] not in affected for path in changed):
        raise _AdapterRefused('affected_sources do not account for the exact LM changes')
    return {'schema': 'publisher-reliability/widen-result-v1', 'target_id': declaration['id'],
            'profile_id': declaration['profile_id'], 'scenario': target,
            'authority_action': 'preserve', 'affected_sources': affected}


def _generator_document(context, publisher, feed_name):
    _adapter_object(context, ('schema', 'source', 'document'), where='generator context')
    if context['schema'] != 'publisher-reliability/generator-context-v1':
        raise _AdapterRefused('unsupported generator context')
    _adapter_ref(context['source'], 'generator source')
    document = context['document']
    if not isinstance(document, dict):
        raise _AdapterRefused('generator document must be the full parsed party object')
    _adapter_text(document.get('party'), 'generator document.party')
    if document['party'] != context['source']['party']:
        raise _AdapterRefused('generator context party differs from its source')
    edges = document.get('inherits')
    if not isinstance(edges, list):
        raise _AdapterRefused('generator context lacks its actual selected feed edge')
    selected = [edge for edge in edges if isinstance(edge, dict)
                and edge.get('party') == publisher and edge.get('kind') == 'feed'
                and edge.get('name') == feed_name]
    if len(selected) != 1:
        raise _AdapterRefused('generator context requires one exact selected feed edge')
    _adapter_text(selected[0].get('version'), 'selected feed version')
    return document


def recovery_scenario(payload, institution):
    """A separate prospective institution-year model; no inherited threat/fine inputs."""
    import re
    from datetime import date
    _adapter_object(payload, ('model', 'scope', 'feed_version', 'published_by', 'currency', 'note',
                             'accounting', 'institutions'), ('release_cage',), 'recovery payload')
    if (payload['model'] != 'direct-security-recovery-expense/v1' or payload['scope'] != 'shadow-collection-only'
            or payload['published_by'] != 'feeds' or payload['currency'] != 'GBP'
            or payload['feed_version'] != 'v1'):
        raise _AdapterRefused('recovery model requires its explicit GBP major-1 publisher identity')
    _adapter_text(payload['note'], 'recovery note')
    accounting = _adapter_object(payload['accounting'],
        ('unit_basis', 'included', 'excluded', 'allocation', 'recognition', 'completeness', 'finality', 'collection_policy_sha256'),
        where='recovery accounting')
    if accounting['unit_basis'] != 'nominal direct security-incident recovery expense per registered subject-year':
        raise _AdapterRefused('recovery unit is not the declared institutional direct-expense outcome')
    for name in ('included', 'excluded'):
        if not isinstance(accounting[name], list) or not accounting[name]:
            raise _AdapterRefused('recovery accounting requires explicit included/excluded categories')
        for item in accounting[name]:
            _adapter_text(item, 'accounting.' + name)
    for name in ('allocation', 'recognition', 'completeness', 'finality'):
        _adapter_text(accounting[name], 'accounting.' + name)
    if not isinstance(accounting['collection_policy_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', accounting['collection_policy_sha256']):
        raise _AdapterRefused('recovery accounting requires its exact collection-policy digest')
    if {k: v for k, v in accounting.items() if k != 'collection_policy_sha256'} != ACCOUNTING:
        raise _AdapterRefused('recovery accounting boundary differs from the direct-expense contract')
    institutions = _adapter_object(payload['institutions'], ('driftwood', 'tuppence', 'ludlow'),
                                   where='recovery institutions')
    if institution not in institutions:
        raise _AdapterRefused('recovery case has no explicit institution-level model')
    for party, value in institutions.items():
        row = _adapter_object(value, ('lef', 'lm_gbp', 'lef_basis', 'lm_basis', 'cost_centres',
                                     'parameter_source'), where='recovery institution ' + party)
        if row['parameter_source'] != 'institution-level-owner-planning':
            raise _AdapterRefused('recovery parameters cannot be observed claims or summed workload contingencies')
        _adapter_triple(row['lef'])
        _adapter_triple(row['lm_gbp'])
        centres = row['cost_centres']
        if (not isinstance(centres, list) or not centres
                or any(not isinstance(c, str) or not c.strip() for c in centres)
                or len(set(centres)) != len(centres)):
            raise _AdapterRefused('recovery requires explicit unique institutional cost centres')
        for field in ('lef_basis', 'lm_basis'):
            basis = _adapter_object(row[field], ('kind', 'statement', 'as_of'), where=field)
            if basis['kind'] != 'normative-planning-unvalidated':
                raise _AdapterRefused('recovery parameters are normative unvalidated planning inputs')
            _adapter_text(basis['statement'], field + '.statement')
            if not isinstance(basis['as_of'], str) or not re.fullmatch('[0-9]{4}-[0-9]{2}-[0-9]{2}', basis['as_of']):
                raise _AdapterRefused('recovery parameter basis requires an exact date')
            date.fromisoformat(basis['as_of'])
    row = institutions[institution]
    lef = list(row['lef'])
    lm = list(row['lm_gbp'])
    return {'version': payload['feed_version'],
            'name': 'recovery-expense:' + payload['feed_version'] + ' direct-security-recovery ' + institution,
            'warn': {'lef': lef, 'lm': lm}, 'deny': {'lef': list(lef), 'lm': list(lm)},
            'note': 'Separate institution-year direct recovery-expense planning model. '
                    'No empirical calibration or control-effectiveness credit. '
                    + row['lef_basis']['statement'] + ' ' + row['lm_basis']['statement']}


def _publisher_command(mode, payload_path, context_path, publisher, version_key, authority):
    try:
        payload = _adapter_json(_adapter_read(payload_path))
        context = _adapter_json(_adapter_read(context_path))
        if mode == 'widen-to':
            result = _publisher_widen(payload, context, publisher, version_key, authority)
        else:
            result = _publisher_forecast_base(payload, context)
            _adapter_scenario(_adapter_json(json.dumps(result, allow_nan=False).encode()))
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        sys.exit(f'{mode}: invalid publisher instrument: {error}')


def _publisher_forecast_base(payload, context):
    document = _generator_document(context, 'feeds', 'recovery-expense')
    return recovery_scenario(payload, document['party'])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3 or argv[0] not in ('forecast-base', 'widen-to'):
        raise SystemExit('expected forecast-base|widen-to payload.json context.json')
    _publisher_command(argv[0], argv[1], argv[2], 'feeds', 'feed_version', 'publisher-loss-model')


if __name__ == '__main__':
    main()
