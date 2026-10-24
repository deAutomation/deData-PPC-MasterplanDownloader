#!/usr/bin/env python3
# coding: utf-8
#
# Render charts from the LATEST snapshot in _outputfiles/json into charts/.
# Run after every snapshot so the README always shows live/latest data:
#
#   python3 ppc_downloader.py && python3 render_charts.py
#
# Outputs (committed to git, embedded in README.md):
#   charts/overview_status_bars.png  — all estates stacked by status code
#   charts/overview_map.png          — estate rings + centroids
#   charts/estates/{slug}.png        — one card per estate: ring map (if any)
#                                      + status breakdown + listed count

import glob
import json
import os
from collections import Counter
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'charts')
EST_DIR = os.path.join(OUT, 'estates')

CODE_LABEL = {'1': '1 ?', '2': '2 avail', '3': '3 ?', '4': '4 future',
              '5': '5 ?', '7': '7 sold', '8': '8 ?'}
CODE_COL = {'1': '#bdbdbd', '2': '#2ca02c', '3': '#9467bd', '4': '#1f77b4',
            '5': '#ff7f0e', '7': '#d62728', '8': '#7f7f7f'}


def latest_run():
    files = sorted(glob.glob(os.path.join(HERE, '_outputfiles', 'json', '*.json')))
    if not files:
        raise SystemExit('no snapshots in _outputfiles/json — run ppc_downloader.py first')
    by_ts = {}
    for f in files:
        by_ts.setdefault(os.path.basename(f)[:19], []).append(f)
    # fullest run wins (a TESTING re-run must not shadow the weekly snapshot)
    ts = max(by_ts, key=lambda t: (len(by_ts[t]), t))
    return ts, by_ts[ts]


def load_estates(run):
    estates = {}
    for f in run:
        d = json.load(open(f))
        slug = d['community']
        cfg = d.get('lotConfig', {})
        lots = cfg.get('all_lots_with_status', [])
        ring = (d.get('mapConfig', {}) or {}).get('mapCoordinates') or []
        estates[slug] = {'url': d.get('url', ''), 'lots': lots,
                         'listed': cfg.get('lots_data', []), 'ring': ring}
    return estates


def overview_bars(estates, date):
    rows = sorted(estates.items(), key=lambda kv: -len(kv[1]['lots']))
    codes = ['1', '2', '3', '4', '5', '7', '8']
    fig, ax = plt.subplots(figsize=(11, max(6, len(rows) * 0.38)))
    y = range(len(rows))
    import numpy as np
    left = np.zeros(len(rows))
    for k in codes:
        v = np.array([sum(1 for l in e['lots'] if str(l.get('lot_status')) == k) for _, e in rows])
        ax.barh(list(y), v, left=left, color=CODE_COL[k], label=CODE_LABEL[k],
                edgecolor='white', linewidth=0.3)
        left += v
    ax.set_yticks(list(y))
    ax.set_yticklabels([s for s, _ in rows], fontsize=8)
    ax.set_xlabel('Lots')
    ax.legend(fontsize=8, loc='lower right', ncol=4)
    total = sum(len(e['lots']) for _, e in estates.items())
    ax.set_title(f'Peet — all estates by lot-status code ({total:,} lots, {date})',
                 fontsize=12, weight='bold')
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'overview_status_bars.png'), bbox_inches='tight')
    plt.close(fig)


def overview_map(estates, date):
    fig, ax = plt.subplots(figsize=(9, 7))
    n_ring = n_pt = 0
    allx, ally = [], []
    for slug, e in estates.items():
        pts = [l for l in e['lots']]
        if e['ring']:
            xs = [pt[1] for pt in e['ring']]
            ys = [pt[0] for pt in e['ring']]
            ax.add_patch(MplPoly(list(zip(xs, ys)), closed=True, facecolor='#1f77b4',
                                 edgecolor='#333', alpha=0.55, linewidth=0.8))
            allx += xs
            ally += ys
            n_ring += 1
        else:
            n_pt += 1
    if allx:
        ax.set_xlim(min(allx) - 0.05, max(allx) + 0.05)
        ax.set_ylim(min(ally) - 0.05, max(ally) + 0.05)
    ax.set_title(f'Peet — estate boundaries ({n_ring} rings, {date})', fontsize=11, weight='bold')
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    ax.grid(alpha=0.25)
    ax.set_aspect('equal', adjustable='box')
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, 'overview_map.png'), bbox_inches='tight')
    plt.close(fig)


