#!/usr/bin/env python3
# coding: utf-8
#
# PPC Community Discovery v2 — auto-discovery from every source the site leaks.
# Sources (union, then validated):
#   1. /communities/ index page (marketing list)
#   2. robots.txt sitemap_index entries (catches microsites the index omits,
#      e.g. the-landing-strathpine, hummingbird-rise)
# Validation: URL must return 200 AND embed `var lotConfig` (else flagged, not tracked).
# New/gone/changed vs last snapshot. --notify raises a Todoist task on news
# (needs TODOIST_TOKEN + TODOIST_PROJECT_ID env; falls back to
# ~/.hermes/todoist_token locally; silently skips in Cloud Run).
#
#   python3 discover_communities.py [--notify]

import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
SNAP = os.path.join(HERE, '_outputfiles', 'discovery_snapshot.json')
BASE = 'https://www.peet.com.au'
# Spring Mountain's page serves a leaked aggregate feed (606 lots from OTHER
# estates: Forestville, Yanchep, Tonsley...). Tracking it as an estate would
# double-count, so it is excluded from auto-discovery.
EXCLUDE = {'communities/queensland/spring-mountain'}
TODOIST_TOKEN = (os.environ.get('TODOIST_TOKEN') or
                 (open(os.path.expanduser('~/.hermes/todoist_token')).read().strip()
                  if os.path.exists(os.path.expanduser('~/.hermes/todoist_token')) else ''))
TODOIST_PROJECT = os.environ.get('TODOIST_PROJECT_ID', '')  # no default: notifications stay off unless configured


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


def from_index():
    h = get(BASE + '/communities/')
    return sorted(set(p.strip('/') for p in
                      re.findall(r'/communities/[a-z\-]+/[a-z\-]+/?', h)) - EXCLUDE)


def from_robots():
    h = get(BASE + '/robots.txt')
    out = set()
    for m in re.findall(r'peet\.com\.au(/communities/[a-z\-]+/[a-z\-]+)/sitemap_index\.xml', h):
        out.add(m.strip('/'))
    return sorted(out - EXCLUDE)


def validate(path):
    """(ok, reason, n_lots). Fetch page, require lotConfig with lots."""
    try:
        h = get(BASE + '/' + path)
    except Exception as e:
        return False, f'http fail {e}', 0
    if 'var lotConfig' not in h:
        return False, 'no lotConfig', 0
    i = h.find('var lotConfig = ')
    try:
        dec = json.JSONDecoder()
        d, _ = dec.raw_decode(h[h.find('=', i) + 1:].lstrip())
        n = len((d.get('all_lots_with_status', [])))
        return (True, f'{n} lots', n) if n else (False, 'empty lots', 0)
    except Exception as e:
        return False, f'parse fail {e}', 0


def notify_todoist(text):
    import urllib.parse
    if not TODOIST_TOKEN or not TODOIST_PROJECT:
        print('  notify skipped (TODOIST_TOKEN / TODOIST_PROJECT_ID not set)')
        return {}
    data = urllib.parse.urlencode(
        {'content': text, 'project_id': TODOIST_PROJECT}).encode()
    req = urllib.request.Request(
        'https://api.todoist.com/api/v1/tasks', data=data,
        headers={'Authorization': f'Bearer {TODOIST_TOKEN}',
                 'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    notify = '--notify' in sys.argv
    idx, rob = from_index(), from_robots()
    cands = sorted(set(idx) | set(rob))
    print(f'index={len(idx)} robots={len(rob)} union={len(cands)}')
    prev = json.load(open(SNAP)) if os.path.exists(SNAP) else {}
    prev_paths = set(prev.get('tracked', []))
    results, news = {}, []
    for p in cands:
        ok, reason, n = validate(p)
        results[p] = {'ok': ok, 'note': reason, 'lots': n}
        flag = 'OK ' if ok else 'SKIP'
        print(f'  [{flag}] {p} — {reason}')
        if p not in prev_paths and ok:
            news.append(f'NEW community: {p} ({n} lots)')
    gone = sorted(prev_paths - set(cands))
    for p in gone:
        news.append(f'GONE from index/sitemaps: {p} (was {prev.get("lots", {}).get(p, "?")} lots)')
    if news:
        print('NEWS:')
        for n in news:
            print('  !', n)
        if notify:
            t = notify_todoist('Peet tracker: ' + '; '.join(news) +
                               ' (auto-discovery)')
            if t.get('id'):
                print('  todoist task:', t.get('id'))
    else:
        print('no changes since last snapshot')
    os.makedirs(os.path.dirname(SNAP), exist_ok=True)
    json.dump({'tracked': sorted(p for p, r in results.items() if r['ok']),
               'lots': {p: r['lots'] for p, r in results.items() if r['ok']},
               'skipped': {p: r['note'] for p, r in results.items() if not r['ok']}},
              open(SNAP, 'w'), indent=1)


def tracked_paths():
    if os.path.exists(SNAP):
        return json.load(open(SNAP)).get('tracked', [])
    return []


if __name__ == '__main__':
    main()
