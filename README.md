# deData-PPC-MasterplanDownloader (Peet Limited)

Weekly snapshotter for Peet community inventory — the same machine as SGP/CWP/LIC,
pointed at Peet's public `lotConfig` feed. No token, no auth, plain GET + parse.

## Why this exists
Peet publishes per-lot inventory on every community page: which lots exist, their
status codes, and the currently listed subset with price/frontage/size. Diffing
weekly snapshots yields net-sales velocity per estate — the same alternative-data
product as the SGP tracker, for a $992.5M Ingenia takeover target where settlement
momentum is genuinely price-relevant.

## Source
Each community page embeds:
```js
var lotConfig = {"lots_data":[...], "all_lots_with_status":[...], "mapConfig":{...}}
```
- `lots_data` — currently listed lots (lot_id, lot_name, stage, price, frontage, size, product_type)
- `all_lots_with_status` — every lot: lot_id, lot_number, lot_name, stage_name, `lot_status`, `lot_post_status` (`publish` = listed)
- `mapConfig.mapCoordinates` — estate boundary ring (when present)

Status codes, decoded behaviorally (firm up over 2–3 snapshots):
| code | meaning | evidence |
|---|---|---|
| 7 | sold / settled | sold-out estates read ~100% 7, zero published |
| 2 | available | every published lot is a 2 |
| 4 | future stages | clusters on newest stage names |
| 1 / 5 / 3 / 8 | mid-states (deposits, holds, staged releases) | watch transitions 4→2→7 |

## Discovery — no hardcoded IDs
Community paths are scraped live from `https://www.peet.com.au/communities/` on every
run, so new estates enter automatically. `discover_communities.py` diffs the live
index against the last snapshot and reports new/gone estates (no GCS, safe anywhere).

## Run it (local first)
```bash
cd function-PPC-masterplan-dl
TESTING=1 python3 ppc_downloader.py   # 2 communities → ./_outputfiles
python3 ppc_downloader.py             # all ~33 communities → ./_outputfiles
python3 discover_communities.py       # index diff only
```
Filenames mirror SGP: `{ts}-ppc-website-masterplan-data-{slug}.json|.csv`.

CSV columns: date, company, community, lot_id, lot_number, lot_name, stage_name,
lot_status, lot_post_status, price, frontage, size, product_type, bedrooms,
bathrooms, garage_spaces (price/spec columns join from `lots_data` on lot_id;
empty unless the lot is currently listed).

## GCS (Cloud Run Job path)
`LOCAL=0 python3 ppc_downloader.py` writes to `ppc/masterplans/{json,csv}/`
(bucket `masterplans`) instead of disk. Needs ADC or a service-account key —
same IAM as the SGP job (storage.objectViewer + datastore.user on the target project).

## Deploy
Cloud Run Job via `cloudbuild.yaml` (`ppc-masterplan-job`, 600s timeout for ~33 pages).
**CI/CD only — never deploy by hand.** Push to main; pipelines carry it.
Weekly schedule runs the job; downstream ETL/analysis consume `ppc/masterplans/`.
