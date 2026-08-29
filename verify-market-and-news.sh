#!/usr/bin/env bash
# Ecosystem tickets 49 and 50: the market-moves feed and the news feed, observed
# in this repo. Offline -- no cluster, no network, no tag, no model.
#
# verify-feeds.sh already validates every published envelope against the ONE
# schema and its own payload schema, both new feeds included. This script
# observes what is specific to these two:
#
#   1. market-moves publishes a SERIES and nothing probability-shaped;
#   2. the Polymarket adapter's selection is MECHANICAL: the rule admits and
#      refuses, by name, on the committed venue corpus;
#   3. the feed's OWN threshold is what opens a PR (ADR-0023, D2) -- driven
#      through the real clock, which fires on a moved corpus and does not on a
#      sub-threshold one;
#   4. the sub-threshold reading lands on the OBSERVATION branch path, carrying
#      the reading itself and not just a hash;
#   5. news carries the minimal payload, admits only what has a provenance URL,
#      and its threshold fires on a new event and not on a re-read;
#   6. NIOBIUM IS ABSENT from the news feed. It is a scenario, and it lives in
#      the adopter's twin scenario library (ticket 29), never in a feed of
#      observations;
#   7. NO CLOCK IN THIS REPOSITORY INVOKES A MODEL. Reasoning is a skill a human
#      runs (ADR-0024); the clock gathers.
#
# Gate contract: exit 0 observed true, exit 3 could not look (last line
# SKIP: ...), anything else observed false (last line FAIL: ...).
set -uo pipefail

# Gate contract (BUILD-BRIEF.md): exit 0 = observed true, exit 3 = could not
# look, anything else = observed false WITH `FAIL: <reason>` on the LAST line.
# 2026-08-29 review: planting a real defect here ended the run on a raw Python
# traceback ("AssertionError: ..."), which talk/verify-all.sh prints verbatim as
# the row's reason and verify-e2e-step7-honesty.sh grades UNGRADED. The defect
# was always detected; only the reason line was unreadable. This trap makes the
# last line legible without swallowing the traceback above it.
__verdict_trap() {
  local rc=$?
  [ "$rc" = 0 ] || [ "$rc" = 3 ] || echo "FAIL: a check above observed false (exit $rc); its own error line is the last one before this"
  return "$rc"
}
trap __verdict_trap EXIT

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

fail() { echo "FAIL: $*"; exit 1; }
work="$(mktemp -d)"
trap 'rm -rf "$work"; __verdict_trap' EXIT   # one EXIT trap: cleanup THEN the verdict line

echo "== market-moves: a series, and nothing shaped like a probability =="
python3 - <<'PY' || exit 1
import json, re, sys

bad = []
schema = open("market-moves/payload.schema.json").read()
# Property NAMES only: the schema's prose says the word "probability" in the
# sentence explaining why there is no such field, and that sentence is the
# point rather than a violation.
names = set(re.findall(r'"([a-z_]+)"\s*:\s*\{', schema))
forbidden = {"probability", "implied_probability", "belief", "odds", "confidence",
             "likelihood", "moves", "delta"}
if names & forbidden:
    bad.append(f"market-moves/payload.schema.json declares {sorted(names & forbidden)}")

feed = json.load(open("market-moves/v1/feed.json"))
payload = feed["payload"]
markets = payload["markets"]
if not markets:
    bad.append("market-moves publishes no markets")
for market_id, market in markets.items():
    series = market["observations"]
    if len(series) < 2:
        bad.append(f"{market_id}: {len(series)} observation(s) -- a series needs a second point "
                   f"before any consumer can derive a move")
    dates = [point["date"] for point in series]
    if dates != sorted(dates):
        bad.append(f"{market_id}: the series is not in date order")
    if len(set(dates)) != len(dates):
        bad.append(f"{market_id}: two readings share a date")
    for point in series:
        if not 0.0 <= point["price_level"] <= 1.0:
            bad.append(f"{market_id} {point['date']}: price_level {point['price_level']} is "
                       f"outside [0,1]")
    for field in ("venue", "question", "category", "resolution_source"):
        if not market.get(field):
            bad.append(f"{market_id}: no {field}")
if payload.get("venue") != "polymarket":
    bad.append(f"venue is {payload.get('venue')!r}: version 1 reads ONE venue (ticket 22 answer 2)")
if not re.fullmatch(r"market-moves/rule\.yaml@\d+", payload.get("selection_rule", "")):
    bad.append(f"selection_rule {payload.get('selection_rule')!r} names no versioned rule file")

readings = sum(len(m["observations"]) for m in markets.values())
if bad:
    for line in bad:
        print(f"not ok  {line}")
    sys.exit(1)
print(f"ok  {len(markets)} markets, {readings} dated readings, every price_level in [0,1]")
print(f"ok  no probability-shaped and no moves[] field in the payload schema: a consumer derives "
      f"the move (twin/market_signals.py), the publisher never asserts one")
