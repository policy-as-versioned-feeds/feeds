#!/usr/bin/env python3
"""to_fair_scenario.py — the threat register's own converter, shipped by its publisher.

Turns one institution's entry in this repository's signed threat-register payload
into a scenario JSON in the (min, mode, max) shape `platform/fair/fair.py`
consumes. Bumping the feed version is the whole diff needed to move the £; no
change to fair.py.

WHY IT LIVES HERE (eco-system ticket 79 item 4, ticket 24). It used to live in
`platform/feeds/to_fair_scenario.py`, in the SUBSCRIBER's repository, and it
carried `THREAT_LM_GBP` — a table keyed on the three adopters' names holding the
impact per loss event for each. So the platform held a signed-looking number
about each institution that no publisher had published, that no subscriber could
re-derive from anything signed, and that a fourth adopter could not have obtained
at all. From payload major 3 the number is in the payload (`institutions.<name>.
lm_gbp`, with `lm_basis`) and the code that reads it is here, beside it.

STANDALONE, ON PURPOSE. This module imports nothing but the standard library and
the ordinary threat command reads only its payload. The explicit reliability
modes additionally read their closed context and selected publisher declaration. `platform/compose/composition.py`
vendors it into each adopter's `composed/feeds/feeds/<version>/` with a
`PROVENANCE.json` recording the exact argv and the sha256 of the scenario it
returned (eco-system ticket 45), and the hub's `verify/portability/` REPLAYS that
argv in a directory holding nothing but this file and the payload. A sibling
import, a relative path or a read of anything outside the payload would break
that replay, which is the point of it.

PRE-MAJOR-3 PAYLOADS. Majors 1 and 2 are published and carry no `lm_gbp`. They
still price, at the same magnitudes, from FROZEN_LM_GBP below — and the scenario
says so by name: a NAMED could-not-look, never a bare number. That table is
frozen: it is the bytes that were in the platform when the move happened, and it
gains no entry ever. A fourth institution on a pre-major-3 payload refuses,
because there is nothing about it to be frozen.

Usage:
    to_fair_scenario.py threat <payload.json> <institution> [-o OUT]
    to_fair_scenario.py selfcheck
"""
from __future__ import annotations

import argparse
import json
import sys

DENY_LEF = (0, 0, 1)   # admission closes the loss path, as every scenario here does

# The magnitudes as platform/feeds/to_fair_scenario.py held them on 2026-09-09,
# byte for byte. Used ONLY for a payload published before `lm_gbp` existed, and
# always named on the scenario. Frozen: nothing is added here.
FROZEN_LM_GBP = {
    "driftwood": (1_000, 4_000, 9_000),
    "tuppence": (5_000, 25_000, 90_000),
    "ludlow": (20_000, 100_000, 400_000),
}
FROZEN_NOTE = (
    "MAGNITUDE UNSOURCED: the impact per event {lm} {currency} is not in payload version "
    "{version}, which predates the publisher's `lm_gbp` field; it is this converter's frozen "
    "copy of the adopter-keyed table that used to live in the SUBSCRIBER's own code "
    "(platform/feeds/to_fair_scenario.py THREAT_LM_GBP). From major 3 the number and its basis "
    "are in the payload. A named could-not-look (eco-system ticket 79 item 4), never a bare "
    "number.")


def _triple(value, what: str, where: str) -> tuple:
    if not (isinstance(value, (list, tuple)) and len(value) == 3):
        sys.exit(f"{where}: {what} is {value!r}, not a (min, mode, max) triple")
    lo, mode, hi = (float(x) for x in value)
    if not lo <= mode <= hi:
        sys.exit(f"{where}: {what} is {value!r}, which is not lo<=mode<=hi")
    return (lo, mode, hi)


def _basis_note(basis, what: str, where: str) -> str:
    """A published number must say what it rests on. One the publisher signs and
    cannot say the source of is a missing instrument (ADR-0020), never a cheaper
    one -- so this refuses rather than annotating it away."""
    if not isinstance(basis, dict) or not basis.get("statement") or not basis.get("as_of"):
        sys.exit(f"{where}: publishes {what} with no basis carrying a `statement` and an "
                 f"`as_of` date. Its basis belongs beside it in the payload "
                 f"(eco-system ticket 79 item 4)")
    note = (f"{what} basis ({basis.get('kind', 'unlabelled')}, read {basis['as_of']}): "
            f"{basis['statement']}")
    if basis.get("could_not_look"):
        note += f" COULD NOT LOOK: {basis['could_not_look']}"
    return note


