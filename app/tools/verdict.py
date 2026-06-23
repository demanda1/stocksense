"""Multi-signal weighted verdict.

Combines five technical signals — chart pattern, RSI, MACD, trend, volume —
into ONE confidence-weighted bull/bear score, using per-signal weights that
depend on the chosen risk profile (conservative / moderate / aggressive).

Each signal returns a score in [-1, +1] (bearish .. bullish) plus a short
human note. The weighted sum becomes the overall verdict. Pure math — no LLM.
"""
from __future__ import annotations

from app.models.risk import SIGNAL_WEIGHTS
from app.tools.technicals import get_technical_series
from app.tools.patterns import detect_pattern

PIVOT_WINDOW = {"1D": 5, "1W": 4, "5m": 8}


def _clamp(v, lo=-1.0, hi=1.0):
    return max(lo, min(hi, v))


def _pattern_signal(pattern: dict):
    if not pattern or pattern.get("target") is None:
        return 0.0, "No clear pattern."
    sig = pattern.get("signal")
    conf = (pattern.get("confidence") or 0) / 100.0
    if sig == "bullish":
        return conf, f"{pattern['pattern']} (bullish, {pattern['confidence']}%)."
    if sig == "bearish":
        return -conf, f"{pattern['pattern']} (bearish, {pattern['confidence']}%)."
    return 0.0, f"{pattern['pattern']} (neutral)."


def _rsi_signal(rsi_series):
    if not rsi_series:
        return 0.0, "No RSI."
    v = rsi_series[-1]["value"]
    # >70 overbought (bearish lean), <30 oversold (bullish lean); 50 = neutral.
    if v >= 70:
        return -_clamp((v - 70) / 20 + 0.3), f"RSI {v:.0f} — overbought."
    if v <= 30:
        return _clamp((30 - v) / 20 + 0.3), f"RSI {v:.0f} — oversold."
    # Between 30-70: mild momentum read off the 50 midline.
    return _clamp((v - 50) / 40), f"RSI {v:.0f} — neutral momentum."


def _macd_signal(macd_series, signal_series):
    if not macd_series or not signal_series:
        return 0.0, "No MACD."
    m = macd_series[-1]["value"]
    s = signal_series[-1]["value"]
    diff = m - s
    # Normalise the gap by the MACD's own recent magnitude.
    mag = max(abs(m), abs(s), 1e-6)
    score = _clamp(diff / mag)
    if diff > 0:
        return abs(score) * 0.8 + 0.1, "MACD above signal — bullish momentum."
    if diff < 0:
        return -(abs(score) * 0.8 + 0.1), "MACD below signal — bearish momentum."
    return 0.0, "MACD flat."


def _trend_signal(analysis: dict):
    struct = analysis.get("trend_structure")
    adx = analysis.get("adx") or 0
    # Strength factor: a trend only counts if ADX confirms it.
    strength = _clamp((adx - 15) / 25, 0, 1)   # 0 at ADX15, 1 at ADX40
    if struct == "uptrend":
        return strength, f"Uptrend (ADX {adx:.0f})." if adx else "Uptrend."
    if struct == "downtrend":
        return -strength, f"Downtrend (ADX {adx:.0f})." if adx else "Downtrend."
    return 0.0, f"Sideways / no trend (ADX {adx:.0f})."


def _volume_signal(analysis: dict, pattern_score: float):
    ratio = analysis.get("volume_ratio")
    if ratio is None:
        return 0.0, "No volume data."
    # Volume confirms whichever way price is leaning. High volume amplifies the
    # prevailing bias; low volume undercuts it.
    bias = 1.0 if pattern_score >= 0 else -1.0
    if ratio >= 1.5:
        return _clamp(0.6 * bias), f"High volume ({ratio}× avg) — confirms the move."
    if ratio < 0.7:
        return _clamp(-0.3 * bias), f"Low volume ({ratio}× avg) — move lacks conviction."
    return _clamp(0.15 * bias), f"Normal volume ({ratio}× avg)."


def _label(score: float) -> str:
    if score >= 0.5:
        return "Strong Buy"
    if score >= 0.15:
        return "Buy"
    if score > -0.15:
        return "Neutral / Hold"
    if score > -0.5:
        return "Sell"
    return "Strong Sell"


def compute_verdict(ticker: str, tf: str = "1D", risk: str = "moderate") -> dict:
    risk = risk if risk in SIGNAL_WEIGHTS else "moderate"
    weights = SIGNAL_WEIGHTS[risk]

    series = get_technical_series(ticker, tf)   # raises ValueError on bad data
    analysis = series.get("analysis", {})
    closes = [c["close"] for c in series["candles"]]
    highs = [c["high"] for c in series["candles"]]
    lows = [c["low"] for c in series["candles"]]
    pattern = detect_pattern(closes, highs, lows, PIVOT_WINDOW.get(tf, 5)) or {}

    ps, pnote = _pattern_signal(pattern)
    rs, rnote = _rsi_signal(series.get("rsi"))
    ms, mnote = _macd_signal(series.get("macd"), series.get("macd_signal"))
    ts, tnote = _trend_signal(analysis)
    vs, vnote = _volume_signal(analysis, ps)

    signals = [
        {"key": "pattern", "label": "Chart pattern", "score": round(ps, 2), "weight": weights["pattern"], "note": pnote},
        {"key": "rsi", "label": "RSI", "score": round(rs, 2), "weight": weights["rsi"], "note": rnote},
        {"key": "macd", "label": "MACD", "score": round(ms, 2), "weight": weights["macd"], "note": mnote},
        {"key": "trend", "label": "Trend", "score": round(ts, 2), "weight": weights["trend"], "note": tnote},
        {"key": "volume", "label": "Volume", "score": round(vs, 2), "weight": weights["volume"], "note": vnote},
    ]
    for s in signals:
        s["contribution"] = round(s["score"] * s["weight"], 3)

    total = sum(s["contribution"] for s in signals)        # in [-1, +1]
    total = _clamp(total)
    bull_pct = round((total + 1) / 2 * 100)                 # 0..100, 50 = neutral

    # Agreement: how aligned are the non-zero signals?
    dirs = [1 if s["score"] > 0.05 else -1 if s["score"] < -0.05 else 0 for s in signals]
    nonzero = [d for d in dirs if d != 0]
    agree = 0
    if nonzero:
        majority = 1 if sum(nonzero) >= 0 else -1
        agree = round(sum(1 for d in nonzero if d == majority) / len(nonzero) * 100)

    return {
        "ticker": series["symbol"],
        "timeframe": tf,
        "risk": risk,
        "score": round(total, 3),       # -1..+1
        "bull_pct": bull_pct,           # 0..100
        "label": _label(total),
        "agreement": agree,             # % of signals agreeing with the call
        "signals": signals,
        "disclaimer": "Weighted technical signals, educational only — not financial advice.",
    }
