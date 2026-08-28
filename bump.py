#!/usr/bin/env python3
"""Compute the semver bump between two feed envelopes, under a feed's own rule.

ADR-0019 (one envelope, the tag is the signature) and ADR-0023 / decision D2
(a scheduled fetch opens a PR only when the computed bump is not "none", and
each feed says in its own versioned rule file what "changed" means).

    bump.py <old feed.json> <new feed.json> <rule.yaml>   -> prints one word
    bump.py selfcheck                                     -> asserts the ladder

The ladder, highest wins:

    payload_schema changed   major   consumers must re-read the shape
    entry removed            major   a pin that resolved stops resolving
    entry added              minor   additive, every existing pin still resolves
    minor_when_changed       minor   the one payload field a feed declares as a
      field changed                  minor on its own (fx: a new month)
    only numeric moves,      none    sub-threshold: an observation, not a release
      all within tolerance
    anything else            patch

Envelope `version` and `published_at` are ignored: they are the release's own
facts, not the feed's content. Only `payload_schema` and `payload` are compared.

Standard library only -- this runs on a GitHub runner and in the offline gate,
and neither is promised pyyaml. rule.yaml is therefore flat `key: value`.
"""
import json
import sys

LADDER = ("none", "patch", "minor", "major")


def load_rule(path):
    """Flat `key: value` YAML. ponytail: the rule files are three keys; a real
    parser arrives the day a rule needs a list or a nested map."""
    rule = {}
    with open(path) as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip() if not line.lstrip().startswith("#") else ""
            if not line or ":" not in line:
                continue
            key, _, value = line.partition(":")
            value = value.strip().strip('"').strip("'")
            try:
                value = float(value) if "." in value else int(value)
            except ValueError:
                pass
            rule[key.strip()] = value
    for required in ("entries", "numeric_tolerance", "changed_when"):
        if required not in rule:
            raise SystemExit(f"FAIL: {path} has no {required}")
    return rule