def _threat_row_scenario(feed: dict, institution: str, entry: dict, threat: str,
                         lm, where: str) -> dict:
    """A row of the institution's `threats` map (payload major 4, eco-system
    ticket 145): a frequency the register publishes, with a magnitude that is
    either the row's own (`lm_gbp`) or the SUBSCRIBER's, handed in by the caller
    and named as such on the scenario. A row with neither refuses by name."""
    version = feed.get("feed_version", "unversioned")
    rows = entry.get("threats") or {}
    if threat not in rows:
        sys.exit(f"{where}: payload version {version} publishes no threats.{threat!r} row (it "
                 f"carries {sorted(rows)}). The row arrives with major 4 (eco-system ticket 145); "
                 f"there is nothing here to price from (ADR-0020)")
    row = rows[threat]
    where = f"{where}.threats.{threat}"
    lef = _triple(row["lef"], "lef", where)
    notes = [f"{row['threat']}."]
    if row.get("actor"):
        notes.append(str(row["actor"]))
    notes.append(_basis_note(row.get("lef_basis"), "Frequency", where))
    if "lm_gbp" in row:
        magnitude = "publisher"
        lm = _triple(row["lm_gbp"], "lm_gbp", where)
        notes.append(_basis_note(row.get("lm_basis"), "Magnitude", where))
    elif lm is not None:
        magnitude = "subscriber"
        lm = _triple(lm, "lm", "the caller's magnitude")
        basis = row.get("magnitude_basis") or {}
        notes.append(f"Magnitude: the subscriber's own ({basis.get('kind', 'unstated')}, read "
                     f"{basis.get('as_of', 'undated')}): "
                     f"{basis.get('statement', 'the register publishes none and says nothing about whose it is')}")
    else:
        basis = row.get("magnitude_basis") or {}
        sys.exit(f"{where}: publishes no `lm_gbp` and the caller supplied no magnitude. Its "
                 f"magnitude_basis says whose it is ({basis.get('kind', 'unstated')}: "
                 f"{basis.get('statement', 'no statement')}); there is nothing to annualise "
                 f"(ADR-0020)")
    return {
        "version": version,
        "name": f"threat-register:{version} {institution} {threat}",
        "threat": threat,
        "magnitude": magnitude,
        "note": " ".join(notes),
        "warn": {"lef": list(lef), "lm": list(lm)},
        "deny": {"lef": list(DENY_LEF), "lm": list(lm)},
    }


def threat_scenario(feed: dict, institution: str, threat: str | None = None, lm=None) -> dict:
    """One institution's HEADLINE threat as a fair.py scenario, or, with `threat`,
    one row of its `threats` map (major 4). `lm` is the caller's own magnitude
    for a row that publishes none; it is ignored for the headline."""
    version = feed.get("feed_version", "unversioned")
    currency = feed.get("currency") or "GBP"
    institutions = feed.get("institutions") or {}
    if institution not in institutions:
        sys.exit(f"threat-register {version}: no institution {institution!r} in this payload "
                 f"(it carries {sorted(institutions)})")
    entry = institutions[institution]
    where = f"threat-register {version}: institutions.{institution}"
    if threat is not None:
        return _threat_row_scenario(feed, institution, entry, threat, lm, where)

    lef = _triple(entry["lef"], "lef", where)
    notes = [f"{entry['threat']} ({entry['flavour']})."]

    if "lef_basis" in entry:
        notes.append(_basis_note(entry["lef_basis"], "Frequency", where))
    else:
        notes.append(f"lef sourced from {entry['source']}.")

    if "lm_gbp" in entry:
        lm = _triple(entry["lm_gbp"], "lm_gbp", where)
        notes.append(_basis_note(entry.get("lm_basis"), "Magnitude", where))
    else:
        if institution not in FROZEN_LM_GBP:
            sys.exit(f"{where}: payload version {version} publishes no `lm_gbp`, and this "
                     f"converter holds no frozen magnitude for {institution!r}. The magnitude "
                     f"belongs in the publisher's payload from major 3 (eco-system ticket 79 "
                     f"item 4); there is nothing here to price from (ADR-0020)")
        lm = tuple(float(x) for x in FROZEN_LM_GBP[institution])
        notes.append(FROZEN_NOTE.format(lm=lm, currency=currency, version=version))

    return {
        "version": version,
        "name": f"threat-register:{version} {institution}",
        "note": " ".join(notes),
        "warn": {"lef": list(lef), "lm": list(lm)},
        "deny": {"lef": list(DENY_LEF), "lm": list(lm)},
    }


