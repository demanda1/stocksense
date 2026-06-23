"""Top gainers / losers across the Nifty 200 — a proxy for what people are
buying (rising) vs selling (falling).

This is NOT real broker order-flow data (that needs a paid exchange/broker
feed). It's based on % price change, which is the standard free proxy for
buy/sell pressure. Labelled honestly in the UI.

To stay within Yahoo's rate limits we fetch ALL symbols in a SINGLE batched
yf.download() call (not per-ticker), and cache the computed result.
"""
from __future__ import annotations

import json
import os
import time

import pandas as pd
import yfinance as yf

_DATA = os.path.join(os.path.dirname(__file__), "..", "data", "nifty200.json")
_CACHE: dict | None = None
_CACHE_TS = 0.0
_TTL = 300  # seconds (5 minutes)


def _load_universe() -> list[dict]:
    try:
        with open(_DATA, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _compute() -> dict:
    """Batch-download the universe and compute % change from the last 2 closes."""
    universe = _load_universe()
    if not universe:
        return {"gainers": [], "losers": [], "as_of": None, "universe": 0}

    name_by_sym = {u["symbol"]: u["name"] for u in universe}
    sector_by_sym = {u["symbol"]: u.get("sector", "") for u in universe}
    symbols = [u["symbol"] for u in universe]

    # Download in chunks — Yahoo throttles one giant 200-symbol request, but
    # tolerates several smaller batches well.
    CHUNK = 40
    movers = []
    for i in range(0, len(symbols), CHUNK):
        batch = symbols[i:i + CHUNK]
        yf_batch = [f"{s}.NS" for s in batch]
        try:
            df = yf.download(yf_batch, period="5d", interval="1d",
                             group_by="ticker", progress=False, threads=True)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for sym in batch:
            col = f"{sym}.NS"
            try:
                closes = df[col]["Close"].dropna()
            except Exception:
                continue
            if len(closes) < 2:
                continue
            prev, last = float(closes.iloc[-2]), float(closes.iloc[-1])
            if prev <= 0:
                continue
            pct = (last - prev) / prev * 100
            movers.append({
                "symbol": sym,
                "name": name_by_sym.get(sym, sym),
                "sector": sector_by_sym.get(sym, ""),
                "price": round(last, 2),
                "change_pct": round(pct, 2),
            })

    movers.sort(key=lambda m: m["change_pct"], reverse=True)
    gainers = movers[:5]
    losers = sorted(movers[-5:], key=lambda m: m["change_pct"]) if len(movers) >= 5 \
        else [m for m in movers if m["change_pct"] < 0][:5]

    # Per-sector average % change + market (all-200) average.
    sector_sums: dict[str, list[float]] = {}
    for m in movers:
        sector_sums.setdefault(m["sector"], []).append(m["change_pct"])
    sectors = {
        s: round(sum(v) / len(v), 2)
        for s, v in sector_sums.items() if s
    }
    market_avg = round(sum(m["change_pct"] for m in movers) / len(movers), 2) if movers else None

    return {
        "gainers": gainers,
        "losers": losers,
        "as_of": int(time.time()),
        "universe": len(movers),
        "by_symbol": {m["symbol"]: m for m in movers},
        "sectors": sectors,
        "market_avg": market_avg,
    }


def _refresh(force: bool = False) -> dict:
    """Return the full cached computation (incl. by_symbol/sectors), refreshing
    at most every _TTL seconds. Serves stale cache if a fresh fetch fails."""
    global _CACHE, _CACHE_TS
    now = time.time()
    if _CACHE and not force and (now - _CACHE_TS) < _TTL:
        return _CACHE
    try:
        result = _compute()
        if result.get("universe"):     # don't overwrite good data with empty
            _CACHE, _CACHE_TS = result, now
            return result
    except Exception:
        pass
    if _CACHE:
        return _CACHE
    return {"gainers": [], "losers": [], "as_of": None, "universe": 0,
            "by_symbol": {}, "sectors": {}, "market_avg": None}


def get_movers(force: bool = False) -> dict:
    """Lean top gainers / losers for the dashboard panel (no heavy maps)."""
    d = _refresh(force)
    return {"gainers": d.get("gainers", []), "losers": d.get("losers", []),
            "as_of": d.get("as_of"), "universe": d.get("universe", 0)}


def get_sector_context(symbol: str) -> dict:
    """How a stock is doing vs. its sector and vs. the market (Nifty 200 avg)."""
    d = _refresh()
    sym = symbol.upper().replace(".NS", "")
    row = (d.get("by_symbol") or {}).get(sym)
    if not row:
        return {"available": False, "reason": "Stock not in the Nifty 200 universe."}
    sector = row.get("sector") or "—"
    sector_avg = (d.get("sectors") or {}).get(sector)
    market_avg = d.get("market_avg")
    stock_chg = row.get("change_pct")

    def rel(a, b):
        if a is None or b is None:
            return None
        return round(a - b, 2)

    vs_sector = rel(stock_chg, sector_avg)
    vs_market = rel(stock_chg, market_avg)
    # Leading = outperforming both sector and market; lagging = underperforming.
    if vs_sector is not None and vs_market is not None:
        if vs_sector > 0.1 and vs_market > 0.1:
            strength = "leading"
        elif vs_sector < -0.1 and vs_market < -0.1:
            strength = "lagging"
        else:
            strength = "in line"
    else:
        strength = "unknown"

    return {
        "available": True,
        "symbol": sym,
        "sector": sector,
        "stock_change": stock_chg,
        "sector_change": sector_avg,
        "market_change": market_avg,
        "vs_sector": vs_sector,
        "vs_market": vs_market,
        "strength": strength,
        "as_of": d.get("as_of"),
    }
