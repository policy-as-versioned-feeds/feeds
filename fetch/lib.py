#!/usr/bin/env python3
"""The shared body of every `fetch/<feed>.py`.

One scheduled fetch per feed (ADR-0023, decision D2): read upstream, compute
the bump against what is published under this feed's own rule.yaml, and then
either stage a release PR or record one observation. It never decides: a bump
that is not "none" becomes a pull request a human merges, and nothing here
writes to main.

ponytail: "upstream" is a committed fixture under `fetch/source/<feed>.json`,
so the clock, the bump rule, the PR path and the observation path are all real
and testable offline while the network is not. Upgrade path: replace
`read_upstream()` with a `urllib.request.urlopen(upstream_url)` and a parse
into the same payload shape -- everything downstream of it already works.

Standard library only: the runner is not promised pyyaml.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import bump as bump_engine  # noqa: E402


def published_versions(feed):
    """Every published major of `feed`, as (major, path to its feed.json)."""
    found = []
    for entry in sorted(os.listdir(os.path.join(ROOT, feed))):
        match = re.fullmatch(r"v(\d+)", entry)
        path = os.path.join(ROOT, feed, entry, "feed.json")
        if match and os.path.exists(path):
            found.append((int(match.group(1)), path))
    if not found:
        raise SystemExit(f"FAIL: {feed} has no published v<N>/feed.json")
    return sorted(found)


def read_upstream(feed):
    """ponytail: a committed fixture stands in for the upstream GET."""
    with open(os.path.join(ROOT, "fetch", "source", f"{feed}.json")) as fh:
        return json.load(fh)


def next_version(version, bump):
    major, minor, patch = (int(part) for part in version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return version


def observation(feed, current, bump):
    """One line for the observation branch: a sub-threshold reading survives
    for scoring even though it never becomes a release (spec, story 11)."""
    body = json.dumps(current["payload"], sort_keys=True, separators=(",", ":")).encode()
    return {
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "feed": feed,
        "published_version": current["version"],
        "bump": bump,
        "payload_sha256": hashlib.sha256(body).hexdigest(),
    }


def main(feed, upstream_url):
    parser = argparse.ArgumentParser(description=f"scheduled fetch for the {feed} feed")
    parser.add_argument("--observations-dir", default=os.path.join(ROOT, "observations"),
                        help="where to append <feed>.jsonl when the bump is none "
                             "(the workflow points this at the observations worktree)")
    parser.add_argument("--dry-run", action="store_true",
                        help="compute and report, write nothing")
    args = parser.parse_args()

    major, latest_path = published_versions(feed)[-1]
    with open(latest_path) as fh:
        current = json.load(fh)
    rule = bump_engine.load_rule(os.path.join(ROOT, feed, "rule.yaml"))

    candidate = dict(current)
    candidate["payload"] = read_upstream(feed)
    candidate["published_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    verdict = bump_engine.compute(current, candidate, rule)
    print(f"{feed}: upstream ({upstream_url}) vs published v{current['version']} "
          f"under rule.yaml ({rule['changed_when']}) -> {verdict}")

    # The observation is written on EVERY run, whatever the verdict. It used to
    # be written only when the verdict was `none`, so the series had a hole on
    # exactly the interesting days -- and a permanent hole for as long as a
    # proposal sat unmerged, because the workflow's proposal step exits early
    # when the branch is already open (review, 2026-08-28). Story 11 wants the
    # series to survive for scoring; a series with holes where the movement was
    # cannot be scored. The line already carries the computed bump.
    line = observation(feed, current, verdict)
    if not args.dry_run:
        os.makedirs(args.observations_dir, exist_ok=True)
        with open(os.path.join(args.observations_dir, f"{feed}.jsonl"), "a") as fh:
            fh.write(json.dumps(line, sort_keys=True) + "\n")
    print(json.dumps(line, sort_keys=True))

    if verdict == "none":
        _github_output(bump=verdict, path="", version=current["version"])
        return 0

    version = next_version(current["version"], verdict)
    target = os.path.join(feed, f"v{version.split('.')[0]}", "feed.json")
    candidate["version"] = version
    if not args.dry_run:
        os.makedirs(os.path.dirname(os.path.join(ROOT, target)), exist_ok=True)
        with open(os.path.join(ROOT, target), "w") as fh:
            json.dump(candidate, fh, indent=2)
            fh.write("\n")
        _write_declared_bump(feed, verdict)
    print(f"staged {target} at {version}, {feed}/bump.yaml declares {verdict}")
    _github_output(bump=verdict, path=target, version=version)
    return 0


def _write_declared_bump(feed, verdict):
    """Rewrite the one `bump:` line, keeping the file's comment header."""
    path = os.path.join(ROOT, feed, "bump.yaml")
    with open(path) as fh:
        lines = fh.readlines()
    for index, line in enumerate(lines):
        if line.startswith("bump:"):
            lines[index] = f"bump: {verdict}\n"
            break
    else:
        lines.append(f"bump: {verdict}\n")
    with open(path, "w") as fh:
        fh.writelines(lines)


def _github_output(**values):
    out = os.environ.get("GITHUB_OUTPUT")
    if not out:
        return
    with open(out, "a") as fh:
        for key, value in values.items():
            fh.write(f"{key}={value}\n")
