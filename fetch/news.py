#!/usr/bin/env python3
"""Scheduled fetch for the news feed -- the pool reader.

MECHANICAL admission and nothing else (ecosystem tickets 23 and 50): an event
enters if it carries an id, a date, a source, a statement and a resolvable
provenance URL, and is inside the window news/rule.yaml declares. No model runs
here, no relevance is judged, no STEEP tag is assigned, nothing is bound to any
component. All of that is the classify-and-judge skill, run by a human over the
published pool, landing as a reviewed PR on the adopter's own overlay
(.claude/skills/classify-and-judge, ADR-0024).

The URL requirement is load-bearing: an invented headline has nowhere it was
read, so a SCENARIO cannot enter a feed of observations. The niobium supply
shock lives in the adopter's twin scenario library, never here.

See fetch/lib.py for the shared body.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

# ponytail: read via lib.read_upstream() from the committed pool. Upgrade path:
# `urllib.request.urlopen()` against a press-release or news endpoint and a
# parse into the same five fields -- `admit` below does not change.
UPSTREAM = "publisher release records in the policy-as-versioned organisations"

FIELDS = ("id", "date", "source", "statement", "provenance")


def admit(event, rule, today):
    """The rule, applied. Returns None when the event is admitted, or the rule
    field that refused it."""
    for field in FIELDS:
        if not event.get(field):
            return f"required field {field}"
    if rule.get("requires_provenance_url") and not str(
            event["provenance"].get("url", "")).startswith(("http://", "https://")):
        return "requires_provenance_url"
    age = (dt.date.fromisoformat(today) - dt.date.fromisoformat(event["date"])).days
    if age > int(rule["max_age_days"]):
        return "max_age_days"
    if age < 0:
        return "dated in the future"
    return None


def build(published, corpus):
    """The published pool plus every newly admitted event. Append-only: a
    published event is never dropped by this clock, because withdrawing one is
    a MAJOR a human declares, not something a bad upstream day can do."""
    rule = lib.load_rule("news")
    today = corpus.get("as_of") or dt.datetime.now(dt.timezone.utc).date().isoformat()
    admitted, refusals = [], []
    for event in corpus["events"]:
        why = admit(event, rule, today)
        if why:
            refusals.append((event.get("id", "<no id>"), why))
        else:
            admitted.append({field: event[field] for field in FIELDS})
    print(f"news: rule.yaml@{rule['rule_version']} admits {len(admitted)} of "
          f"{len(corpus['events'])} pool entries; refused "
          + ", ".join(f"{eid} ({why})" for eid, why in refusals))

    events = list(published.get("events", []))
    known = {event["id"] for event in events}
    for event in admitted:
        if event["id"] in known:
            # A restatement is a patch a human reviews, so take the pool's text.
            events = [event if published_event["id"] == event["id"] else published_event
                      for published_event in events]
        else:
            events.append(event)
    payload = dict(published)
    payload.update({"source": corpus["source"],
                    "events": sorted(events, key=lambda e: (e["date"], e["id"]))})
    return payload


def reading(payload):
    """What the observation line carries: the size of the pool and the id of
    the newest event in it, so a day on which nothing was admitted is still a
    dated point in a series somebody can score."""
    events = payload["events"]
    newest = max(events, key=lambda event: (event["date"], event["id"]))
    return {"events": len(events), "newest": newest["id"], "newest_date": newest["date"]}


if __name__ == "__main__":
    raise SystemExit(lib.main("news", UPSTREAM, build=build, reading=reading))
