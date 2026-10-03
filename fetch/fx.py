#!/usr/bin/env python3
"""Read authentic HMRC monthly rates in units per GBP (ticket144).

The clock reads the current UTC month. FEEDS_FX_PERIOD selects a reviewed
historical month; FEEDS_SOURCE_DIR still supplies offline replay corpora.
"""
from __future__ import annotations
import csv
import datetime as dt
import hashlib
import io
import json
import math
import os
import re
import sys
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

UPSTREAM = 'https://www.trade-tariff.service.gov.uk/api/v2/exchange_rates/files/monthly_csv_{year}-{month}.csv'

def parse(raw: bytes, period: str, url: str) -> dict:
    if not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', period):
        raise ValueError('FX source names no YYYY-MM period')
    rates = {}
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    if not rows:
        raise ValueError('HMRC rate table is empty')
    for row in rows:
        code = row['Currency Code'].strip()
        rate = float(row['Currency Units per £1'].replace(',', ''))
        start = dt.datetime.strptime(row['Start date'], '%d/%m/%Y').date()
        end = dt.datetime.strptime(row['End date'], '%d/%m/%Y').date()
        if start.strftime('%Y-%m') != period or end.strftime('%Y-%m') != period:
            raise ValueError('HMRC table dates do not match requested month')
        if not re.fullmatch(r'[A-Z]{3}', code) or not math.isfinite(rate) or rate <= 0:
            raise ValueError('invalid HMRC currency or rate: ' + code)
        if code in rates and rates[code] != rate:
            raise ValueError('HMRC publishes conflicting country rates for ' + code)
        if code != 'GBP':
            rates[code] = rate
    return {'source': 'HMRC monthly exchange rates', 'period': period, 'base': 'GBP',
            'rates': dict(sorted(rates.items())),
            'note': 'Authentic HMRC monthly CSV, units of foreign currency per GBP1; valid ' + period + '. Source: ' + url + '. Raw SHA256: ' + hashlib.sha256(raw).hexdigest() + '. Filing dates and conversion month are separate recorded facts.'}

def source() -> dict:
    period = os.environ.get('FEEDS_FX_PERIOD') or dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')
    if not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', period):
        raise ValueError('FEEDS_FX_PERIOD must be YYYY-MM')
    year, month = period.split('-'); url = UPSTREAM.format(year=year, month=int(month))
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'policy-as-versioned-feeds/HMRC'}), timeout=30) as response:
        return parse(response.read(), period, url)

if __name__ == '__main__':
    raise SystemExit(lib.main('fx', UPSTREAM, source=source))
