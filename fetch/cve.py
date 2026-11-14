#!/usr/bin/env python3
"""CISA KEV membership, NVD CVSS and dated FIRST EPSS; ADR-0035.

The default clock reads primary sources. FEEDS_SOURCE_DIR supplies a raw corpus
for offline replay. A missing NVD/EPSS record refuses rather than inventing a rate.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

KEV_URL = 'https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'
NVD_URL = 'https://services.nvd.nist.gov/rest/json/cves/2.0?hasKev&resultsPerPage=2000'
EPSS_URL = 'https://epss.cyentia.com/epss_scores-current.csv.gz'
UPSTREAM = KEV_URL + ' + ' + NVD_URL + ' + ' + EPSS_URL


def fetch(url):
    headers = {'User-Agent': 'policy-as-versioned-feeds/ADR-0035'}
    if os.environ.get('NVD_API_KEY') and url.startswith(NVD_URL):
        headers['apiKey'] = os.environ['NVD_API_KEY']
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503) or attempt == 3:
                raise
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError('source could not be read: ' + url)


def source():
    kev_bytes, epss_bytes = fetch(KEV_URL), fetch(EPSS_URL)
    kev = json.loads(kev_bytes)
    text = gzip.decompress(epss_bytes).decode()
    date = re.search(r'score_date:([0-9-]+)', text.splitlines()[0])
    if date is None:
        raise ValueError('FIRST EPSS file names no score_date')
    epss = {row['cve']: float(row['epss']) for row in csv.DictReader(io.StringIO('\n'.join(
        line for line in text.splitlines() if not line.startswith('#'))))}
    rows, page_hashes, start = [], [], 0
    while True:
        raw = fetch(NVD_URL + '&startIndex=' + str(start))
        page = json.loads(raw)
        batch = page.get('vulnerabilities', [])
        if not batch and start < int(page['totalResults']):
            raise ValueError('NVD returned an empty page before totalResults')
        rows.extend(batch)
        page_hashes.append({'startIndex': start, 'sha256': hashlib.sha256(raw).hexdigest()})
        start += len(batch)
        if start >= int(page['totalResults']):
            break
        time.sleep(0.6 if os.environ.get('NVD_API_KEY') else 6)
    return {'kev': kev, 'nvd': rows, 'epss': epss, 'epss_date': date.group(1),
            'provenance': {'kev': {'url': KEV_URL, 'sha256': hashlib.sha256(kev_bytes).hexdigest()},
                           'nvd': {'url': NVD_URL, 'pages': page_hashes},
                           'epss': {'url': EPSS_URL, 'sha256': hashlib.sha256(epss_bytes).hexdigest()}}}


def build(published, upstream):
    nvd = {row['cve']['id']: row['cve'] for row in upstream['nvd']}
    epss = upstream['epss']
    entries = {}
    for kev in upstream['kev']['vulnerabilities']:
        cid = kev['cveID']
        if cid in entries:
            raise ValueError('CISA KEV repeats ' + cid)
        if cid not in nvd or cid not in epss:
            raise ValueError('missing NVD or dated EPSS instrument for KEV ' + cid)
        cve = nvd[cid]
        metrics = cve.get('metrics', {})
        candidates = next((metrics[key] for key in ('cvssMetricV40', 'cvssMetricV31', 'cvssMetricV30', 'cvssMetricV2')
                           if metrics.get(key)), None)
        if not candidates:
            raise ValueError('NVD supplies no CVSS instrument for KEV ' + cid)
        metric = next((item for item in candidates if item.get('type') == 'Primary'), candidates[0])
        cvss = float(metric['cvssData']['baseScore'])
        severity = str(metric['cvssData'].get('baseSeverity') or metric.get('baseSeverity') or
                       ('CRITICAL' if cvss >= 9 else 'HIGH' if cvss >= 7 else 'MEDIUM' if cvss >= 4 else 'LOW')).lower()
        if severity not in ('critical', 'high', 'medium', 'low') or not 0 <= float(epss[cid]) <= 1:
            raise ValueError('invalid NVD severity or EPSS probability for ' + cid)
        entries[cid] = {'component': kev['vendorProject'] + '/' + kev['product'],
                        'cvss': cvss, 'severity': severity, 'epss': float(epss[cid]),
                        'published': cve['published'][:10],
                        'source': 'CISA KEV; NVD ' + cid + '; FIRST EPSS ' + upstream['epss_date']}
    out = dict(published)
    out.update(cves=dict(sorted(entries.items())), feed_version='kev',
               changelog='CISA KEV membership and NVD CVSS severity with FIRST EPSS dated ' + upstream['epss_date'] +
                         '; primary-source corpus with original response hashes in provenance.',
               note='CISA KEV-scoped feed; NVD severity; dated FIRST EPSS ' + upstream['epss_date'] +
                    '. One headline in each adopter inventory intersection. Source provenance: ' +
                    json.dumps(upstream.get('provenance', {}), sort_keys=True))
    return out


def reading(payload):
    return {'epss': {cid: row['epss'] for cid, row in sorted(payload['cves'].items())},
            'provenance': payload['note']}


def selfcheck():
    raw = {'kev': {'vulnerabilities': [{'cveID': 'CVE-2021-44228', 'vendorProject': 'Apache', 'product': 'Log4j'}]},
           'nvd': [{'cve': {'id': 'CVE-2021-44228', 'published': '2021-12-10T10:15:09',
                            'metrics': {'cvssMetricV31': [{'type': 'Primary', 'cvssData': {'baseScore': 10, 'baseSeverity': 'CRITICAL'}}]}}}],
           'epss': {'CVE-2021-44228': 0.9}, 'epss_date': '2026-09-25'}
    got = build({'severity_lm_gbp': {'critical': [1, 2, 3]},
                 'changelog': 'ILLUSTRATIVE legacy fixture entry'}, raw)
    assert 'ILLUSTRATIVE' not in got['changelog'], 'a primary-source corpus retained a fixture changelog'
    assert list(got['cves']) == ['CVE-2021-44228']
    assert got['cves']['CVE-2021-44228']['severity'] == 'critical'
    for key in ('epss', 'nvd'):
        broken = dict(raw, **{key: {} if key == 'epss' else []})
        try:
            build({}, broken)
        except ValueError:
            pass
        else:
            raise AssertionError('a missing ' + key + ' instrument priced')
    print('PASS: KEV-only CVE builder joins primary instruments and refuses missing records')


if __name__ == '__main__':
    if sys.argv[1:] == ['selfcheck']:
        selfcheck()
    else:
        raise SystemExit(lib.main('cve', UPSTREAM, build=build, reading=reading, source=source))
