#!/usr/bin/env python3
# coding: utf-8
#
# PPC Community Discovery — mirrors discover_communities.py (SGP).
# Diffs the live /communities/ index against the last snapshot's slugs.
# No GCS, no uploads. Safe to run anywhere.
#
#   python3 discover_communities.py

import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
SNAP = os.path.join(HERE, '_outputfiles', 'discovery_snapshot.json')


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


def main():
    h = get('https://www.peet.com.au/communities/')
    live = sorted(set(re.findall(r'/communities/[a-z\-]+/[a-z\-]+/?', h)))
    live = [p.strip('/') for p in live]
    prev = json.load(open(SNAP)) if os.path.exists(SNAP) else []
    new = [p for p in live if p not in prev]
    gone = [p for p in prev if p not in live]
    print(f'live: {len(live)}  new: {len(new)} {new}  gone: {len(gone)} {gone}')
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    json.dump(live, open(SNAP, 'w'), indent=1)


if __name__ == '__main__':
    main()
