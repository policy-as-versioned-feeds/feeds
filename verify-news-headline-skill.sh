#!/usr/bin/env bash
# Ecosystem ticket 50: the headline skill, and the twin's binding of the pinned
# market-moves series. The two feeds this repository publishes are the pool that
# skill reads, which is why the check lives here -- the gate discovers verify
# scripts under .estate-clone/ and verify/, and the skill itself lives in the hub
# checkout beside this clone.
#
# What it observes:
#   1. the skill exists, is marked disable-model-invocation, and says in its own
#      words that no clock may run it (ADR-0024, C4);
#   2. its claim file carries ONLY claim kinds the twin already has, read from
#      twin/schema.py itself, and `derived_from` names every pin the claims cite
#      and nothing it does not (ticket 50's gate check);
#   3. only an override prices -- and the validator BITES on each rule, proved
#      by mutating the example and watching it fail;
#   4. the twin BINDS the pinned series: twin/market_signals.py derives dated
#      MOVES from this repository's published market-moves feed, refuses to read
#      a level as a probability, and signal-classify binds a derived move to a
#      component in the adopter's own overlay;
#   5. niobium lives in the adopter's twin scenario library and not in the news
#      feed (the other half of verify-market-and-news.sh's absence check).
#
# Gate contract: exit 0 observed true, exit 3 could not look (last line
# SKIP: ...), anything else observed false (last line FAIL: ...).
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

fail() { echo "FAIL: $*"; exit 1; }
skipped() { echo "SKIP: $*"; exit 3; }

# The hub checkout: it holds the skill, the twin package and the adopter clones.
hub="${HUB_DIR:-}"
if [ -z "$hub" ]; then
  for candidate in "$here/../.." "$here/../../.."; do
    [ -f "$candidate/twin/schema.py" ] && hub="$(cd "$candidate" && pwd)" && break
  done
fi
skill="${hub:+$hub/.claude/skills/classify-and-judge}"
[ -n "$hub" ] && [ -f "$skill/SKILL.md" ] || \
  skipped "cannot look -- the classify-and-judge skill and the twin package live in the hub checkout, and none was found beside this clone; set HUB_DIR"

echo "== the skill is a skill a human runs, never a clock =="
grep -q '^disable-model-invocation: true$' "$skill/SKILL.md" || \
  fail "the skill is not marked disable-model-invocation: a model could invoke it unattended"
grep -qi 'ever runs on a clock' "$skill/SKILL.md" || \
  fail "the skill does not say that nothing in it runs on a clock"
grep -qiE 'never[^a-z]{0,4}merge' "$skill/SKILL.md" || \
  fail "the skill does not forbid merging its own PR -- the reviewed PR is the unit of adoption"
grep -qi 'adopter' "$skill/SKILL.md" || fail "the skill does not say whose repo its PR lands on"
echo "ok  $skill/SKILL.md: disable-model-invocation, no clock, opens a PR it never merges"

echo
echo "== the claim file: only existing claim kinds, and derived_from names them =="
python3 "$skill/assets/validate_claim.py" "$skill/assets/example-claim.yaml" --twin "$hub" || \
  fail "the skill's own worked claim file does not validate"

echo
echo "== and the check bites: each rule, mutated, is caught =="
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
mutate() {  # <name> <python expression over `doc`> <expected phrase>
  python3 - "$skill/assets/example-claim.yaml" "$work/mutant.yaml" "$2" <<'PY'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
exec(sys.argv[3])
yaml.safe_dump(doc, open(sys.argv[2], "w"))
PY
  out="$(python3 "$skill/assets/validate_claim.py" "$work/mutant.yaml" --twin "$hub" 2>&1)"
  if [ $? -eq 0 ]; then fail "the validator accepted a claim file where $1"; fi
  case "$out" in
    *"$3"*) echo "ok  caught: $1" ;;
    *) fail "the validator refused '$1' for the wrong reason: $out" ;;
  esac
}
mutate "a claim invents a kind" \
  "doc['claims'][0]['kind'] = 'headline'" "is not one the twin has"
mutate "a grade-5 binding claims to price" \
  "doc['claims'][0]['price_eligible'] = True" "only an override prices"
mutate "an override is claimed by free text instead of a role" \
  "[c for c in doc['claims'] if c['kind']=='override'][0]['claimed_by'] = 'chris'" \
  "is not a role in twin/roles.yaml"
mutate "an override answers no retained estimate" \
  "[c for c in doc['claims'] if c['kind']=='override'][0].pop('answers')" \
  "must keep the estimate it overrules"
mutate "a claim cites a pin derived_from does not name" \
  "doc['derived_from'] = doc['derived_from'][:1]" "which derived_from does not name"
mutate "derived_from names a pin no claim cites" \
  "doc['derived_from'].append({'party': 'ico', 'kind': 'feed', 'name': 'penalty-schema', 'version': '3.0.0'})" \
  "which no claim cites"

