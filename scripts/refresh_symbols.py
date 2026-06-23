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
NIFTY200_CSV_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv"
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "static", "symbols.json")
NIFTY200_OUT = os.path.join(os.path.dirname(__file__), "..", "app", "data", "nifty200.json")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/csv,*/*",
}


def _download_csv(url: str = NSE_CSV_URL) -> str:
    import requests  # local import so the script is usable with --csv offline
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def _parse_nifty200(csv_text: str) -> list[dict]:
    rows = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        clean = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        if clean.get("Series") == "EQ" and clean.get("Symbol"):
            rows.append({"symbol": clean["Symbol"], "name": clean.get("Company Name", "")})
    rows.sort(key=lambda r: r["symbol"])
    return rows


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

    # Also refresh the Nifty 200 list used by the Top Movers panel.
    if not args.csv:
        try:
            n200 = _parse_nifty200(_download_csv(NIFTY200_CSV_URL))
            n200_out = os.path.abspath(NIFTY200_OUT)
            os.makedirs(os.path.dirname(n200_out), exist_ok=True)
            with open(n200_out, "w", encoding="utf-8") as f:
                json.dump(n200, f, ensure_ascii=False, separators=(",", ":"))
            print(f"Wrote {len(n200)} Nifty 200 symbols → {n200_out}")
        except Exception as e:
            print(f"Skipped Nifty 200 refresh: {e}")


if __name__ == "__main__":
    main()
