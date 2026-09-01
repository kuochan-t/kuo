"""Pull the 計費報表 export for one month, straight from the API.

Needs outbound access to auth.authme.com and api.authme.com. As of 2026-09-01
this environment's network policy denies both (403 at the egress gateway), so
this script is here ready for when that policy is opened.

Credentials are per-tenant Client/Secret pairs, kept OUT of this repo — they
live in the Notion 每月1日SaaS報表 page. Supply them at run time:

    export AUTHME_JUJI_CLIENT_ID=...     AUTHME_JUJI_CLIENT_SECRET=...
    export AUTHME_AFTEE_CLIENT_ID=...    AUTHME_AFTEE_CLIENT_SECRET=...
    python fetch/fetch_billing.py --month 202608 --out data/202608

or put them in an untracked creds.json: {"juji": {"client_id": ..., "secret": ...}}

    python fetch/fetch_billing.py --month 202608 --out data/202608 --creds creds.json

NOTE: the token endpoint below is the ABP/OpenIddict default and has NOT been
verified against the real ekyc_reports.sh (gist.githubusercontent.com is also
blocked here). If the token request 404s or returns invalid_client, check the
gist for the actual path and fix TOKEN_PATH.
"""

import argparse
import calendar
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from saas_billing.config import CLIENTS  # noqa: E402

AUTH_HOST = "https://auth.authme.com"
API_HOST = "https://api.authme.com"
TOKEN_PATH = "/connect/token"          # unverified — see module docstring
EXPORT_PATH = "/api/identity-verification/v1/reports/billing/export"
PAGE_SIZE = 10000


def month_range(month):
    year, mon = int(month[:4]), int(month[4:])
    last = calendar.monthrange(year, mon)[1]
    return f"{year:04d}-{mon:02d}-01", f"{year:04d}-{mon:02d}-{last:02d}"


def post(url, data, headers=None):
    body = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(url, data=body, headers=headers or {})
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def get(url, token):
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def get_token(client_id, client_secret):
    payload = post(AUTH_HOST + TOKEN_PATH, {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"token 回應裡沒有 access_token: {payload}")
    return token


def fetch_items(token, tenant_id, start, end):
    """Page through the export so a busy month is not silently truncated."""
    items = []
    while True:
        query = urllib.parse.urlencode({
            "startTime": start, "endTime": end, "tenantId": tenant_id,
            "skipCount": len(items), "maxResultCount": PAGE_SIZE,
        })
        payload = get(f"{API_HOST}{EXPORT_PATH}?{query}", token)
        page = payload.get("items") or payload.get("result", {}).get("items") or []
        items.extend(page)
        if len(page) < PAGE_SIZE:
            return items


def load_credentials(path):
    if path:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    creds = {}
    for key in CLIENTS:
        env = key.upper()
        client_id = os.environ.get(f"AUTHME_{env}_CLIENT_ID")
        secret = os.environ.get(f"AUTHME_{env}_CLIENT_SECRET")
        if client_id and secret:
            creds[key] = {"client_id": client_id, "secret": secret}
    return creds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="如 202608")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--creds", help="untracked JSON with per-client credentials")
    parser.add_argument("--only", nargs="*", help="只抓這幾個客戶")
    args = parser.parse_args()

    start, end = month_range(args.month)
    creds = load_credentials(args.creds)
    if not creds:
        parser.error("沒有任何憑證 —— 請設環境變數或用 --creds")

    args.out.mkdir(parents=True, exist_ok=True)
    failures = []
    for key, client in CLIENTS.items():
        if args.only and key not in args.only:
            continue
        if key not in creds:
            continue
        tenant_id = client.get("tenant_id")
        if not tenant_id:
            failures.append(f"{key}: config 裡沒有 tenant_id")
            continue
        try:
            token = get_token(creds[key]["client_id"], creds[key]["secret"])
            items = fetch_items(token, tenant_id, start, end)
        except Exception as exc:                     # noqa: BLE001 — report, don't mask
            failures.append(f"{key}: {exc}")
            continue
        target = args.out / f"{key}.json"
        target.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {client['label']:<22}{len(items):>8,} 筆  -> {target}")

    for failure in failures:
        print(f"  ✗ {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
