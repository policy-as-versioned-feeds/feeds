#!/usr/bin/env python3
"""Scheduled fetch for the fx feed. See fetch/lib.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

# ponytail: read via lib.read_upstream() from the committed fixture. Upgrade
# path: the HMRC monthly file itself --
# https://www.gov.uk/government/collections/exchange-rates-for-customs-and-vat
# publishes one CSV/XML per month (exrates-monthly-MMYY.csv), so the swap is a
# urllib GET of next month's file plus a csv.DictReader into {code: rate}.
UPSTREAM = "https://www.gov.uk/government/collections/exchange-rates-for-customs-and-vat"

if __name__ == "__main__":
    raise SystemExit(lib.main("fx", UPSTREAM))
