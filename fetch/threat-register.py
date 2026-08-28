#!/usr/bin/env python3
"""Scheduled fetch for the institution threat register. See fetch/lib.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

# ponytail: read via lib.read_upstream() from the committed fixture. Upgrade
# path: the Verizon DBIR sector breach-frequency tables this register is
# editorialised from, refreshed on publication.
UPSTREAM = "https://www.verizon.com/business/resources/reports/dbir/ (sector base rates)"

if __name__ == "__main__":
    raise SystemExit(lib.main("threat-register", UPSTREAM))
