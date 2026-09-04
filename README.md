# policy-as-versioned-feeds / feeds

**Licence:** [Apache-2.0](LICENSE) · *A demonstration party, not affiliated with, endorsed by or speaking for any real authority it names.*

**The publisher of the estate's reactive feeds** — the institution threat
register, a trivy/GHSA-shaped CVE feed, an `endoflife.date`-shaped EOL feed,
`fx`, the HMRC monthly exchange rates every cross-currency price is restated
through, `market-moves`, a dated prediction-market price series, and `news`,
dated statements with the place each was read. The first three used to live inside `platform/feeds/`, which made the
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
| `none` | nothing is proposed. |

and on **every** run, whatever the verdict, one JSON line is appended to
`observations/<feed>.jsonl` on the `observations` branch, so a sub-threshold
series survives for scoring. For `market-moves` and `news` that line carries the
**reading itself** — the day's price levels, the size of the pool — because a
hash proves only that nothing changed, and a hash is not a series.

The clock **appends observations and proposes changes. It never commits a
declaration to main and it never releases** (ADR-0023, D1 and D2).

The ladder `bump.py` walks, highest wins: a `payload_schema` change is major; an
entry removed is major; an entry added is minor; changes that are only numeric
moves inside the feed's declared `numeric_tolerance` are `none`; anything else is
patch. A feed that publishes a dated SERIES per entry (`market-moves`) declares
`series` and `move_threshold` instead, and the move of its latest reading is what
decides -- appending a reading is not "some numbers moved". `payload.<entries>`
may be a map or a list of objects each carrying an `id` (`news`'s `events[]`),
which is the same ladder over both shapes. `python3 bump.py selfcheck` asserts
all of it, 21 cases.

## Verify

```
./verify-feeds.sh                  the envelope, the payload schemas, the ladder, fx
./verify-market-and-news.sh        market-moves and news: series, rule, threshold, niobium, no model
./verify-news-headline-skill.sh    the human-run skill's claim file, and the twin binding the series
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
- **`market-moves` reads one venue, mechanically, and publishes a SERIES.**
  `market-moves/rule.yaml` is the whole of the selection (category list,
  liquidity floor, horizon window, seeded volume valve) and the whole of the
  change (`move_threshold`: five price points). There is no `moves[]` block and
  no probability-shaped field anywhere in the payload: a consumer derives the
  move (`twin/market_signals.py::price_moves`), and a price LEVEL is never a
  probability -- the twin's `as_probability` refuses outright, because the
  favourite-longshot bias makes a level a biased estimator of unknown scale,
  worst in the low-price tail (twin research 17 S3.1). Kalshi would land as a
  minor bump under the same rule; corroboration is a consumer reading two
  series, never a publisher claim.
- **Polymarket's redistribution terms are the owner's precondition for the first
  `market-moves/*` tag** (ticket 49). They were not readable from here on
  2026-08-29: `polymarket.com/tos` renders its text client-side and the docs
  index publishes no terms page. Nothing is redistributed in the meantime -- the
  committed corpus and the published series are illustrative, in the venue's
  shape and magnitude, and no fetch of Polymarket has happened.
- **`news` carries observed entries only**, and the entry is minimal: `id`,
  `date`, `source`, `statement`, `provenance.url`. No STEEP tag, no severity, no
  relevance, no subject. Every one of those is a judgement, and a judgement here
  is a grade-5 claim the `classify-and-judge` skill produces with a human at the
  keyboard, landing as a reviewed PR on the **adopter's** overlay. The required
  URL is why an invented headline cannot enter: a scenario has nowhere it was
  read. **The niobium supply shock is a scenario**, it lives in driftwood's
  `twin/orgs/driftwood/scenarios/`, and `verify-market-and-news.sh` walks every
  published payload to prove it is not here.
- **No clock in this repository invokes a model.** The fetch computes a bump
  from a rule file and appends a reading; that is all it does.
  `verify-market-and-news.sh` asserts it of every scheduled workflow and every
  adapter, and the skill that does the reasoning is marked
  `disable-model-invocation: true` so nothing unattended can call it.
- **`fx` publishes one month.** The envelope keeps the latest release of a major
  at `fx/v<MAJOR>/feed.json`, so the rates in force for `period` are the only
  rates in the repo. A price stated as of any other month has no rate and
  refuses as a missing instrument (ADR-0020) rather than borrowing a neighbouring
  month's number. `converters/fx.py` names the upgrade path: a `periods:` map as
  an fx payload major, with the same lookup.