def _numbers(value, prefix=""):
    """Every numeric leaf under `value`, keyed by its path."""
    if isinstance(value, bool):
        return {}
    if isinstance(value, (int, float)):
        return {prefix: float(value)}
    out = {}
    if isinstance(value, dict):
        for key, sub in value.items():
            out.update(_numbers(sub, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, sub in enumerate(value):
            out.update(_numbers(sub, f"{prefix}[{index}]"))
    return out


def _within(old, new, tolerance):
    if old == new:
        return True
    scale = max(abs(old), abs(new))
    return scale > 0 and abs(new - old) / scale <= tolerance


def compute(old, new, rule):
    if old.get("payload_schema") != new.get("payload_schema"):
        return "major"

    key = rule["entries"]
    old_entries = old.get("payload", {}).get(key, {})
    new_entries = new.get("payload", {}).get(key, {})
    if not isinstance(old_entries, dict) or not isinstance(new_entries, dict):
        raise SystemExit(f"FAIL: payload.{key} is not an entry map in both feeds")

    if set(old_entries) - set(new_entries):
        return "major"
    if set(new_entries) - set(old_entries):
        return "minor"

    old_payload, new_payload = old.get("payload", {}), new.get("payload", {})
    if old_payload == new_payload:
        return "none"

    # One optional field per feed whose change is a minor on its own, so a feed
    # that republishes its whole table on a period (fx: a new HMRC month) is not
    # read as "some numbers moved". Absent from a rule.yaml, nothing changes.
    minor_field = rule.get("minor_when_changed")
    if minor_field and old_payload.get(minor_field) != new_payload.get(minor_field):
        return "minor"

    # Same entries, same schema, some difference. It is "none" only if every
    # difference is a numeric move inside the feed's declared tolerance.
    old_numbers, new_numbers = _numbers(old_payload), _numbers(new_payload)
    if set(old_numbers) != set(new_numbers):
        return "patch"
    stripped_old = json.dumps(_blank_numbers(old_payload), sort_keys=True)
    stripped_new = json.dumps(_blank_numbers(new_payload), sort_keys=True)
    if stripped_old != stripped_new:
        return "patch"
    tolerance = float(rule["numeric_tolerance"])
    for path, old_value in old_numbers.items():
        if not _within(old_value, new_numbers[path], tolerance):
            return "patch"
    return "none"


def _blank_numbers(value):
    """The document with every numeric leaf replaced, so two documents compare
    equal exactly when they differ only in their numbers."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return "<number>"
    if isinstance(value, dict):
        return {k: _blank_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_blank_numbers(v) for v in value]
    return value


def selfcheck():
    rule = {"entries": "institutions", "numeric_tolerance": 0.10, "changed_when": "x"}

    def feed(entries, schema="threat-register/payload.schema.json"):
        return {"kind": "feed", "name": "threat-register", "version": "1.0.0",
                "published_by": "feeds", "published_at": "2026-07-31T16:22:39+01:00",
                "payload_schema": schema,
                "payload": {"feed_version": "v1", "institutions": entries}}

    base = feed({"driftwood": {"lef": [2, 4, 9]}, "tuppence": {"lef": [3, 6, 14]}})

    cases = [
        ("unchanged", base, "none"),
        ("entry added", feed({**base["payload"]["institutions"],
                              "ludlow": {"lef": [1, 2, 5]}}), "minor"),
        ("entry removed", feed({"driftwood": {"lef": [2, 4, 9]}}), "major"),
        ("payload schema changed", feed(base["payload"]["institutions"],
                                        schema="threat-register/payload.v2.schema.json"), "major"),
        ("numeric move inside tolerance",
         feed({"driftwood": {"lef": [2, 4, 9]}, "tuppence": {"lef": [3, 6, 15]}}), "none"),
        ("numeric move outside tolerance",
         feed({"driftwood": {"lef": [2, 4, 9]}, "tuppence": {"lef": [3, 6, 20]}}), "patch"),
        ("non-numeric field changed",
         feed({"driftwood": {"lef": [2, 4, 9]},
               "tuppence": {"lef": [3, 6, 14], "threat": "new wording"}}), "patch"),
    ]
    # fx declares `minor_when_changed: period` and a zero tolerance: it is the
    # money instrument itself, so no rate move is too small to publish.
    fx_rule = {"entries": "rates", "numeric_tolerance": 0, "changed_when": "x",
               "minor_when_changed": "period"}

    def fx(period, rates):
        return {"kind": "feed", "name": "fx", "version": "1.0.0",
                "published_by": "feeds", "published_at": "2026-07-31T09:00:00+01:00",
                "payload_schema": "fx/payload.schema.json",
                "payload": {"source": "HMRC monthly exchange rates", "period": period,
                            "base": "GBP", "rates": rates}}

    august = fx("2026-08", {"USD": 1.2840, "EUR": 1.1735})
    fx_cases = [
        ("fx new month", fx("2026-09", {"USD": 1.2915, "EUR": 1.1698}), "minor"),
        ("fx corrected rate", fx("2026-08", {"USD": 1.2841, "EUR": 1.1735}), "patch"),
        ("fx currency added", fx("2026-08", {"USD": 1.2840, "EUR": 1.1735, "JPY": 191.42}), "minor"),
        ("fx currency withdrawn", fx("2026-08", {"USD": 1.2840}), "major"),
    ]

    for name, candidate, expected in cases:
        got = compute(base, candidate, rule)
        assert got == expected, f"{name}: expected {expected}, got {got}"
        print(f"ok  {name} -> {expected}")
    for name, candidate, expected in fx_cases:
        got = compute(august, candidate, fx_rule)
        assert got == expected, f"{name}: expected {expected}, got {got}"
        print(f"ok  {name} -> {expected}")
    print(f"ok  bump.py selfcheck: {len(cases) + len(fx_cases)} cases")


def main(argv):
    if len(argv) == 2 and argv[1] == "selfcheck":
        selfcheck()
        return 0
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: bump.py <old feed.json> <new feed.json> <rule.yaml> | selfcheck",
              file=sys.stderr)
        return 2
    old = json.load(open(argv[1]))
    new = json.load(open(argv[2]))
    print(compute(old, new, load_rule(argv[3])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
