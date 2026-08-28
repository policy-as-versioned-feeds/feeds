# Converters — one per feed, shipped by the feed's own publisher

A feed publishes a formula, not a price. Turning it into money needs a fact only
the consuming party holds — its size (turnover, customers, data subjects,
headcount), or the date a price is stated as of. **That step is the publisher's
code, not the consumer's**: only the party that wrote the formula knows what its
own units mean, and a converter living beside its feed moves and versions with
it (ticket 25, the £ seam).

The shape is deliberately dull:

```python
def to_lm(payload_entry, party_size) -> (min, mode, max)   # a loss magnitude triple
```

A small standard-library module, one function, no framework. `party_size` is the
`size` block off the consuming party's signed `party.yaml` (`turnover`,
`customers`, `data_subjects`, `headcount`, `as_of`). A stale size widens back to
the statutory cap; it never refuses (ADR-0020). fx is the one member of the
family whose second argument is a *date* rather than a size, because a rate is in
force for a month and for nothing else.

## Who owns what

| feed | publisher | converter | takes |
|---|---|---|---|
| `penalty-schema` | `ico` | `ico/schema/to_fair_scenario.py` | a regime/violation entry + the adopter's size → lm triple. Do not fork it here. |
| `fx` | `feeds` | `converters/fx.py` | `(amount, from, to, as_of)` → the amount in `to`. No rate for the date is a **missing instrument** and refuses. |
| `cve`, `eol`, `threat-register` | `feeds` | `platform/feeds/to_fair_scenario.py` *(still in `platform`)* | a feed entry + `--as-of` → a `fair.py` scenario. It has no size argument yet: these three price a technical event, not a percent of turnover. |

The `cve`/`eol`/`threat-register` converter is the one honest gap in the table:
its code still sits in `platform/feeds/` with the migrated copies of those feeds
(see the moved-notice in `platform/feeds/README.md`), and it belongs here beside
the feeds it converts. It moves when the composer's `feed_file()` bridge is
repointed. Nothing about it changes in the move — it is already stdlib, already
one function per feed.

## What is not here, and why

Three sizing rules from ticket 15 have **no converter in this repo and must not
get one**, because they belong to regimes whose feeds are not published yet
(ticket 24 decides them, and each converter then ships with its own publisher):

- **FCA** reads *relevant revenue* through published rate bands, with a
  publisher-shipped widening target when the adopter's revenue split is stale.
  The bands are the FCA's to publish, so the band lookup is the FCA feed's
  converter.
- **HIPAA** reads data subjects against the **annual cap × the number of
  provisions** violated, not against turnover. The cap and the provision count
  are HHS/OCR facts, so that arithmetic ships with the HIPAA feed.
- **PCI DSS** stays **size-blind** — its escalating monthly penalty does not
  read the adopter's size at all — until a publisher ships a per-card line to
  size it against. Until then a PCI price is the published band, unsized, and
  that is a real answer rather than a gap.

Today those three live inside `ico`'s `to_fair_scenario.py` as one publisher's
reading of four regimes. Splitting them out is a ticket-24 consequence, not a
thing to do quietly here.
