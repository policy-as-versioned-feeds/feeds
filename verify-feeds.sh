#!/usr/bin/env bash
# Ticket 21, the feed contract, observed in this repo. Offline -- no cluster,
# no network, no tag required.
#
# What it observes:
#   1. every published <feed>/v<N>/feed.json validates against the ONE envelope
#      schema, platform/feeds/schema.json (ADR-0019 point 1);
#   2. every payload validates against the payload_schema its own envelope
#      names, so a consumer can check the payload as well as the wrapper;
#   3. bump.py's ladder holds on its four decided cases (ADR-0023, D2);
#   4. every path party.yaml publishes exists, because publishes[] IS the
#      catalogue (ADR-0019 point 5) and a catalogue entry pointing at nothing
#      is a lie.
#
# Gate contract: exit 0 observed true, exit 3 could not look (last line
# SKIP: ...), anything else observed false (last line FAIL: ...).
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

# platform holds the envelope schema. Prefer an explicit PLATFORM_DIR (the
# release workflow sets it to its second checkout), then the sibling clone.
platform="${PLATFORM_DIR:-}"
if [ -z "$platform" ]; then
  for candidate in "$here/../platform" "$here/.platform"; do
    [ -f "$candidate/feeds/schema.json" ] && platform="$candidate" && break
  done
fi
schema="${platform:+$platform/feeds/schema.json}"
if [ -z "$schema" ] || [ ! -f "$schema" ]; then
  echo "no platform checkout with feeds/schema.json next to this repo"
  echo "SKIP: cannot look -- the envelope schema lives at platform/feeds/schema.json (ADR-0019) and no platform checkout was found; set PLATFORM_DIR"
  exit 3
fi

echo "== envelope schema: $schema =="
python3 - "$schema" "${platform}/feeds/forward-intel.payload.schema.json" <<'PY'
import json, os, re, sys

schema_path = sys.argv[1]
failures = []


