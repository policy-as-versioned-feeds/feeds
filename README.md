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

- **CVE and FX read primary sources on the clock.** CVE joins CISA KEV membership,
  NVD CVSS severity and FIRST's dated EPSS reading; a missing joined record refuses.
  FX reads HMRC's monthly CSV for the current UTC month; `FEEDS_FX_PERIOD` selects
  a reviewed historical month. `FEEDS_SOURCE_DIR=fetch/source` supplies committed
  offline replay inputs. The CVE replay preserves the build inputs and hashes of
  the original complete responses; the FX replay contains the captured August
  2026 HMRC payload. Neither replay claims a new observation date. Other adapters
  still read their committed fixture corpora through `lib.read_upstream()`.
- **Old major payloads remain frozen history.** The migrated originals carry
  their former body-level `feed_version` and `published_by`; the envelope is
  authoritative. CVE v3 replaces the illustrative entries with the captured
  primary-source corpus. Threat-register v4 adds a cited frequency row and keeps
  v3 headline magnitudes unchanged. FX 1.1.0 replaces the illustrative August
  rates with that month's authentic HMRC rates, using the same payload schema.
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

## Publisher reliability converter modes

The standalone `threat-register/to_fair_scenario.py` adds two explicit modes; existing
converter commands and published payloads keep their behavior:

```
python3 threat-register/to_fair_scenario.py forecast-base payload.json context.json
python3 threat-register/to_fair_scenario.py widen-to payload.json context.json
```

Both inputs are JSON; the payload is unwrapped with the existing converter version-key normalization (preserve a supplied key; otherwise use the authenticated selected edge version). `forecast-base` accepts only the
closed `publisher-reliability/generator-context-v1` wrapper (`schema`, exact
`source` reference, and complete parsed `document`). It returns the existing
headline FAIR scenario using that document's party. A missing or malformed declared native currency refuses by name.
The complete document must select this publisher/feed exactly once. No caller-selected scenario, institution or extra converter flags enter this mode.

`widen-to` accepts the closed `publisher-reliability/widen-context-v1` context.
Its adopter context is an exact cross-source reference or an exact same-tree
`{path, git_blob}` under the enclosing adopter source; historical generator
contexts still require the complete signed source reference.
Run it in the authenticated publisher snapshot: `context.widening.path` selects
the declaration, read as a regular file without symbolic links and checked
against its actual Git blob. The widening may be a different immutable release
from the target under the same publisher. The complete declared bounded-PERT
scenario must preserve identity, state frequencies and LM source arrangement;
LM components cannot narrow and every changed source must be declared. The
result carries the declaration's actual profile ID and preserves authority.
The consumer independently admits signatures, profile/unit bindings, release-cage
proof and applicability; a context or result is no authentication receipt.

There is no production target, forecast, outcome, bar or new feed release here.
A portable widening closure includes its selected declaration beside the copied
converter and input files; ordinary legacy replay still needs no sibling module.

The source-only opt-in native proof uses `.github/scripts/publisher-release-gate.py`:

```sh
python3 .github/scripts/publisher-release-gate.py build threat-register threat-register/v3.0.1 native.json cage.json
python3 .github/scripts/publisher-release-gate.py verify cage.json threat-register/v3.0.1
```

Commit the semantic target, existing native code, rule and bump declaration before
building. The build writes only new proof files. After inspecting them, a future
enrollment adds the exact cage path/Git blob to `payload.release_cage`, commits
the proof and pointer, and uses the ordinary signed release path. The new
`threat-register/payload.release-cage.schema.v1.json` permits this optional pointer; no
existing payload selects it. Changing `payload_schema` still computes a major.
The pre-sign workflow reproduces an enrolled proof; without a pointer its
existing release gates apply unchanged.

The proof uses the publisher's actual existing native computation. An input,
history, structural or tag-legality fault refuses. Only a successfully computed
bump above the declared rung is degraded: the exact requested tag must then be
`-quarantine.N`, with quarantine tier/suffix. Equal or stronger declarations
produce a clean baseline release. The tag must still be the exact declared
increment of the maximal clean predecessor. Complete first-parent Git history
and annotated tags are required; Git tag dates/order are publisher assertions,
not an independent clock. Later descendant tags do not change replay.

Native evidence binds code/rule/declaration blobs, captured release history and
predecessor, and a canonical target semantic hash excluding **only**
`payload.release_cage` to avoid a pointer/hash cycle. That projection hash is not
a raw Git blob. The outer proof separately binds actual native-evidence and
gate-code Git blobs. The consumer must authenticate the full publisher source,
its release tags and closure before executing the public replay CLI. Neither
this helper nor an input descriptor is signature admission. No current financial
value, proof, tag or enrollment is manufactured by this capability.