def estate_card(slug, e, date):
    lots = e['lots']
    cnt = Counter(str(l.get('lot_status', '?')) for l in lots)
    listed = len(e['listed'])
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    ax1, ax2 = axes
    if e['ring']:
        xs = [pt[1] for pt in e['ring']]
        ys = [pt[0] for pt in e['ring']]
        ax1.add_patch(MplPoly(list(zip(xs, ys)), closed=True, facecolor='#1f77b4',
                              edgecolor='#333', alpha=0.55))
        ax1.set_xlim(min(xs) - 0.002, max(xs) + 0.002)
        ax1.set_ylim(min(ys) - 0.002, max(ys) + 0.002)
        ax1.set_title('boundary', fontsize=9)
    else:
        ax1.text(0.5, 0.5, 'no boundary ring\npublished', ha='center', va='center', fontsize=9)
    ax1.set_xticks([])
    ax1.set_yticks([])
    ax1.set_aspect('equal', adjustable='box')
    codes = [k for k in ['7', '4', '2', '5', '1', '3', '8'] if cnt.get(k)]
    ax2.bar(codes, [cnt[k] for k in codes],
            color=[CODE_COL.get(k, '#999') for k in codes], edgecolor='white')
    ax2.set_title('status codes', fontsize=9)
    for i, k in enumerate(codes):
        ax2.text(i, cnt[k], str(cnt[k]), ha='center', va='bottom', fontsize=8)
    fig.suptitle(f'{slug} — {len(lots)} lots, {listed} listed ({date})',
                 fontsize=12, weight='bold')
    fig.tight_layout()
    fig.savefig(os.path.join(EST_DIR, f'{slug}.png'), bbox_inches='tight')
    plt.close(fig)


def main():
    ts, run = latest_run()
    date = ts[:10]
    print(f'latest run: {ts} ({len(run)} estates)')
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(EST_DIR, exist_ok=True)
    estates = load_estates(run)
    overview_bars(estates, date)
    overview_map(estates, date)
    for slug, e in sorted(estates.items()):
        estate_card(slug, e, date)
    total = sum(len(e['lots']) for e in estates.values())
    listed = sum(len(e['listed']) for e in estates.values())
    manifest = {'run': ts, 'date': date, 'estates': len(estates),
                'lots': total, 'listed': listed,
                'generated': datetime.now().isoformat(timespec='seconds')}
    json.dump(manifest, open(os.path.join(OUT, 'latest.json'), 'w'), indent=1)
    print(f'estates={len(estates)} lots={total} listed={listed} -> charts/')
    write_readme_table(estates, date)


def write_readme_table(estates, date):
    """Regenerate the per-estate table in README.md between markers."""
    rows = []
    for slug in sorted(estates, key=lambda s: -len(estates[s]['lots'])):
        e = estates[slug]
        n = len(e['lots'])
        cnt = Counter(str(l.get('lot_status', '?')) for l in e['lots'])
        sold = cnt.get('7', 0)
        pct = f'{100 * sold / n:.0f}%' if n else '—'
        rows.append(f'| [{slug}](function-PPC-masterplan-dl/charts/estates/{slug}.png) '
                    f'| {n} | {len(e["listed"])} | {sold} ({pct}) '
                    f'| 2:{cnt.get("2", 0)} 4:{cnt.get("4", 0)} 5:{cnt.get("5", 0)} '
                    f'1:{cnt.get("1", 0)} |')
    table = ('| Estate (click for card) | Lots | Listed | Sold 7 | Avail 2 · Fut 4 · Other |\n'
             '|---|---|---|---|---|\n' + '\n'.join(rows) + f'\n\n*Snapshot {date}. Codes: 7 sold · 2 available · 4 future · 1/5/3/8 mid-states.*\n')
    rp = os.path.join(HERE, '..', 'README.md')
    if not os.path.exists(rp):
        print('README not found, skipping table embed')
        return
    md = open(rp).read()
    start, end = '<!-- ESTATE_TABLE:START -->', '<!-- ESTATE_TABLE:END -->'
    if start not in md or end not in md:
        print('markers missing in README, skipping table embed')
        return
    pre, rest = md.split(start, 1)
    _, post = rest.split(end, 1)
    open(rp, 'w').write(pre + start + '\n' + table + end + post)
    print(f'README table updated ({len(rows)} estates)')


if __name__ == '__main__':
    main()