echo
echo "== every claim file a real run has landed in an adopter repo, by the same rules =="
landed=0
for claim in "$hub"/.estate-clone/*/twin/claims/*.claim.yaml; do
  [ -f "$claim" ] || continue
  landed=$((landed + 1))
  python3 "$skill/assets/validate_claim.py" "$claim" --twin "$hub" || \
    fail "$claim does not validate: a claim file in an adopter repo is the skill's output and is held to its own rules"
done
[ "$landed" -gt 0 ] || echo "ok  no adopter repo carries a claim file yet -- the skill has not been run for real; the worked example above is what the gate holds to the rules"

echo
echo "== the twin binds the pinned series =="
python3 - "$hub" "$here" <<'PY' || exit 1
import json, os, sys, glob

hub, feeds = sys.argv[1], sys.argv[2]
sys.path.insert(0, hub)
try:
    from twin.market_signals import (PriceObservation, PriceLevelAsProbabilityError,
                                     as_probability, move_statement, price_moves)
    from twin.signal_classify import classify
except Exception as exc:  # noqa: BLE001
    print(f"SKIP: the twin package at {hub} cannot be imported ({exc})")
    sys.exit(3)

feed = json.load(open(os.path.join(feeds, "market-moves", "v1", "feed.json")))
observations = [PriceObservation(market_id, market["venue"], point["date"], point["price_level"])
                for market_id, market in feed["payload"]["markets"].items()
                for point in market["observations"]]
moves = price_moves(observations)
if not moves:
    print("not ok  the published series derives no move at all")
    sys.exit(1)
print(f"ok  twin/market_signals.price_moves derives {len(moves)} dated moves from "
      f"market-moves {feed['version']}, {len(observations)} readings over "
      f"{len(feed['payload']['markets'])} markets")
biggest = max(moves, key=lambda move: abs(move.delta))
print(f"ok  the largest is {biggest.delta:+.2f}: {move_statement(biggest)}")

try:
    as_probability(observations[0])
except PriceLevelAsProbabilityError as exc:
    print(f"ok  and a LEVEL still refuses to be read as a probability: {str(exc)[:96]}...")
else:
    print("not ok  a price level was read as a probability")
    sys.exit(1)

# The overlay's own component ids are the candidates a binding may name.
import yaml
overlay = os.path.join(hub, ".estate-clone", "driftwood", "twin")
if not os.path.isdir(overlay):
    print("SKIP: no driftwood checkout beside this one to bind a derived move against")
    sys.exit(3)
candidates = []
for path in sorted(glob.glob(os.path.join(overlay, "*", "*", "components", "*.yaml")) +
                   glob.glob(os.path.join(overlay, "world", "components", "*.yaml"))):
    doc = yaml.safe_load(open(path))
    candidates.append({"id": str(doc["id"]), "name": str(doc["name"])})
out = classify({"statement": move_statement(biggest), "source": biggest.venue,
                "candidates": candidates})
claim = out["claim"]
if claim["kind"] != "binding" or claim["evidence_grade"] != 5:
    print(f"not ok  signal-classify returned {claim}")
    sys.exit(1)
if claim["component"] not in {c["id"] for c in candidates}:
    print(f"not ok  bound to {claim['component']!r}, which is not a component in the overlay")
    sys.exit(1)
print(f"ok  signal-classify binds that move to {claim['component']!r} in driftwood's overlay at "
      f"grade {claim['evidence_grade']}, steep {out['steep']!r} -- a PROPOSAL the human reviews")

scenario = os.path.join(overlay, "orgs", "driftwood", "scenarios",
                        "niobium-supply-shock-2026.yaml")
if not os.path.isfile(scenario):
    print(f"not ok  no niobium scenario at {scenario}: ticket 23 answer 1 says it lives in the "
          f"scenario library, and it is in neither place")
    sys.exit(1)
lookup = yaml.safe_load(open(os.path.join(overlay, "signals.yaml")))
unbound = {row["scenario"] for row in lookup.get("unbound_scenarios", [])}
if "niobium-supply-shock-2026" not in unbound:
    print("not ok  the niobium scenario is bound by the clock's lookup table, so a headline "
          "would bind without a human")
    sys.exit(1)
print("ok  niobium is a scenario in driftwood's library, declared unbound by any pinned feed "
      "version: it reaches the twin only through the human-run skill")
PY
rc=$?
[ $rc -ne 3 ] || { echo "SKIP: the twin package or the driftwood overlay could not be read from this checkout"; exit 3; }
[ $rc -eq 0 ] || fail "the twin does not bind the published market-moves series"

echo
echo "PASS: classify-and-judge is a human-run skill (disable-model-invocation) whose claim file carries only claim kinds the twin has and a derived_from that names exactly the pins its claims cite, with only the override price-eligible and every rule proved to bite; the twin derives dated moves from the pinned market-moves series and still refuses to read a level as a probability; niobium is a scenario in the adopter's library, unbound by any clock."
exit 0
