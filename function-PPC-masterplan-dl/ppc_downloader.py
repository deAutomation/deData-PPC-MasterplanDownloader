#!/usr/bin/env python3
# coding: utf-8
#
# deAutomation deData - PPC (Peet) Data Downloader - Google Cloud Run Job
# Mirrors function-SGP-masterplan-dl/sgp_downloader.py.
#
# Source: Peet community pages (WordPress, public). Each page embeds
#   var lotConfig = {"lots_data":[...14ish live...],
#                    "all_lots_with_status":[...every lot + status code...],
#                    "mapConfig": {"mapCoordinates":[...]}}  (boundary ring, when present)
# No token, no auth. Plain GET + parse.
#
# Outputs (per community, per run):
#   JSON: full lotConfig snapshot (status array + live list + ring)
#   CSV : one flattened row per lot in all_lots_with_status, left-joined to
#         lots_data on lot_id for price/frontage/size (publish list only).
#
# GCS layout mirrors SGP:
#   ppc/masterplans/json/{ts}-ppc-website-masterplan-data-{slug}.json
#   ppc/masterplans/csv/{ts}-ppc-website-masterplan-data-{slug}.csv
# Local mode (default): writes ./_outputfiles/json|csv instead of GCS.
#   LOCAL=0 (or --upload) pushes to GCS. TESTING=1 limits to 2 communities.

import csv
import gzip
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from random import shuffle
from time import sleep

try:
    from zoneinfo import ZoneInfo
    ADL = ZoneInfo('Australia/Adelaide')
except Exception:
    ADL = None


class PPCDownloader:
    BUCKET_NAME = 'masterplans'
    BASE = 'https://www.peet.com.au'
    INDEX = BASE + '/communities/'
    UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'}
    TESTING = os.environ.get('TESTING', '') == '1'
    LOCAL = not (os.environ.get('LOCAL') in ('0', 'false', 'no') or '--upload' in sys.argv)

    def __init__(self):
        self.communities = self.discover()
        shuffle(self.communities)
        if self.TESTING:
            self.communities = self.communities[:2]
        print(f'PPC communities: {len(self.communities)}')

    def get(self, url, timeout=30):
        req = urllib.request.Request(url, headers=self.UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='replace')

    def discover(self):
        """Community paths: /communities/ index UNION robots.txt sitemaps.
        (robots catches microsites the index omits.) Failures per community
        are handled at fetch time; use discover_communities.py --notify
        for validated new/gone alerts."""
        try:
            from discover_communities import from_index, from_robots, EXCLUDE
            paths = sorted((set(from_index()) | set(from_robots())) - set(EXCLUDE))
        except Exception:
            h = self.get(self.INDEX)
            paths = sorted(set(p.strip('/') for p in
                               re.findall(r'/communities/[a-z\-]+/[a-z\-]+/?', h)))
        return [{'company': 'ppc', 'slug': p.split('/')[-1], 'url': self.BASE + '/' + p}
                for p in paths]

    @staticmethod
    def extract_lotconfig(html):
        out = {}
        i = html.find('var lotConfig = ')
        if i >= 0:
            j = html.find('=', i) + 1
            dec = json.JSONDecoder()
            out['lotConfig'], _ = dec.raw_decode(html[j:].lstrip())
        m = re.search(r'var mapConfig = (\{.*?\});', html, re.S)
        if m:
            try:
                out['mapConfig'] = json.loads(m.group(1))
            except Exception:
                pass
        return out or None

    def fetch_community(self, community):
        html = self.get(community['url'])
        cfg = self.extract_lotconfig(html)
        if cfg is None:
            raise ValueError('no lotConfig on page')
        return cfg

    @staticmethod
    def to_json(community, cfg):
        return json.dumps({'community': community['slug'], 'url': community['url'],
                           'company': community['company'], 'lotConfig': cfg.get('lotConfig', {}),
                           'mapConfig': cfg.get('mapConfig', {})}, indent=1)

    @staticmethod
    def to_csv(community, cfg, date_str):
        lots_cfg = cfg.get('lotConfig', {})
        live = {str(x.get('lot_id')): x for x in lots_cfg.get('lots_data', [])}
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(['date', 'company', 'community', 'lot_id', 'lot_number', 'lot_name',
                    'stage_name', 'lot_status', 'lot_post_status', 'price', 'frontage',
                    'size', 'product_type', 'bedrooms', 'bathrooms', 'garage_spaces'])
        for lot in lots_cfg.get('all_lots_with_status', []):
            lid = str(lot.get('lot_id', ''))
            lv = live.get(lid, {})
            w.writerow([date_str, community['company'], community['slug'], lid,
                        lot.get('lot_number', ''), lot.get('lot_name', ''),
                        lot.get('stage_name', ''), lot.get('lot_status', ''),
                        lot.get('lot_post_status', ''), lv.get('price', ''),
                        lv.get('frontage', ''), lv.get('size', ''),
                        lv.get('product_type', ''), lv.get('bedrooms', ''),
                        lv.get('bathrooms', ''), lv.get('garage_spaces', '')])
        return out.getvalue()

    def upload_to_bucket(self, blob_name, content):
        from google.cloud import storage
        raw = content.encode('utf-8')
        blob_name = blob_name if blob_name.endswith('.gz') else blob_name + '.gz'
        client = storage.Client()
        bucket = client.bucket(self.BUCKET_NAME)
        blob = bucket.blob(blob_name)
        blob.content_encoding = 'gzip'
        blob.upload_from_string(gzip.compress(raw),
                                content_type='application/json' if '.json' in blob_name else 'text/csv')
        print(f'Uploaded {blob_name} ({len(raw)} -> {len(gzip.compress(raw))} bytes).')

    def run(self):
        now = datetime.now(ADL) if ADL else datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        ts = now.strftime('%Y-%m-%d_%H-%M-%S')
        ok, failed = 0, []
        for i, c in enumerate(self.communities):
            print(f"[{i + 1}/{len(self.communities)}] {c['slug']} ...")
            try:
                cfg = self.fetch_community(c)
                lots_cfg = cfg.get('lotConfig', {})
                n_all = len(lots_cfg.get('all_lots_with_status', []))
                n_live = len(lots_cfg.get('lots_data', []))
                print(f'  lots={n_all} listed={n_live}')
                base = f'{ts}-ppc-website-masterplan-data-{c["slug"]}'
                if self.LOCAL:
                    os.makedirs('_outputfiles/json', exist_ok=True)
                    os.makedirs('_outputfiles/csv', exist_ok=True)
                    open(f'_outputfiles/json/{base}.json', 'w').write(self.to_json(c, cfg))
                    open(f'_outputfiles/csv/{base}.csv', 'w').write(self.to_csv(c, cfg, date_str))
                else:
                    self.upload_to_bucket(f'ppc/masterplans/json/{base}.json', self.to_json(c, cfg))
                    self.upload_to_bucket(f'ppc/masterplans/csv/{base}.csv', self.to_csv(c, cfg, date_str))
                ok += 1
                sleep(1)
            except Exception as e:
                print(f'  FAIL: {e}')
                failed.append(c['slug'])
        print(f'done: {ok} ok, {len(failed)} failed {failed}')
        return ok, failed


def download_data():
    return PPCDownloader().run()


if __name__ == '__main__':
    download_data()