def selfcheck() -> None:
    import glob
    import os

    root = os.path.dirname(os.path.abspath(__file__))
    checked, sourced, frozen = 0, 0, 0
    for path in sorted(glob.glob(os.path.join(root, "v*/feed.json"))):
        payload = json.load(open(path))["payload"]
        for inst in payload["institutions"]:
            sc = threat_scenario(payload, inst)
            for half in ("warn", "deny"):
                lo, mode, hi = sc[half]["lef"]
                assert lo <= mode <= hi, (path, inst, half, sc)
                lo, mode, hi = sc[half]["lm"]
                assert lo <= mode <= hi, (path, inst, half, sc)
            if "lm_gbp" in payload["institutions"][inst]:
                assert "Magnitude basis" in sc["note"], (path, inst, sc["note"])
                assert "MAGNITUDE UNSOURCED" not in sc["note"], (path, inst, sc["note"])
                sourced += 1
            else:
                assert "MAGNITUDE UNSOURCED" in sc["note"], (path, inst, sc["note"])
                frozen += 1
            checked += 1
    assert checked >= 9, f"only checked {checked} (version, institution) pairs"
    assert sourced >= 3, "no published version carries lm_gbp in its own payload"
    assert frozen >= 6, "the pre-major-3 versions stopped naming their frozen magnitude"
    print(f"ok  {checked} (version, institution) scenarios; {sourced} price a magnitude the "
          f"PUBLISHER published, {frozen} price the frozen table and say so by name")

    # The move moved no price: major 3's magnitudes are the frozen table's.
    v3 = json.load(open(os.path.join(root, "v3", "feed.json")))["payload"]
    v2 = json.load(open(os.path.join(root, "v2", "feed.json")))["payload"]
    for inst, lm in FROZEN_LM_GBP.items():
        got = tuple(v3["institutions"][inst]["lm_gbp"])
        assert got == tuple(float(x) for x in lm) or got == tuple(lm), (inst, got, lm)
        assert threat_scenario(v3, inst)["warn"]["lm"] == list(threat_scenario(v2, inst)["warn"]["lm"]), inst
    print("ok  every magnitude in major 3 is the number the platform's own table held, so the "
          "move re-homes it and does not re-price it")

    # A number with no basis REFUSES, it does not default.
    import copy
    bare = copy.deepcopy(v3)
    del bare["institutions"]["driftwood"]["lm_basis"]
    try:
        threat_scenario(bare, "driftwood")
    except SystemExit as e:
        assert "basis" in str(e) and "driftwood" in str(e), e
    else:
        raise AssertionError("a magnitude with no basis priced instead of refusing")
    print("ok  a magnitude with no basis refuses, naming the institution and where its basis goes")

    # Standalone: nothing but the standard library and the payload path. Read
    # off the module's own import statements, not off prose that mentions a
    # module name -- a check that greps its own docstring grades the docstring.
    import re
    src = open(os.path.join(root, os.path.basename(__file__))).read()
    imported = set(re.findall(r"^\s*(?:import|from)\s+([A-Za-z_.][\w.]*)", src, re.M))
    stdlib = {"__future__", "argparse", "json", "sys", "glob", "os", "copy", "re", "stat", "math", "hashlib", "datetime"}
    assert imported <= stdlib, (
        f"this converter is not standalone: it imports {sorted(imported - stdlib)}")
    assert not re.search(r"^\s*sys\.path", src, re.M), "this converter mutates sys.path"
    print("ok  the converter imports only the standard library, so the hub's portability replay "
          "can run it in a directory holding nothing but itself and the payload")

    # Major 4 (eco-system ticket 145): the `threats` map. Every institution's
    # `scheduled-agent-misuses-write-credential` row prices with a magnitude the
    # CALLER hands in and names it as the subscriber's; with none it refuses by
    # name; an unknown row refuses by name; and a pre-major-4 payload refuses the
    # row naming the major it arrives with. The headline scenario of every
    # major-4 institution is byte-identical to major 3's, so the move re-prices
    # no headline.
    v4_path = os.path.join(root, "v4", "feed.json")
    assert os.path.exists(v4_path), "major 4 is in the tree"
    v4 = json.load(open(v4_path))["payload"]
    row_id = "scheduled-agent-misuses-write-credential"
    priced = 0
    for inst in v4["institutions"]:
        assert row_id in (v4["institutions"][inst].get("threats") or {}), (inst, "carries the row")
        sc = threat_scenario(v4, inst, threat=row_id, lm=(10.0, 10.0, 10.0))
        assert sc["magnitude"] == "subscriber" and sc["threat"] == row_id, sc
        assert sc["warn"]["lm"] == [10.0, 10.0, 10.0] and sc["warn"]["lef"][0] <= sc["warn"]["lef"][1] <= sc["warn"]["lef"][2], sc
        assert 0 < sc["warn"]["lef"][1] < 0.01, ("a per-year rate well under one event", sc["warn"]["lef"])
        assert "Frequency basis (published" in sc["note"] and "the subscriber's own" in sc["note"], sc["note"]
        assert "COULD NOT LOOK" in sc["note"], "the row names what it could not look at"
        assert threat_scenario(v4, inst)["warn"] == threat_scenario(v3, inst)["warn"], (inst, "headline unchanged")
        priced += 1
        for bad, why in ((lambda: threat_scenario(v4, inst, threat=row_id), "no magnitude at all"),
                         (lambda: threat_scenario(v4, inst, threat="no-such-row", lm=(1, 1, 1)), "unknown row"),
                         (lambda: threat_scenario(v3, inst, threat=row_id, lm=(1, 1, 1)), "pre-major-4 payload")):
            try:
                bad()
            except SystemExit as e:
                assert row_id in str(e) or "no-such-row" in str(e), (why, e)
                assert "ADR-0020" in str(e), (why, e)
            else:
                raise AssertionError(f"{why} priced instead of refusing")
    assert priced == 3, priced
    print(f"ok  major 4: {priced} institutions carry the `{row_id}` row; each prices only with the "
          f"subscriber's own magnitude and says so, refuses with none, and every headline scenario is "
          f"major 3's")