def check(node, schema, where):
    """Draft-07, the subset these two schemas use. Hand-rolled for the same
    reason platform/party/party_artefact.py hand-rolls its own: python3 in the
    estate has no jsonschema, and the shapes are small."""
    if "enum" in schema and node not in schema["enum"]:
        failures.append(f"{where}: {node!r} not one of {schema['enum']}")
        return
    types = schema.get("type")
    if types:
        types = [types] if isinstance(types, str) else types
        ok = {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "null": lambda v: v is None,
        }
        if not any(ok[t](node) for t in types if t in ok):
            failures.append(f"{where}: expected {types}, got {type(node).__name__}")
            return
    if isinstance(node, str):
        if len(node) < schema.get("minLength", 0):
            failures.append(f"{where}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], node):
            failures.append(f"{where}: {node!r} does not match {schema['pattern']}")
        if schema.get("format") == "date-time" and not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})", node):
            failures.append(f"{where}: {node!r} is not an RFC3339 date-time")
    if isinstance(node, list):
        if len(node) < schema.get("minItems", 0):
            failures.append(f"{where}: fewer than minItems {schema['minItems']}")
        if "maxItems" in schema and len(node) > schema["maxItems"]:
            failures.append(f"{where}: more than maxItems {schema['maxItems']}")
        if "items" in schema:
            for index, item in enumerate(node):
                check(item, schema["items"], f"{where}[{index}]")
    if isinstance(node, dict):
        for field in schema.get("required", []):
            if field not in node:
                failures.append(f"{where}: missing required {field!r}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in node.items():
            if key in properties:
                check(value, properties[key], f"{where}.{key}")
            elif isinstance(extra, dict):
                check(value, extra, f"{where}.{key}")
            elif extra is False:
                failures.append(f"{where}: unexpected property {key!r}")


envelope = json.load(open(schema_path))
feeds = sorted(d for d in os.listdir(".")
               if os.path.isdir(d) and os.path.exists(os.path.join(d, "payload.schema.json")))
if not feeds:
    failures.append("no feed directory carries a payload.schema.json")

published = 0
for feed in feeds:
    for entry in sorted(os.listdir(feed)):
        path = os.path.join(feed, entry, "feed.json")
        if not re.fullmatch(r"v\d+", entry) or not os.path.exists(path):
            continue
        published += 1
        doc = json.load(open(path))
        before = len(failures)
        check(doc, envelope, path)
        # the envelope's own facts have to agree with where it lives
        if doc.get("name") != feed:
            failures.append(f"{path}: name {doc.get('name')!r} is not {feed!r}")
        if doc.get("version", "").split(".")[0] != entry[1:]:
            failures.append(f"{path}: version {doc.get('version')!r} is not a v{entry[1:]} release")
        payload_schema = doc.get("payload_schema", "")
        if not os.path.exists(payload_schema):
            failures.append(f"{path}: payload_schema {payload_schema!r} does not exist")
        else:
            check(doc.get("payload"), json.load(open(payload_schema)), f"{path}:payload")
        if len(failures) == before:
            print(f"ok  {path} -> envelope + {payload_schema}")
    # the sidecars beside the feed: rule.yaml (what "changed" means, D2) and bump.yaml
    # (the declared bump for the next release) -- a feed with no declared bump cannot be tagged
    for side in ("rule.yaml", "bump.yaml"):
        if not os.path.isfile(os.path.join(feed, side)):
            failures.append(f"{feed}/{side} missing beside the feed")
    bump = next((line.split(":", 1)[1].strip() for line in open(os.path.join(feed, "bump.yaml"))
                 if line.startswith("bump:")), None) if os.path.isfile(os.path.join(feed, "bump.yaml")) else None
    if bump not in ("major", "minor", "patch", "none"):
        failures.append(f"{feed}/bump.yaml declares {bump!r}, not major|minor|patch|none")

if published == 0:
    failures.append("no published <feed>/v<N>/feed.json found")
else:
    print(f"ok  {published} published feed versions validated")

# publishes[] IS the catalogue: every path it names must exist. Flat scan, no
# pyyaml -- the runner is not promised it.
paths = re.findall(r"^\s+(?:path|payload_schema):\s*(\S+)\s*$", open("party.yaml").read(), re.M)
if not paths:
    failures.append("party.yaml declares no publishes[] paths")
for path in paths:
    if not os.path.exists(path):
        failures.append(f"party.yaml publishes {path!r}, which does not exist")
    else:
        print(f"ok  party.yaml publishes {path}")

# The ADR-0021 forward-intel payload schema (2.0.0, ticket 15 amendment C10).
# It lives beside the envelope schema in platform because it is the twin's
# contract with every estate, not one publisher's feed; this is the script in
# the gate that already carries a draft-07 checker, so it checks it here.
forward_intel_path = sys.argv[2]
if not os.path.exists(forward_intel_path):
    print(f"no forward-intel payload schema at {forward_intel_path}")
    sys.exit(3)

forward_intel = json.load(open(forward_intel_path))
scenario = {
    "perspective": "driftwood",
    "shock": "a cart PII disclosure through an unrestricted egress path",
    "horizon": 1,
    "lef": None,
    "lm": {"model": "lognormal-gpd", "mu": 11.6, "sigma": 1.4,
           "u": 250000, "xi": 0.35, "beta": 180000},
    "currency": "GBP",
    "curve": [
        {"account": "baseline", "net_cost_of_risk": 412000.0},
        {"account": "restricted", "net_cost_of_risk": 188000.0},
        {"account": "quarantine", "net_cost_of_risk": 141000.0},
        {"account": "isolated", "net_cost_of_risk": 203000.0},
    ],
    "register": [
        {"source": "nist", "id": "cp-9", "tier": "quarantine",
         "note": "named by the uk-gdpr higher-tier weights, no adopter scenario prices it yet"},
    ],
    "claim_scope": {"included": ["uk-gdpr", "nist:sc-28"], "excluded": ["pci-dss"]},
    "derived_from": [
        {"party": "ico", "kind": "feed", "name": "penalty-schema", "version": "3.0.0"},
        {"party": "feeds", "kind": "feed", "name": "fx", "version": "1.0.0"},
    ],
}
before = len(failures)
check(scenario, forward_intel, "forward-intel:sample")
if len(failures) == before:
    print(f"ok  a twin scenario validates against {forward_intel_path}")

triple = dict(scenario, lm=[80000, 340000, 2100000])
before = len(failures)
check(triple, forward_intel, "forward-intel:sample(lm triple)")
if len(failures) == before:
    print("ok  the same schema takes an lm triple as well as a lognormal-GPD severity spec")

# and it bites: C10's three keys are required, so a 1.0.0-shaped payload fails.
before = len(failures)
old_shape = {k: v for k, v in scenario.items()
             if k not in ("register", "claim_scope", "derived_from")}
check(old_shape, forward_intel, "forward-intel:1.0.0-shaped")
bitten = failures[before:]
del failures[before:]
if len(bitten) == 3:
    print("ok  a 1.0.0-shaped payload fails on all three C10 keys: "
          + "; ".join(sorted(line.split("missing required ")[-1] for line in bitten))
          + " -- which is why C10 is one major")
else:
    failures.append(f"forward-intel: expected 3 C10 keys to be required, got {bitten}")

if "recommended_action" in forward_intel.get("properties", {}):
    failures.append("forward-intel: the payload carries a recommended action, and ADR-0021 says never")
if forward_intel.get("additionalProperties") is not False:
    failures.append("forward-intel: the payload is open, so a recommended action could ride in anyway")
ladder = ["baseline", "restricted", "quarantine", "isolated", "infra"]
got_ladder = (forward_intel["properties"]["register"]["items"]
              ["properties"]["tier"]["enum"])
if got_ladder != ladder:
    failures.append(f"forward-intel: register tier enum is {got_ladder}, not the ladder {ladder}")
else:
    print(f"ok  a register entry takes a tier off the ladder {ladder}")

if failures:
    for line in failures:
        print(f"not ok  {line}")
    sys.exit(1)
PY
schema_rc=$?
[ $schema_rc -ne 3 ] || { echo "SKIP: the platform checkout carries no forward-intel payload schema (ADR-0021)"; exit 3; }
[ $schema_rc -eq 0 ] || { echo "FAIL: a published feed does not match the envelope or its payload schema"; exit 1; }

echo
echo "== bump ladder (ADR-0023, D2) =="
if ! python3 bump.py selfcheck; then
  echo "FAIL: bump.py selfcheck failed -- the computed bump is what opens a release PR"
  exit 1
fi

echo
echo "== the rule each feed publishes is the rule bump.py reads =="
for feed in threat-register cve eol; do
  got=$(python3 bump.py "$feed/v1/feed.json" "$feed/v2/feed.json" "$feed/rule.yaml") || {
    echo "FAIL: bump.py could not compare $feed v1 with v2"; exit 1; }
  echo "ok  $feed v1 -> v2 computes $got"
done

echo
echo "== fx: the rule computes a new month as a minor and a corrected rate as a patch =="
fxwork="$(mktemp -d)"
trap 'rm -rf "$fxwork"' EXIT
python3 - "$fxwork" <<'PY'
import json, sys
work = sys.argv[1]
published = json.load(open("fx/v1/feed.json"))
month = dict(published, payload=dict(published["payload"],
                                     period="2026-09",
                                     rates=dict(published["payload"]["rates"], USD=1.2915)))
corrected = dict(published, payload=dict(published["payload"],
                                         rates=dict(published["payload"]["rates"], USD=1.2841)))
json.dump(month, open(f"{work}/new-month.json", "w"))
json.dump(corrected, open(f"{work}/corrected-rate.json", "w"))
PY
for case in "new-month minor" "corrected-rate patch"; do
  set -- $case
  got=$(python3 bump.py fx/v1/feed.json "$fxwork/$1.json" fx/rule.yaml) || {
    echo "FAIL: bump.py could not compare the published fx month with $1"; exit 1; }
  [ "$got" = "$2" ] || { echo "FAIL: fx/rule.yaml says $1 is a $2, bump.py computed $got"; exit 1; }
  echo "ok  fx $1 computes $got"
done

echo
echo "== fx: a rate lookup for a published date, and a refusal for one with no rate (ADR-0020) =="
if ! python3 converters/fx.py selfcheck; then
  echo "FAIL: converters/fx.py selfcheck failed -- the fx converter is what refuses a missing rate"
  exit 1
fi
known=$(python3 converters/fx.py convert 1000 GBP USD 2026-08-14) || {
  echo "FAIL: no conversion for 2026-08-14, a date the published fx feed covers"; exit 1; }
echo "ok  1000 GBP -> $known USD on 2026-08-14, at the published HMRC rate"
if refusal=$(python3 converters/fx.py convert 1000 GBP USD 2026-05-14 2>&1); then
  echo "FAIL: 2026-05-14 has no published fx rate and the converter returned $refusal anyway"
  exit 1
fi
case "$refusal" in
  MISSING\ INSTRUMENT*) echo "ok  2026-05-14 refuses: $refusal" ;;
  *) echo "FAIL: 2026-05-14 failed for some other reason than a missing instrument: $refusal"; exit 1 ;;
esac

echo
echo "PASS: every published feed is one envelope validated against platform/feeds/schema.json and its own payload schema; rule.yaml and bump.yaml sit beside each feed; the bump ladder holds; publishes[] names only real paths; a twin scenario validates against the 2.0.0 forward-intel payload schema; fx prices a date it publishes and refuses one it does not."
exit 0
