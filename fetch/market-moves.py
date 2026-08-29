#!/usr/bin/env python3
"""Scheduled fetch for the market-moves feed -- the Polymarket adapter.

One MECHANICAL rule (market-moves/rule.yaml) over ONE venue corpus, producing a
dated SERIES per admitted market (ecosystem tickets 22 and 49). Nothing in this
file judges anything: no model is called, no relevance is assessed, no move is
interpreted. The clock gathers; the twin classifies a move by a skill a human
runs (ticket 50, ADR-0024).

What "changed" means lives in rule.yaml, not here: `lib.main` computes the bump
with `bump.py` and opens a PR only when it is not `none`. A sub-threshold
reading appends to the observation branch with the reading in the line, so the
series survives a threshold that never fires (spec, story 11).

See fetch/lib.py for the shared body.
"""
import datetime as dt
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

# ponytail: read via lib.read_upstream() from the committed venue corpus.
# Upgrade path: `urllib.request.urlopen(UPSTREAM)` and a parse into the same
# gamma-API field names -- `select` and `build` below already work on those.
# Polymarket's terms on redistributing market data are read before the first
# market-moves tag is cut (ticket 49); the fixture keeps the clock honest until
# then, because it publishes no venue data at all.
UPSTREAM = "https://gamma-api.polymarket.com/markets"


def _days_between(start, end):
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days


def select(corpus, rule, as_of):
    """The rule, applied. Returns (admitted, refusals) where a refusal is
    (market id, the rule field that refused it) -- so "mechanical" is something
    a verify script can observe rather than a word in a comment."""
    categories = [c.strip() for c in str(rule["categories"]).split(",") if c.strip()]
    admitted, refusals = [], []
    for market in corpus["markets"]:
        horizon = _days_between(as_of, market["endDate"])
        if market["category"] not in categories:
            refusals.append((market["id"], "categories"))
        elif float(market["liquidityNum"]) < float(rule["min_liquidity"]):
            refusals.append((market["id"], "min_liquidity"))
        elif horizon < int(rule["min_horizon_days"]):
            refusals.append((market["id"], "min_horizon_days"))
        elif horizon > int(rule["max_horizon_days"]):
            refusals.append((market["id"], "max_horizon_days"))
        else:
            admitted.append(market)
    admitted.sort(key=lambda m: m["id"])
    # The seeded volume valve (rule.yaml, twin ticket 21 Q2's "(c) random
    # sampling as a volume valve if the rule selects too many"): a seeded cut,
    # so two runs over the same corpus admit the same set.
    limit = int(rule["max_markets"])
    if len(admitted) > limit:
        chosen = random.Random(int(rule["sample_seed"])).sample(admitted, limit)
        for market in admitted:
            if market not in chosen:
                refusals.append((market["id"], "max_markets"))
        admitted = sorted(chosen, key=lambda m: m["id"])
    return admitted, refusals


def build(published, corpus):
    """The published payload plus today's reading, for every admitted market.

    Appends; never rewrites history. A second run on the same date replaces
    that date's reading rather than doubling it, so a re-dispatch of the clock
    is not a new observation."""
    rule = lib.load_rule("market-moves")
    as_of = corpus.get("as_of") or dt.datetime.now(dt.timezone.utc).date().isoformat()
    admitted, refusals = select(corpus, rule, as_of)
    print(f"market-moves: rule.yaml@{rule['rule_version']} admits {len(admitted)} of "
          f"{len(corpus['markets'])} markets; refused "
          + ", ".join(f"{mid} ({why})" for mid, why in refusals))

    was = published.get("markets", {})
    markets = {}
    for market in admitted:
        series = [point for point in was.get(market["id"], {}).get("observations", [])
                  if point["date"] != as_of]
        series.append({"date": as_of, "price_level": float(market["lastTradePrice"])})
        markets[market["id"]] = {
            "venue": corpus["venue"],
            "question": market["question"],
            "category": market["category"],
            "resolution_source": market["resolutionSource"],
            "observations": sorted(series, key=lambda point: point["date"]),
        }
    payload = dict(published)
    payload.update({
        "venue": corpus["venue"],
        "source": corpus["source"],
        "selection_rule": f"market-moves/rule.yaml@{rule['rule_version']}",
        "markets": markets,
    })
    return payload


def reading(payload):
    """What the observation line carries: the dated readings themselves, not a
    digest of them. A hash is enough to prove a payload did not change; a
    SERIES is what story 11 asks to survive a threshold that never fires."""
    latest = {}
    for market_id, market in payload["markets"].items():
        point = max(market["observations"], key=lambda p: p["date"])
        latest[market_id] = point["price_level"]
    return {"venue": payload["venue"], "price_levels": latest}


if __name__ == "__main__":
    raise SystemExit(lib.main("market-moves", UPSTREAM, build=build, reading=reading))
