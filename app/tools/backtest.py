"""Backtest a chart pattern on a stock's own history.

Slides the pattern detector over the maximum available daily history. Each time
the detector fires the SAME pattern type that's showing now, we look forward and
record whether price reached the measured target before the stop-loss. This turns
the projection from pure geometry into a track record (hit-rate + average move).

All educational — past behaviour does not guarantee future results, and small
samples are flagged.
"""
from __future__ import annotations

import time

import pandas as pd
import yfinance as yf

from app.config import to_yf_symbol
from app.tools.patterns import detect_pattern

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 3600  # 1 hour — pattern history barely changes intraday

# How far forward (in bars) to give a pattern to reach its target before we call
# it a miss. Scales with the pattern's own horizon at detection time.
_MAX_FORWARD = 60
_MIN_OCCURRENCES = 5     # below this we warn "low confidence"
_PIVOT_WINDOW = 5


def _outcome(closes, start_idx, signal, target, stop, horizon):
    """Walk forward from start_idx; did target or stop hit first? Return move %."""
    entry = closes[start_idx]
    if entry <= 0 or target is None or stop is None:
        return None
    forward = min(len(closes), start_idx + max(horizon, 10) + _MAX_FORWARD)
    for j in range(start_idx + 1, forward):
        price = closes[j]
        if signal == "bullish":
            if price >= target:
                return {"win": True, "move_pct": (target - entry) / entry * 100}
            if price <= stop:
                return {"win": False, "move_pct": (price - entry) / entry * 100}
        elif signal == "bearish":
            if price <= target:
                return {"win": True, "move_pct": (entry - target) / entry * 100}
            if price >= stop:
                return {"win": False, "move_pct": (entry - price) / entry * 100}
    # Neither hit within the window — score by where it ended up.
    end = closes[forward - 1]
    move = (end - entry) / entry * 100 * (1 if signal == "bullish" else -1)
    return {"win": False, "move_pct": move, "expired": True}


def _run(symbol_no_suffix: str, pattern_name: str) -> dict:
    symbol = to_yf_symbol(symbol_no_suffix)
    df = yf.download(symbol, period="max", interval="1d", progress=False)
    if df is None or df.empty:
        return {"available": False, "reason": "No history available."}
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    closes = [float(x) for x in df["Close"].dropna().tolist()]
    highs = [float(x) for x in df["High"].dropna().tolist()]
    lows = [float(x) for x in df["Low"].dropna().tolist()]
    n = min(len(closes), len(highs), len(lows))
    if n < 120:
        return {"available": False, "reason": "Not enough history to backtest."}

    occurrences, wins, moves = 0, 0, []
    last_entry_idx = -999
    # Slide a detection window; step a few bars. We only count a NEW occurrence
    # once the previous one's trade window has passed, so a single formation
    # (which the detector sees for several consecutive windows) is counted once.
    WIN = 120
    step = 2
    for end in range(WIN, n, step):
        idx = end - 1
        res = detect_pattern(closes[:end], highs[:end], lows[:end], _PIVOT_WINDOW)
        if not res or res.get("pattern") != pattern_name or res.get("target") is None:
            continue
        horizon = max(res.get("horizon_bars") or 20, 15)
        # De-dup: skip if we're still inside the prior occurrence's horizon.
        if idx < last_entry_idx + horizon:
            continue
        signal = res["signal"]
        target = res["target"]
        entry = closes[idx]
        # Measured-move test: stop is the mirror of the target (≈1:1 R:R), which
        # is the standard, honest way to score whether the projection "worked".
        risk = abs(target - entry)
        stop = entry - risk if signal == "bullish" else entry + risk
        out = _outcome(closes, idx, signal, target, stop, horizon)
        if out is None:
            continue
        occurrences += 1
        wins += 1 if out["win"] else 0
        moves.append(out["move_pct"])
        last_entry_idx = idx

    if occurrences == 0:
        return {"available": True, "occurrences": 0,
                "note": f"No prior '{pattern_name}' formations found in history."}

    avg_move = sum(moves) / len(moves)
    return {
        "available": True,
        "pattern": pattern_name,
        "occurrences": occurrences,
        "wins": wins,
        "hit_rate": round(wins / occurrences * 100, 1),
        "avg_move_pct": round(avg_move, 2),
        "years": round(n / 250, 1),
        "low_confidence": occurrences < _MIN_OCCURRENCES,
    }


def backtest_pattern(ticker: str, pattern_name: str) -> dict:
    """Cached backtest of `pattern_name` on `ticker`'s full history."""
    if not pattern_name or pattern_name.lower().startswith("no clear"):
        return {"available": False, "reason": "No pattern to backtest."}
    key = f"{ticker.upper()}|{pattern_name}"
    cached = _CACHE.get(key)
    now = time.time()
    if cached and (now - cached[0]) < _TTL:
        return cached[1]
    try:
        result = _run(ticker, pattern_name)
    except Exception as e:
        if cached:
            return cached[1]
        return {"available": False, "reason": f"Backtest failed: {e}"}
    _CACHE[key] = (now, result)
    return result
