# policy-as-versioned-feeds / feeds

**The publisher of the estate's reactive feeds** — the institution threat
register, a trivy/GHSA-shaped CVE feed, an `endoflife.date`-shaped EOL feed, and
`fx`, the HMRC monthly exchange rates every cross-currency price is restated
through. The first three used to live inside `platform/feeds/`, which made the
platform both the substrate and a publisher. They are a party of their own now:
`feeds` publishes, everyone else pins. *(eco-system tickets 21 and 25,
[ADR-0019](https://github.com/policy-as-versioned-flux/policy-as-versioned-flux/blob/main/docs/adr/0019-one-feed-envelope-signed-by-the-tag.md),
[ADR-0020](https://github.com/policy-as-versioned-flux/policy-as-versioned-flux/blob/main/docs/adr/0020-a-missing-instrument-refuses-a-missing-behaviour-is-priced.md))*

## The contract

Every published file is **one envelope** — `kind`, `name`, `version`,
`published_by`, `published_at`, `payload_schema`, `payload` — validated against
`platform/feeds/schema.json`. There is no `signature` field: **the signature is
the gitsign tag**, and a signature cannot cover itself (ADR-0012, ADR-0019).

```
<feed>/payload.schema.json   the shape of payload, so a consumer checks the body too
<feed>/rule.yaml             what "changed" means for this feed (ADR-0023, D2)
<feed>/bump.yaml             the bump declared for the next release; one key
<feed>/v<MAJOR>/feed.json    a published version
converters/<feed>.py         the publisher's own converter: the feed prices nothing
                             until a consumer's size (or, for fx, a date) is applied
```

`converters/README.md` says which publisher owns which converter, and names the
three sizing rules (FCA rate bands, HIPAA's annual cap x provisions, PCI's
size-blindness) that are deliberately **not** here.

This repo publishes more than one feed, so a release tag names the feed:
**`<feed>/vX.Y.Z`**, e.g. `cve/v2.1.0`. A single-feed publisher (`ico`, `nist`)
stays on a plain `vX.Y.Z`. The envelope's `version` carries no leading `v`; the
tag adds it. Discovery is `publishes[]` on `party.yaml` — the set of signed
publisher artefacts *is* the catalogue, there is no central one.

## The clock

`.github/workflows/fetch.yml` runs daily at 03:17 UTC. Per feed it reads
upstream, computes the bump with `bump.py` against that feed's own `rule.yaml`,
and takes exactly one of two paths:

| computed bump | what happens |
|---|---|
| not `none` | a PR carrying the new payload and the declared bump. A human merges it, a human dispatches `cut-release.yml`. |
| `none` | one JSON line appended to `observations/<feed>.jsonl` on the `observations` branch, so a sub-threshold series survives for scoring. |

The clock **appends observations and proposes changes. It never commits a
declaration to main and it never releases** (ADR-0023, D1 and D2).

The ladder `bump.py` walks, highest wins: a `payload_schema` change is major; an
entry removed is major; an entry added is minor; changes that are only numeric
moves inside the feed's declared `numeric_tolerance` are `none`; anything else is
patch. `python3 bump.py selfcheck` asserts all of it.

## Verify

```
./verify-feeds.sh
```

Offline, no cluster, no tag. Exit 0 observed true, exit 3 could-not-look (it
needs a `platform` checkout beside this one, or `PLATFORM_DIR`, for the envelope
schema), anything else observed false. It is one of the scripts
`talk/verify-all.sh` discovers.

## Honest edges

- **The fetch is a fixture.** `fetch/source/<feed>.json` stands in for the
  upstream GET, so the clock, the rule, the PR path and the observation path are
  all real and testable offline while the network is not. Each `fetch/<feed>.py`
  names the upstream it will read. Upgrade path: swap `lib.read_upstream()` for a
  `urllib.request` call — nothing downstream changes.
- **The payloads are the migrated originals, byte for byte.** Each still carries
  its own `feed_version: "v1"` and `published_by: "platform"` inside the body.
  The envelope, not the body, is now authoritative for both: the body's copies
  are frozen history and a consumer must read `version` and `published_by` off
  the envelope.
- **The old `.sig` files did not come with them.** They signed the payload under a
  repo-local ed25519 demo key. One signature, the tag (ADR-0019 point 2).
- `market-moves` is not published here yet; it arrives with the twin's
  prediction-market work.
- **`fx` publishes one month.** The envelope keeps the latest release of a major
  at `fx/v<MAJOR>/feed.json`, so the rates in force for `period` are the only
  rates in the repo. A price stated as of any other month has no rate and
  refuses as a missing instrument (ADR-0020) rather than borrowing a neighbouring
  month's number. `converters/fx.py` names the upgrade path: a `periods:` map as
  an fx payload major, with the same lookup.
