#!/usr/bin/env python3
"""fx converter -- an amount in one currency, at the rate published for a date.

Every feed that prices ships a converter beside it, and the converter is the
publisher's, not the consumer's (ticket 25; converters/README.md names who owns
which). Most converters take `(payload_entry, party_size)` and return a loss
magnitude triple, because most feeds publish a formula that only a party's own
size can turn into money. fx is the exception in the same family: its second
argument is a *date* rather than a size, because a rate is in force for a month
and for nothing else.

    from converters import fx
    fx.convert(1000.0, "GBP", "USD", "2026-08-14")   -> 1284.0
    fx.convert(1000.0, "GBP", "USD", "2026-05-14")   -> MissingInstrument

ADR-0020: a missing *behaviour* is priced, a missing *instrument* refuses. No
published rate for the price's as_of date is a missing instrument. It is never
widened, never zero, never last month's number: the gate cannot read, so it must
not emit a number. Callers must never sum unconverted amounts (spec, the £ seam).

Standard library only, like every other script in this repo.

ponytail: one published version carries one month, so history is only as long as
the published majors. That is the envelope's shape (`<feed>/v<MAJOR>/feed.json`
holds the latest release of that major) and it is why a date outside the current
month refuses rather than guessing. Upgrade path when a backdated price needs a
real rate: publish `periods: {YYYY-MM: {...}}` as an fx payload major and keep
this lookup, which already scans every published major and keys by month.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED = "fx"


class MissingInstrument(Exception):
    """No FX rate for this date, or no such currency in it (ADR-0020)."""


def _published(root):
    """{period: (base, rates)} across every published major of the fx feed."""
    table = {}
    feed_dir = os.path.join(root, FEED)
    for entry in sorted(os.listdir(feed_dir)) if os.path.isdir(feed_dir) else []:
        path = os.path.join(feed_dir, entry, "feed.json")
        if not re.fullmatch(r"v\d+", entry) or not os.path.exists(path):
            continue
        with open(path) as fh:
            payload = json.load(fh)["payload"]
        table[payload["period"]] = (payload["base"], payload["rates"])
    if not table:
        raise MissingInstrument(f"no published fx feed under {feed_dir}")
    return table


def rates_for(as_of, root=ROOT):
    """The base currency and rate table in force on `as_of` (YYYY-MM-DD or YYYY-MM)."""
    if not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", as_of):
        raise ValueError(f"as_of {as_of!r} is not YYYY-MM-DD or YYYY-MM")
    table = _published(root)
    month = as_of[:7]
    if month not in table:
        raise MissingInstrument(
            f"no fx rate published for {as_of}: the fx feed publishes "
            f"{', '.join(sorted(table))} (ADR-0020, a missing instrument refuses)")
    return table[month]


def convert(amount, from_currency, to_currency, as_of, root=ROOT):
    """`amount` restated in `to_currency` at the rate in force on `as_of`."""
    if from_currency == to_currency:
        return float(amount)
    base, rates = rates_for(as_of, root)
    quoted = dict(rates, **{base: 1.0})
    for currency in (from_currency, to_currency):
        if currency not in quoted:
            raise MissingInstrument(
                f"the fx feed for {as_of[:7]} quotes no rate for {currency} "
                f"(it quotes {', '.join(sorted(quoted))}); ADR-0020, refusing")
    return float(amount) * quoted[to_currency] / quoted[from_currency]


def selfcheck():
    """Observed against the published feed, not a fixture."""
    base, rates = rates_for("2026-08-14")
    assert base == "GBP", base
    got = convert(1000, "GBP", "USD", "2026-08-14")
    assert abs(got - 1000 * rates["USD"]) < 1e-9, got
    print(f"ok  1000 GBP -> {got:.2f} USD at the 2026-08 HMRC rate {rates['USD']}")

    back = convert(got, "USD", "GBP", "2026-08-31")
    assert abs(back - 1000) < 1e-6, back
    print(f"ok  {got:.2f} USD -> {back:.2f} GBP, the same month's rate both ways")

    cross = convert(100, "EUR", "USD", "2026-08-01")
    assert abs(cross - 100 * rates["USD"] / rates["EUR"]) < 1e-9, cross
    print(f"ok  100 EUR -> {cross:.2f} USD, crossed through the GBP base")

    assert convert(42, "USD", "USD", "1999-01-01") == 42.0
    print("ok  a same-currency amount needs no rate and no date")

    for bad, why in (("2026-05-14", "a month the feed does not publish"),
                     ("2027-01-31", "a month the feed has not reached")):
        try:
            convert(1000, "GBP", "USD", bad)
        except MissingInstrument as refusal:
            print(f"ok  {bad} refuses ({why}): {refusal}")
        else:
            raise AssertionError(f"{bad} returned a number with no published rate")

    try:
        convert(1000, "GBP", "XYZ", "2026-08-14")
    except MissingInstrument as refusal:
        print(f"ok  an unquoted currency refuses: {refusal}")
    else:
        raise AssertionError("XYZ returned a number with no published rate")

    print("ok  converters/fx.py selfcheck: 7 cases")


def main(argv):
    if len(argv) == 2 and argv[1] == "selfcheck":
        selfcheck()
        return 0
    if len(argv) == 6 and argv[1] == "convert":
        try:
            print(convert(float(argv[2]), argv[3], argv[4], argv[5]))
        except MissingInstrument as refusal:
            print(f"MISSING INSTRUMENT: {refusal}", file=sys.stderr)
            return 4
        return 0
    print("usage: fx.py convert <amount> <from> <to> <as_of> | selfcheck", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
