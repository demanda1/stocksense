"""Rule-based chart pattern detection (no LLM).

Given an OHLC price series, find swing pivots and match them against a core set
of classic chart patterns. For each match we compute a *measured-move* target
(textbook geometry) and a confidence score from how cleanly the geometry fits.

All targets are measured moves for EDUCATIONAL purposes, not price forecasts.

Public entry point: detect_pattern(closes, highs, lows, dates) -> dict | None
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import math

import numpy as np


# ---------------------------------------------------------------------------
# Pivot detection
# ---------------------------------------------------------------------------
@dataclass
class Pivot:
    idx: int        # position in the series
    price: float
    kind: str       # "high" or "low"


def find_pivots(highs: list[float], lows: list[float], window: int = 5) -> list[Pivot]:
    """Find swing highs/lows: a bar that is the extreme within +/- `window` bars.

    A larger window yields fewer, more significant pivots.
    """
    n = len(highs)
    pivots: list[Pivot] = []
    for i in range(window, n - window):
        left_hi = highs[i - window:i]
        right_hi = highs[i + 1:i + window + 1]
        left_lo = lows[i - window:i]
        right_lo = lows[i + 1:i + window + 1]

        # Swing high: strictly above both flanks (>= within a flank handles
        # short plateaus, but must strictly exceed the flank extremes overall).
        if (highs[i] >= max(left_hi) and highs[i] >= max(right_hi)
                and highs[i] > min(left_hi) and highs[i] > min(right_hi)):
            pivots.append(Pivot(i, highs[i], "high"))
        # Swing low: strictly below both flanks.
        elif (lows[i] <= min(left_lo) and lows[i] <= min(right_lo)
              and lows[i] < max(left_lo) and lows[i] < max(right_lo)):
            pivots.append(Pivot(i, lows[i], "low"))

    # Collapse runs of same-kind pivots (plateaus) into the most extreme one,
    # so we don't emit two adjacent "high" pivots from a flat top.
    collapsed: list[Pivot] = []
    for p in pivots:
        if collapsed and collapsed[-1].kind == p.kind:
            prev = collapsed[-1]
            better = (p.price > prev.price) if p.kind == "high" else (p.price < prev.price)
            if better:
                collapsed[-1] = p
        else:
            collapsed.append(p)
    return collapsed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pct_diff(a: float, b: float) -> float:
    """Absolute percentage difference between two prices."""
    base = (abs(a) + abs(b)) / 2 or 1.0
    return abs(a - b) / base


def _slope(xs: list[int], ys: list[float]) -> float:
    """Least-squares slope of ys over xs (price per bar)."""
    if len(xs) < 2:
        return 0.0
    return float(np.polyfit(xs, ys, 1)[0])


def _result(pattern, signal, confidence, target, breakout, current, rationale,
            horizon_bars):
    """Standard return envelope shared by every detector."""
    return {
        "pattern": pattern,
        "signal": signal,                       # bullish | bearish | neutral
        "confidence": int(round(max(0, min(100, confidence)))),
        "current_price": round(current, 2),
        "breakout_level": round(breakout, 2) if breakout is not None else None,
        "target": round(target, 2) if target is not None else None,
        "projected_move_pct": (
            round((target - current) / current * 100, 1)
            if target is not None and current else None
        ),
        "horizon_bars": horizon_bars,
        "rationale": rationale,
        "disclaimer": "Measured-move geometry, educational only — not financial advice.",
    }


# ---------------------------------------------------------------------------
# Individual detectors. Each returns a result dict or None.
# Each receives the pivot list (most-recent-last) and the latest close.
# ---------------------------------------------------------------------------
def _double_top_bottom(pivots, current, tol=0.03):
    """Two roughly-equal highs (top) or lows (bottom) with a trough/peak between."""
    if len(pivots) < 3:
        return None
    a, b, c = pivots[-3], pivots[-2], pivots[-1]

    # Double Top: high - low - high, the two highs roughly equal
    if a.kind == "high" and b.kind == "low" and c.kind == "high":
        if _pct_diff(a.price, c.price) <= tol:
            neckline = b.price
            height = ((a.price + c.price) / 2) - neckline
            target = neckline - height                      # projected down
            conf = 70 - _pct_diff(a.price, c.price) / tol * 20
            return _result(
                "Double Top", "bearish", conf, target, neckline, current,
                f"Two highs near ₹{a.price:.2f}/₹{c.price:.2f} with neckline "
                f"₹{neckline:.2f}. Measured move = pattern height below neckline.",
                horizon_bars=c.idx - a.idx)

    # Double Bottom: low - high - low, the two lows roughly equal
    if a.kind == "low" and b.kind == "high" and c.kind == "low":
        if _pct_diff(a.price, c.price) <= tol:
            neckline = b.price
            height = neckline - ((a.price + c.price) / 2)
            target = neckline + height                      # projected up
            conf = 70 - _pct_diff(a.price, c.price) / tol * 20
            return _result(
                "Double Bottom", "bullish", conf, target, neckline, current,
                f"Two lows near ₹{a.price:.2f}/₹{c.price:.2f} with neckline "
                f"₹{neckline:.2f}. Measured move = pattern height above neckline.",
                horizon_bars=c.idx - a.idx)
    return None


def _head_and_shoulders(pivots, current, tol=0.04):
    """H&S: high-low-HIGHER high-low-high with the two shoulders roughly equal.
    Inverse H&S mirrors it on lows."""
    if len(pivots) < 5:
        return None
    p = pivots[-5:]
    kinds = [x.kind for x in p]

    # Top: H L H L H  (middle high = head, outer highs = shoulders)
    if kinds == ["high", "low", "high", "low", "high"]:
        ls, t1, head, t2, rs = p
        if (head.price > ls.price and head.price > rs.price
                and _pct_diff(ls.price, rs.price) <= tol):
            neckline = (t1.price + t2.price) / 2
            height = head.price - neckline
            target = neckline - height
            conf = 75 - _pct_diff(ls.price, rs.price) / tol * 20
            return _result(
                "Head & Shoulders", "bearish", conf, target, neckline, current,
                f"Head ₹{head.price:.2f} above shoulders "
                f"₹{ls.price:.2f}/₹{rs.price:.2f}; neckline ₹{neckline:.2f}.",
                horizon_bars=rs.idx - ls.idx)

    # Inverse: L H L H L  (middle low = head)
    if kinds == ["low", "high", "low", "high", "low"]:
        ls, t1, head, t2, rs = p
        if (head.price < ls.price and head.price < rs.price
                and _pct_diff(ls.price, rs.price) <= tol):
            neckline = (t1.price + t2.price) / 2
            height = neckline - head.price
            target = neckline + height
            conf = 75 - _pct_diff(ls.price, rs.price) / tol * 20
            return _result(
                "Inverse Head & Shoulders", "bullish", conf, target, neckline,
                current,
                f"Head ₹{head.price:.2f} below shoulders "
                f"₹{ls.price:.2f}/₹{rs.price:.2f}; neckline ₹{neckline:.2f}.",
                horizon_bars=rs.idx - ls.idx)
    return None


def _triangle(pivots, current):
    """Converging trendlines on the last few highs and lows.

    Ascending  : flat highs, rising lows  -> bullish breakout
    Descending : falling highs, flat lows -> bearish breakout
    Symmetrical: falling highs, rising lows -> neutral (direction = breakout)
    """
    highs = [p for p in pivots if p.kind == "high"][-3:]
    lows = [p for p in pivots if p.kind == "low"][-3:]
    if len(highs) < 2 or len(lows) < 2:
        return None

    hi_slope = _slope([p.idx for p in highs], [p.price for p in highs])
    lo_slope = _slope([p.idx for p in lows], [p.price for p in lows])

    avg_price = current or 1.0
    flat = avg_price * 0.0008          # per-bar slope considered "flat"
    hi_top, lo_bot = highs[-1].price, lows[-1].price
    height = hi_top - lo_bot
    if height <= 0:
        return None

    asc = abs(hi_slope) < flat and lo_slope > flat
    desc = hi_slope < -flat and abs(lo_slope) < flat
    sym = hi_slope < -flat and lo_slope > flat

    if asc:
        return _result(
            "Ascending Triangle", "bullish", 62, hi_top + height, hi_top,
            current,
            f"Flat resistance ₹{hi_top:.2f} with rising support; "
            f"breakout target adds triangle height.",
            horizon_bars=highs[-1].idx - highs[0].idx)
    if desc:
        return _result(
            "Descending Triangle", "bearish", 62, lo_bot - height, lo_bot,
            current,
            f"Flat support ₹{lo_bot:.2f} with falling resistance; "
            f"breakdown target subtracts triangle height.",
            horizon_bars=lows[-1].idx - lows[0].idx)
    if sym:
        # Direction unknown until breakout; bias by where price sits in the range.
        mid = (hi_top + lo_bot) / 2
        if current >= mid:
            return _result(
                "Symmetrical Triangle", "bullish", 50, hi_top + height, hi_top,
                current, "Converging trendlines; price in upper half — "
                "upside breakout bias.",
                horizon_bars=highs[-1].idx - highs[0].idx)
        return _result(
            "Symmetrical Triangle", "bearish", 50, lo_bot - height, lo_bot,
            current, "Converging trendlines; price in lower half — "
            "downside breakout bias.",
            horizon_bars=lows[-1].idx - lows[0].idx)
    return None


def _support_resistance_breakout(closes, pivots, current, tol=0.02):
    """Most recent close breaking out of its RECENT trading range.

    Uses only the last handful of pivots (the consolidation before the
    breakout), not the full-history extremes, so the measured move stays
    realistic. The projected move is also capped to the range size, which is
    the textbook target — never more than one range beyond the level.
    """
    recent = pivots[-6:]
    highs = [p.price for p in recent if p.kind == "high"]
    lows = [p.price for p in recent if p.kind == "low"]
    if not highs or not lows:
        return None
    resistance = max(highs)
    support = min(lows)
    rng = resistance - support
    if rng <= 0:
        return None

    if current > resistance * (1 - tol) and current >= resistance:
        return _result(
            "Resistance Breakout", "bullish", 55, resistance + rng, resistance,
            current,
            f"Close ₹{current:.2f} broke recent resistance ₹{resistance:.2f}; "
            f"target adds the trading range (₹{rng:.2f}) above the breakout.",
            horizon_bars=len(closes) // 4)
    if current < support * (1 + tol) and current <= support:
        return _result(
            "Support Breakdown", "bearish", 55, support - rng, support,
            current,
            f"Close ₹{current:.2f} broke recent support ₹{support:.2f}; "
            f"target subtracts the trading range (₹{rng:.2f}) below the breakdown.",
            horizon_bars=len(closes) // 4)
    return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def detect_pattern(closes: list[float], highs: list[float], lows: list[float],
                   pivot_window: int = 5) -> Optional[dict]:
    """Run all detectors and return the highest-confidence match (or None).

    Detector priority order matters only as a tie-breaker; we pick the result
    with the greatest confidence.
    """
    if len(closes) < 2 * pivot_window + 5:
        return None

    current = float(closes[-1])
    pivots = find_pivots(highs, lows, window=pivot_window)
    if len(pivots) < 3:
        return {
            "pattern": "No clear pattern",
            "signal": "neutral",
            "confidence": 0,
            "current_price": round(current, 2),
            "breakout_level": None,
            "target": None,
            "projected_move_pct": None,
            "horizon_bars": 0,
            "rationale": "Not enough significant swing points to match a pattern.",
            "disclaimer": "Educational only — not financial advice.",
        }

    candidates = [
        _head_and_shoulders(pivots, current),
        _double_top_bottom(pivots, current),
        _triangle(pivots, current),
        _support_resistance_breakout(closes, pivots, current),
    ]
    candidates = [c for c in candidates if c]
    if not candidates:
        return {
            "pattern": "No clear pattern",
            "signal": "neutral",
            "confidence": 0,
            "current_price": round(current, 2),
            "breakout_level": None,
            "target": None,
            "projected_move_pct": None,
            "horizon_bars": 0,
            "rationale": "Swing structure did not match any of the core patterns.",
            "disclaimer": "Educational only — not financial advice.",
        }

    # Flag patterns whose measured target is already reached: a bullish target
    # at/below current price (or bearish at/above) has effectively played out.
    for c in candidates:
        tgt, sig = c.get("target"), c.get("signal")
        if tgt is None:
            continue
        achieved = (sig == "bullish" and tgt <= current) or \
                   (sig == "bearish" and tgt >= current)
        if achieved:
            c["target_achieved"] = True
            c["confidence"] = int(c["confidence"] * 0.5)
            c["rationale"] += " (Measured target already reached — pattern has largely played out.)"
        else:
            c["target_achieved"] = False

    best = max(candidates, key=lambda c: c["confidence"])
    # Attach pivots used (for optional chart markers)
    best["pivots"] = [
        {"idx": p.idx, "price": round(p.price, 2), "kind": p.kind}
        for p in pivots[-6:]
    ]
    return best
