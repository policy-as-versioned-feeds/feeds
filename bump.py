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
    series move >= the       patch   a feed that publishes a SERIES declares its
      declared threshold             own threshold (market-moves: 5 points)
    only numeric moves,      none    sub-threshold: an observation, not a release
      all within tolerance
    anything else            patch

`payload.<entries>` is an entry map. A feed whose payload carries a LIST of
objects each with an `id` (news: `events[]`) is read as the map that list keys,
so the same ladder computes over both shapes.

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


def entry_map(entries):
    """The entry map `payload.<entries>` is, whichever of the two shapes it took.

    A map is itself. A list of objects each carrying an `id` is the map that
    list keys: news publishes `events[]` because an event is a dated line in a
    log, not a slot somebody overwrites, and platform's market-intel keys its
    `components` list the same way. Anything else is not an entry map.

    ponytail: `id` is the only key it looks for. Upgrade path: a rule key
    naming the field, the day a feed keys its list on something else.
    """
    if isinstance(entries, dict):
        return entries
    if isinstance(entries, list) and all(
            isinstance(item, dict) and "id" in item for item in entries):
        return {str(item["id"]): item for item in entries}
    return None


def _last(series, value_field):
    """The most recent value in a dated series -- the reading a threshold is
    measured against. `date` orders it, because a fetch appends and an append
    is not a promise about order."""
    if not series:
        return None
    latest = max(series, key=lambda point: point.get("date", ""))
    return latest.get(value_field)


