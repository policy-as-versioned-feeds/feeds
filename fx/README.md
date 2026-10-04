# Dated HMRC FX snapshots

Each envelope quotes foreign-currency units per GBP1 for its own calendar month.
GBP is the base and has rate 1. A USD amount reaches GBP by dividing by that
month's USD rate; a date in another month has no instrument in this envelope.

The August 2026 `fx/v1/feed.json` (signed fx/v1.1.0) and its default offline replay
remain byte unchanged. The December 2025 source at `fx/v2/feed.json` is normalized
from HMRC's complete official monthly CSV. Its USD rate is 1.3126 per GBP1 for
1–31 December 2025. Consumption requires the ordinary genuine signed fx/v2.0.0
release; these source bytes do not create a tag or verify a signature.

`fetch/source/hmrc/` retains both complete primary CSVs and `PROVENANCE.json`
records their official URLs, byte hashes, parser identity and derived payload
hashes. The actual published `fetch/fx.py` parser reproduces both tables.
`fetch/source/periods/2025-12/fx.json` is an explicit offline December replay;
the default `fetch/source/fx.json` continues to carry August. A replay does not
claim a new upstream observation:

```sh
FEEDS_SOURCE_DIR=fetch/source/periods/2025-12 python3 fetch/fx.py --dry-run
```

The unchanged publisher rule measures the December snapshot as **major**
against 1.1.0: VES is absent in December, while BGN and VED are present. No
currency code is silently renamed, no rate is projected, and the earlier
August envelope remains available. The normal next-version function yields
2.0.0. `party.yaml` already publishes the FX namespace and payload schema;
its catalogue needs no duplicate row for another major.

The existing converter reads all major directories by their actual `period`.
It can therefore retain August and resolve December without a new payload
shape. A consumer must pin the actual signed tag and peeled commit for the
matching month. No matching signed rate means a missing instrument, never
zero or another month's number.
