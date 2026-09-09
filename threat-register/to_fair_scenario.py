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
reads nothing but the payload path it is given. `platform/compose/composition.py`
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


def threat_scenario(feed: dict, institution: str) -> dict:
    version = feed.get("feed_version", "unversioned")
    currency = feed.get("currency") or "GBP"
    institutions = feed.get("institutions") or {}
    if institution not in institutions:
        sys.exit(f"threat-register {version}: no institution {institution!r} in this payload "
                 f"(it carries {sorted(institutions)})")
    entry = institutions[institution]
    where = f"threat-register {version}: institutions.{institution}"

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
    stdlib = {"__future__", "argparse", "json", "sys", "glob", "os", "copy", "re"}
    assert imported <= stdlib, (
        f"this converter is not standalone: it imports {sorted(imported - stdlib)}")
    assert not re.search(r"^\s*sys\.path", src, re.M), "this converter mutates sys.path"
    print("ok  the converter imports only the standard library, so the hub's portability replay "
          "can run it in a directory holding nothing but itself and the payload")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pt = sub.add_parser("threat", help="one institution's entry -> a fair.py scenario")
    pt.add_argument("feed", help="path to the threat-register PAYLOAD (envelope or bare payload)")
    pt.add_argument("institution")
    pt.add_argument("-o", "--out")
    sub.add_parser("selfcheck", help="every published (version, institution) yields a valid scenario")

    args = p.parse_args(argv)
    if args.cmd == "selfcheck":
        selfcheck()
        return

    doc = json.load(open(args.feed))
    feed = doc.get("payload", doc) if isinstance(doc, dict) else doc
    scenario = threat_scenario(feed, args.institution)
    out = json.dumps(scenario, indent=2)
    if args.out:
        open(args.out, "w").write(out + "\n")
    else:
        print(out)


if __name__ == "__main__":
    main()