def _lm_arg(text: str):
    parts = [float(x) for x in text.split(",")]
    if len(parts) != 3:
        sys.exit(f"--lm wants lo,mode,hi, got {text!r}")
    return parts



# The same standalone protocol lives with each publisher's arithmetic. No
# sibling/SDK dependency is available in the ordinary vendored replay closure.
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

def _publisher_forecast_base(payload, context):
    import re
    document = _generator_document(context, 'feeds', 'threat-register')
    if not isinstance(payload, dict) or 'payload' in payload:
        raise _AdapterRefused('forecast-base requires the unwrapped publisher payload')
    _adapter_text(payload.get('feed_version'), 'payload.feed_version')
    if not isinstance(payload.get('currency'), str) or not re.fullmatch('[A-Z]{3}', payload['currency']):
        raise _AdapterRefused('threat payload must declare its native currency')
    return threat_scenario(payload, document['party'])

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


def main(argv=None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] in ('widen-to', 'forecast-base'):
        if len(argv) != 3:
            sys.exit(f'{argv[0]}: expected unwrapped payload.json and context.json')
        _publisher_command(argv[0], argv[1], argv[2], 'feeds', 'feed_version', 'publisher-loss-model')
        return
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pt = sub.add_parser("threat", help="one institution's entry -> a fair.py scenario")
    pt.add_argument("feed", help="path to the threat-register PAYLOAD (envelope or bare payload)")
    pt.add_argument("institution")
    pt.add_argument("--threat", default=None,
                    help="a row of the institution's `threats` map (major 4) instead of the headline")
    pt.add_argument("--lm", default=None, type=_lm_arg,
                    help="lo,mode,hi: the SUBSCRIBER's own magnitude for a row that publishes none")
    pt.add_argument("-o", "--out")
    sub.add_parser("selfcheck", help="every published (version, institution) yields a valid scenario")

    args = p.parse_args(argv)
    if args.cmd == "selfcheck":
        selfcheck()
        return

    doc = json.load(open(args.feed))
    feed = doc.get("payload", doc) if isinstance(doc, dict) else doc
    scenario = threat_scenario(feed, args.institution, threat=args.threat, lm=args.lm)
    out = json.dumps(scenario, indent=2)
    if args.out:
        open(args.out, "w").write(out + "\n")
    else:
        print(out)


if __name__ == "__main__":
    main()
