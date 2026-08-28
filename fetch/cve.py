#!/usr/bin/env python3
"""Scheduled fetch for the CVE feed. See fetch/lib.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

# ponytail: read via lib.read_upstream() from the committed fixture. Upgrade
# path: `trivy image --format json` over the estate's running images, joined
# to the FIRST EPSS daily CSV.
UPSTREAM = "https://api.first.org/data/v1/epss + trivy image scan"

if __name__ == "__main__":
    raise SystemExit(lib.main("cve", UPSTREAM))
