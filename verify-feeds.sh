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
python3 - "$schema" <<'PY'
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

if failures:
    for line in failures:
        print(f"not ok  {line}")
    sys.exit(1)
PY
schema_rc=$?
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
echo "PASS: every published feed is one envelope validated against platform/feeds/schema.json and its own payload schema; rule.yaml and bump.yaml sit beside each feed; the bump ladder holds; publishes[] names only real paths."
exit 0