def _series_verdict(old_entries, new_entries, rule):
    """The ladder for a feed that publishes a SERIES per entry (market-moves).

    Appending a reading is not "some numbers moved": the numeric leaves are at
    new paths every day, so the generic tolerance below reads every single day
    as a patch and the feed releases daily. This branch is what decision D2
    means by "each feed defines changed in its own versioned rule file": the
    move of the latest reading, against the feed's own `move_threshold`, in the
    units the series is published in (market-moves: price points, so 0.05 is
    five percentage points). Anything about an entry OTHER than its series is a
    patch, because the metadata a consumer pins is not a reading.
    """
    threshold = float(rule["move_threshold"])
    series_field = rule["series"]
    value_field = rule["series_value"]
    for key, new_entry in new_entries.items():
        old_entry = old_entries[key]
        if {k: v for k, v in old_entry.items() if k != series_field} != \
           {k: v for k, v in new_entry.items() if k != series_field}:
            return "patch"
        old_value = _last(old_entry.get(series_field, []), value_field)
        new_value = _last(new_entry.get(series_field, []), value_field)
        if old_value is None or new_value is None:
            if old_value != new_value:
                return "patch"
            continue
        # rounded, because 0.38 - 0.33 is 0.049999999999999996 in binary
        # floating point and a move of exactly the declared threshold is "at
        # least the threshold". Six places is far below any venue's tick.
        if round(abs(float(new_value) - float(old_value)), 6) >= threshold:
            return "patch"
    return "none"


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
    old_entries = entry_map(old.get("payload", {}).get(key, {}))
    new_entries = entry_map(new.get("payload", {}).get(key, {}))
    if old_entries is None or new_entries is None:
        raise SystemExit(
            f"FAIL: payload.{key} is not an entry map in both feeds -- a map, or a "
            f"list of objects each carrying an id")

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

    # A feed that publishes a dated series per entry measures its own move
    # against its own threshold (D2). See _series_verdict.
    if rule.get("series"):
        if {k: v for k, v in old_payload.items() if k != key} != \
           {k: v for k, v in new_payload.items() if k != key}:
            return "patch"  # something outside the series changed; not a reading
        return _series_verdict(old_entries, new_entries, rule)

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

    # market-moves publishes a dated series per market and declares its own
    # threshold: five price points (ecosystem ticket 49, ADR-0023 D2).
    mm_rule = {"entries": "markets", "numeric_tolerance": 0, "changed_when": "x",
               "series": "observations", "series_value": "price_level",
               "move_threshold": 0.05, "minor_when_changed": "selection_rule"}

    def mm(series, extra=None, selection_rule="market-moves/rule.yaml@1"):
        market = {"venue": "polymarket", "question": "q?", "category": "geopolitics",
                  "resolution_source": "https://example.invalid/rules",
                  "observations": series}
        markets = {"0xaaa": market}
        if extra:
            markets["0xbbb"] = dict(market, **extra)
        return {"kind": "feed", "name": "market-moves", "version": "1.0.0",
                "published_by": "feeds", "published_at": "2026-08-29T03:17:00+00:00",
                "payload_schema": "market-moves/payload.schema.json",
                "payload": {"venue": "polymarket", "selection_rule": selection_rule,
                            "markets": markets}}

    def restated_market(build, series):
        doc = build(series)
        doc["payload"]["markets"]["0xaaa"]["question"] = "q, restated?"
        return doc

    published_series = [{"date": "2026-08-27", "price_level": 0.31},
                        {"date": "2026-08-28", "price_level": 0.33}]
    published_mm = mm(published_series)
    mm_cases = [
        ("market-moves sub-threshold reading",
         mm(published_series + [{"date": "2026-08-29", "price_level": 0.36}]), "none"),
        ("market-moves reading at the threshold",
         mm(published_series + [{"date": "2026-08-29", "price_level": 0.38}]), "patch"),
        ("market-moves downward move over the threshold",
         mm(published_series + [{"date": "2026-08-29", "price_level": 0.27}]), "patch"),
        ("market-moves rule version changed",
         mm(published_series, selection_rule="market-moves/rule.yaml@2"), "minor"),
        ("market-moves market admitted",
         mm(published_series, extra={"question": "a second admitted market?"}), "minor"),
        ("market-moves question restated", restated_market(mm, published_series), "patch"),
    ]

    # news publishes events[] -- a LIST keyed by id, not a map (ticket 50).
    news_rule = {"entries": "events", "numeric_tolerance": 0, "changed_when": "x"}

    def news(events):
        return {"kind": "feed", "name": "news", "version": "1.0.0",
                "published_by": "feeds", "published_at": "2026-08-29T03:17:00+00:00",
                "payload_schema": "news/payload.schema.json",
                "payload": {"events": events}}

    event = {"id": "one", "date": "2026-08-20", "source": "a wire",
             "statement": "something was said", "provenance": {"url": "https://example.invalid/a"}}
    other = dict(event, id="two", statement="something else was said")
    published_news = news([event])
    news_cases = [
        ("news re-read of the same pool", news([event]), "none"),
        ("news event added", news([event, other]), "minor"),
        ("news event withdrawn", news([]), "major"),
        ("news statement restated",
         news([dict(event, statement="something was said, restated")]), "patch"),
    ]

    for name, candidate, expected in cases:
        got = compute(base, candidate, rule)
        assert got == expected, f"{name}: expected {expected}, got {got}"
        print(f"ok  {name} -> {expected}")
    for name, candidate, expected in fx_cases:
        got = compute(august, candidate, fx_rule)
        assert got == expected, f"{name}: expected {expected}, got {got}"
        print(f"ok  {name} -> {expected}")
    for name, candidate, expected in mm_cases:
        got = compute(published_mm, candidate, mm_rule)
        assert got == expected, f"{name}: expected {expected}, got {got}"
        print(f"ok  {name} -> {expected}")
    for name, candidate, expected in news_cases:
        got = compute(published_news, candidate, news_rule)
        assert got == expected, f"{name}: expected {expected}, got {got}"
        print(f"ok  {name} -> {expected}")
    total = len(cases) + len(fx_cases) + len(mm_cases) + len(news_cases)
    print(f"ok  bump.py selfcheck: {total} cases")


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
