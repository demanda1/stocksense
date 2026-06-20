#!/usr/bin/env python3
"""Regenerate app/static/symbols.json from NSE's equity list.

The autocomplete on the dashboard reads this bundled file so suggestions are
instant (no per-keystroke API call). The NSE listed-equity set changes rarely,
so run this only occasionally to pick up new listings / delistings.

Usage:
    # Download the latest list from NSE and rebuild symbols.json:
    python scripts/refresh_symbols.py

    # Or build from an already-downloaded CSV:
    python scripts/refresh_symbols.py --csv /path/to/EQUITY_L.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os

NSE_CSV_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "static", "symbols.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/csv,*/*",
}


def _download_csv() -> str:
    import requests  # local import so the script is usable with --csv offline
    r = requests.get(NSE_CSV_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def _parse(csv_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = []
    for row in reader:
        # NSE headers have leading spaces, e.g. " SERIES".
        clean = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        if clean.get("SERIES") != "EQ":      # keep only normal equity series
            continue
        symbol = clean.get("SYMBOL", "")
        name = clean.get("NAME OF COMPANY", "")
        if symbol:
            rows.append({"symbol": symbol, "name": name})
    rows.sort(key=lambda r: r["symbol"])
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="Path to a local EQUITY_L.csv instead of downloading.")
    args = ap.parse_args()

    if args.csv:
        with open(args.csv, encoding="utf-8") as f:
            csv_text = f.read()
    else:
        print(f"Downloading {NSE_CSV_URL} …")
        csv_text = _download_csv()

    rows = _parse(csv_text)
    out = os.path.abspath(OUT_PATH)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {len(rows)} symbols → {out}")


if __name__ == "__main__":
    main()
