#!/usr/bin/env python3
"""Scheduled fetch for the EOL feed. See fetch/lib.py."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

# ponytail: read via lib.read_upstream() from the committed fixture. Upgrade
# path: https://endoflife.date/api/<product>.json per tracked component.
UPSTREAM = "https://endoflife.date/api/"

if __name__ == "__main__":
    raise SystemExit(lib.main("eol", UPSTREAM))