print(f"ok  the payload names its own versioned selection rule: {payload['selection_rule']}")
PY

echo
echo "== market-moves: the selection is mechanical -- the rule admits and refuses by name =="
selection="$(python3 fetch/market-moves.py --dry-run 2>&1 | head -1)" || \
  fail "the market-moves adapter did not run"
echo "$selection"
case "$selection" in
  *"admits 3 of 7"*min_liquidity*categories*min_horizon_days*max_horizon_days*) ;;
  *) fail "the rule did not refuse one market per rule field on the committed venue corpus" ;;
esac
echo "ok  one refusal per rule field: liquidity floor, category list, and both horizon bounds"

echo
echo "== the feed's OWN threshold is what opens a PR (D2), through the real clock =="
# The moved corpus is the committed one with ONE market's last trade moved eight
# price points -- above the five the rule declares. Nothing else differs, so the
# only thing under test is the threshold.
mkdir -p "$work/source" "$work/pinned"
cp fetch/source/*.json "$work/source/"
# a pristine copy, so the observation step below stays deterministic on the day
# read_upstream() becomes a live GET
cp fetch/source/*.json "$work/pinned/"
python3 - "$work/source/market-moves.json" <<'PY'
import json, sys
path = sys.argv[1]
corpus = json.load(open(path))
for market in corpus["markets"]:
    if market["id"] == "0x7f3c9a":
        market["lastTradePrice"] = 0.52   # published series ends 0.44: an eight-point move
json.dump(corpus, open(path, "w"), indent=2)
PY
for case in "committed none" "moved patch"; do
  set -- $case
  if [ "$1" = "moved" ]; then export FEEDS_SOURCE_DIR="$work/source"; else unset FEEDS_SOURCE_DIR; fi
  out="$(python3 fetch/market-moves.py --dry-run --observations-dir "$work/obs" 2>&1)" || \
    fail "the market-moves clock errored on the $1 corpus"
  got="$(echo "$out" | sed -n 's/.*-> \([a-z]*\)$/\1/p' | tail -1)"
  [ "$got" = "$2" ] || fail "the $1 corpus computes $got, not $2 -- the threshold in market-moves/rule.yaml is not what decides"
  echo "ok  the $1 corpus computes $2"
done
unset FEEDS_SOURCE_DIR
echo "ok  a sub-threshold reading proposes nothing; a move of at least the declared threshold does"

echo
echo "== the observation branch path: every run writes a line, and it carries the reading =="
FEEDS_SOURCE_DIR="$work/pinned" python3 fetch/market-moves.py --observations-dir "$work/obs" >/dev/null 2>&1 || \
  fail "the market-moves clock could not write an observation"
FEEDS_SOURCE_DIR="$work/pinned" python3 fetch/news.py --observations-dir "$work/obs" >/dev/null 2>&1 || \
  fail "the news clock could not write an observation"
git diff --quiet -- market-moves news || \
  fail "a clock run changed a published feed in the working tree -- a clock appends observations, never declarations (D1)"
python3 - "$work/obs" <<'PY' || exit 1
import json, os, sys
obs = sys.argv[1]
for feed in ("market-moves", "news"):
    path = os.path.join(obs, f"{feed}.jsonl")
    lines = [json.loads(line) for line in open(path)]
    assert lines, f"{path} is empty"
    line = lines[-1]
    assert line["feed"] == feed and line["bump"] == "none", line
    assert "reading" in line, f"{feed}: the observation line carries no reading, only a hash"
    print(f"ok  observations/{feed}.jsonl <- {json.dumps(line['reading'], sort_keys=True)}")
PY
lane="$(sed -n 's/^  OBSERVATION_LANE: *"\(.*\)"$/\1/p' .github/workflows/fetch.yml)"
case " $lane " in *" observations "*) echo "ok  the clock's cage lets it write only: $lane" ;;
  *) fail "the fetch workflow's observation lane does not include observations/" ;; esac
grep -q "feed: \[.*market-moves.*news.*\]" .github/workflows/fetch.yml || \
  fail "the daily fetch matrix does not carry both new feeds"
echo "ok  both feeds are on the daily clock's matrix"

echo
echo "== news: the minimal payload, admitted only with a provenance URL =="
refusal="$(python3 fetch/news.py --dry-run 2>&1 | head -1)"
echo "$refusal"
case "$refusal" in
  *"admits 4 of 5"*requires_provenance_url*) ;;
  *) fail "the news rule did not refuse the pool entry that records no URL" ;;
esac
python3 - <<'PY' || exit 1
import json, sys
bad = []
feed = json.load(open("news/v1/feed.json"))
allowed = {"id", "date", "source", "statement", "provenance"}
for event in feed["payload"]["events"]:
    extra = set(event) - allowed
    if extra:
        bad.append(f"{event.get('id')}: carries {sorted(extra)} -- the news payload is minimal, "
                   f"and every judgement is a claim on the twin side")
    if not str(event.get("provenance", {}).get("url", "")).startswith(("http://", "https://")):
        bad.append(f"{event.get('id')}: no provenance url")
    if "steep" in event:
        bad.append(f"{event.get('id')}: carries a steep tag, which is a judgement the skill makes")
schema = json.load(open("news/payload.schema.json"))
item = schema["properties"]["events"]["items"]
if item.get("additionalProperties") is not False:
    bad.append("the news event schema is open, so a judgement could ride in anyway")
if sorted(item["required"]) != sorted(allowed):
    bad.append(f"the news event schema requires {item['required']}, not the five decided fields")
if "steep" in item["properties"] or "steep" in schema["properties"]:
    bad.append("the news payload schema declares a steep property: the feed never carries one")
if bad:
    for line in bad:
        print(f"not ok  {line}")
    sys.exit(1)
print(f"ok  {len(feed['payload']['events'])} events, each with exactly id, date, source, "
      f"statement and a provenance url -- no steep, no severity, no relevance")
PY

echo
echo "== news: the threshold fires on a new event and not on a re-read =="
python3 - "$work/source/news.json" <<'PY'
import json, sys
path = sys.argv[1]
pool = json.load(open(path))
pool["events"].append({
    "id": "driftwood-composed-1-1-0-tagged",
    "date": "2026-08-25",
    "source": "policy-as-versioned-driftwood",
    "statement": "driftwood published the signed tag v1.1.0 of its composed artefact.",
    "provenance": {"url": "https://github.com/policy-as-versioned-driftwood/driftwood/releases/tag/v1.1.0"},
})
json.dump(pool, open(path, "w"), indent=2)
PY
for case in "committed none" "moved minor"; do
  set -- $case
  if [ "$1" = "moved" ]; then export FEEDS_SOURCE_DIR="$work/source"; else unset FEEDS_SOURCE_DIR; fi
  out="$(python3 fetch/news.py --dry-run --observations-dir "$work/obs" 2>&1)" || \
    fail "the news clock errored on the $1 pool"
  got="$(echo "$out" | sed -n 's/.*-> \([a-z]*\)$/\1/p' | tail -1)"
  [ "$got" = "$2" ] || fail "the $1 pool computes $got, not $2"
  echo "ok  the $1 pool computes $2"
done
unset FEEDS_SOURCE_DIR
git diff --quiet -- news market-moves || fail "a clock run left a declaration in the working tree"

echo
echo "== niobium is a SCENARIO and is absent from this feed (ticket 23 answer 1) =="
# Over the DATA, not the files: a comment explaining why niobium is not here is
# not a violation, and a JSON walk cannot be fooled by one either way.
python3 - <<'PY' || exit 1
import glob, json, sys

def strings(node, where):
    if isinstance(node, str):
        yield where, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from strings(value, f"{where}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from strings(value, f"{where}[{index}]")

bad = []
scanned = 0
for path in sorted(glob.glob("*/v*/feed.json")) + ["fetch/source/news.json"]:
    scanned += 1
    for where, text in strings(json.load(open(path)), path):
        if "niobium" in text.lower():
            bad.append(f"{where}: {text[:80]!r}")
if bad:
    for line in bad:
        print(f"not ok  niobium in published data at {line}")
    sys.exit(1)
print(f"ok  {scanned} published payloads and the news pool carry no niobium anywhere in their "
      f"data: it is a SCENARIO in the adopter's twin library (ticket 29), not an observation")
PY

echo
echo "== no clock in this repository invokes a model (ADR-0024) =="
clocks="$(grep -rl "^on:" .github/workflows | xargs grep -l "schedule:")"
echo "scheduled workflows: $(echo $clocks)"
model='anthropic|openai|ollama|huggingface|gpt-[0-9]|API_KEY'
for f in fetch/*.py bump.py; do
  hit="$(grep -rniE "$model" "$f" || true)"
  [ -z "$hit" ] || fail "$f reaches for a model: $hit"
done
# A scheduled workflow may not invoke a model NOR the human-run skill. The
# adapters name the skill in their prose, which is a signpost and not a call, so
# the skill-invocation half is asserted where an invocation could actually live.
for f in $clocks; do
  hit="$(grep -rniE "$model"'|claude-code|\.claude/skills|classify-and-judge' "$f" || true)"
  [ -z "$hit" ] || fail "$f reaches for a model or invokes the human-run skill: $hit"
done
echo "ok  no fetch adapter names a model endpoint or key"
echo "ok  no scheduled workflow calls a model or invokes classify-and-judge: the clock gathers,"
echo "ok  and reasoning is a skill a human runs (the skill is marked disable-model-invocation)"

echo
echo "PASS: market-moves publishes a dated series from one mechanical rule over one venue with no probability-shaped field, and its own threshold is what opens a PR; news carries the five decided fields and admits nothing without a provenance URL; sub-threshold readings land on the observation branch carrying the reading; niobium is absent from the feed; no clock here invokes a model."
exit 0
