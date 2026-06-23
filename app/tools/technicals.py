import pandas as pd
import yfinance as yf
from app.config import to_yf_symbol

# Timeframe presets for the dashboard: (yfinance period, interval).
TIMEFRAMES = {
    "1D": ("6mo", "1d"),    # daily candles, 6 months of history
    "1W": ("2y", "1wk"),    # weekly candles, 2 years
    "5m": ("5d", "5m"),     # intraday 5-minute, last 5 days
}


# --- Indicators (plain pandas — no pandas_ta / numba dependency) ----------
# Implemented to match pandas_ta's conventions so values are unchanged.
def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    """Wilder's RSI (same smoothing pandas_ta uses: RMA = EWM alpha=1/length)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line) — EMA(fast)-EMA(slow), EMA(signal) of it."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def bollinger(series: pd.Series, length: int = 20, std: float = 2.0):
    """Returns (lower, middle, upper). Uses population std (ddof=0) like pandas_ta."""
    mid = series.rolling(length).mean()
    sd = series.rolling(length).std(ddof=0)
    return mid - std * sd, mid, mid + std * sd


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(high, low, close, length: int = 14) -> pd.Series:
    """Average True Range (Wilder smoothing) — typical move size per bar."""
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def adx(high, low, close, length: int = 14) -> pd.Series:
    """Average Directional Index — trend STRENGTH (not direction). >25 = trending."""
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    tr = _true_range(high, low, close)
    atr_ = tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)
    return dx.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def support_resistance(highs, lows, closes, window: int = 5, max_levels: int = 6):
    """Cluster recent swing pivots into horizontal support/resistance zones.

    Returns a sorted list of {price, kind, touches}. Levels with more touches are
    stronger. kind is 'support' (below current price) or 'resistance' (above).
    """
    n = len(closes)
    if n < 2 * window + 5:
        return []
    pivots = []
    for i in range(window, n - window):
        seg_hi = highs[i - window:i + window + 1]
        seg_lo = lows[i - window:i + window + 1]
        if highs[i] >= max(seg_hi):
            pivots.append(highs[i])
        if lows[i] <= min(seg_lo):
            pivots.append(lows[i])
    if not pivots:
        return []

    current = closes[-1]
    # Cluster pivots that sit within ~1.2% of each other into one level.
    tol = current * 0.012 or 1.0
    pivots.sort()
    clusters = []
    bucket = [pivots[0]]
    for p in pivots[1:]:
        if p - bucket[-1] <= tol:
            bucket.append(p)
        else:
            clusters.append(bucket)
            bucket = [p]
    clusters.append(bucket)

    levels = []
    for b in clusters:
        price = sum(b) / len(b)
        levels.append({
            "price": round(price, 2),
            "kind": "resistance" if price >= current else "support",
            "touches": len(b),
        })
    # Keep the strongest (most-touched) levels, nearest the current price.
    levels.sort(key=lambda x: (-x["touches"], abs(x["price"] - current)))
    return levels[:max_levels]


def trend_structure(closes, window: int = 5):
    """Classify recent swing structure: uptrend (HH+HL), downtrend (LH+LL), or range."""
    n = len(closes)
    if n < 2 * window + 10:
        return "unknown"
    highs_idx, lows_idx = [], []
    for i in range(window, n - window):
        seg = closes[i - window:i + window + 1]
        if closes[i] >= max(seg):
            highs_idx.append(closes[i])
        elif closes[i] <= min(seg):
            lows_idx.append(closes[i])
    hh = len(highs_idx) >= 2 and highs_idx[-1] > highs_idx[-2]
    hl = len(lows_idx) >= 2 and lows_idx[-1] > lows_idx[-2]
    lh = len(highs_idx) >= 2 and highs_idx[-1] < highs_idx[-2]
    ll = len(lows_idx) >= 2 and lows_idx[-1] < lows_idx[-2]
    if hh and hl:
        return "uptrend"
    if lh and ll:
        return "downtrend"
    return "sideways"


def _clean_float(v):
    """Return a JSON-safe float (None for NaN/inf), else None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return round(f, 4)


def get_technical_series(ticker: str, tf: str = "1D", exchange: str = "NS") -> dict:
    """Return full OHLC + indicator arrays for charting, for a given timeframe.

    Shape: {symbol, timeframe, candles:[{time,open,high,low,close,volume}],
            sma20:[{time,value}], sma50, bb_upper, bb_lower, rsi, macd, macd_signal}
    Times are unix seconds (UTC) — what Lightweight Charts expects.
    """
    if tf not in TIMEFRAMES:
        raise ValueError(f"Unknown timeframe '{tf}'. Use one of {list(TIMEFRAMES)}.")
    period, interval = TIMEFRAMES[tf]
    symbol = to_yf_symbol(ticker, exchange)

    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df.empty:
        raise ValueError(f"No price data for {symbol} ({tf}).")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df["SMA20"] = sma(df["Close"], 20)
    df["SMA50"] = sma(df["Close"], 50)
    df["RSI"] = rsi(df["Close"], 14)
    df["MACD_12_26_9"], df["MACDs_12_26_9"] = macd(df["Close"])
    df["BBL"], _, df["BBU"] = bollinger(df["Close"], 20)
    df["ATR"] = atr(df["High"], df["Low"], df["Close"], 14)
    df["ADX"] = adx(df["High"], df["Low"], df["Close"], 14)
    df["VOLSMA"] = sma(df["Volume"], 20) if "Volume" in df.columns else None

    # --- analysis summary (computed before reset for clean array access) ---
    closes_arr = [float(x) for x in df["Close"].dropna().tolist()]
    highs_arr = [float(x) for x in df["High"].dropna().tolist()]
    lows_arr = [float(x) for x in df["Low"].dropna().tolist()]
    levels = support_resistance(highs_arr, lows_arr, closes_arr)
    structure = trend_structure(closes_arr)
    last_close = closes_arr[-1] if closes_arr else None
    last_atr = _clean_float(df["ATR"].dropna().iloc[-1]) if df["ATR"].notna().any() else None
    last_adx = _clean_float(df["ADX"].dropna().iloc[-1]) if df["ADX"].notna().any() else None
    last_vol = _clean_float(df["Volume"].iloc[-1]) if "Volume" in df.columns else None
    avg_vol = _clean_float(df["VOLSMA"].dropna().iloc[-1]) if df.get("VOLSMA") is not None and df["VOLSMA"].notna().any() else None
    vol_ratio = round(last_vol / avg_vol, 2) if last_vol and avg_vol else None

    df = df.reset_index()
    time_col = "Datetime" if "Datetime" in df.columns else "Date"

    def secs(ts):
        return int(pd.Timestamp(ts).timestamp())

    def line(col):
        if col not in df.columns:
            return []
        out = []
        for _, row in df.iterrows():
            v = _clean_float(row[col])
            if v is not None:
                out.append({"time": secs(row[time_col]), "value": v})
        return out

    candles = []
    for _, row in df.iterrows():
        o, h, l, c = (_clean_float(row[x]) for x in ("Open", "High", "Low", "Close"))
        if None in (o, h, l, c):
            continue
        candles.append({
            "time": secs(row[time_col]),
            "open": o, "high": h, "low": l, "close": c,
            "volume": _clean_float(row.get("Volume")) or 0,
        })

    # ATR as % of price, and an expected daily range band around current price.
    atr_pct = round(last_atr / last_close * 100, 2) if last_atr and last_close else None

    if last_adx is None:
        trend_label = "unknown"
    elif last_adx >= 40:
        trend_label = "very strong"
    elif last_adx >= 25:
        trend_label = "strong"
    elif last_adx >= 18:
        trend_label = "weak"
    else:
        trend_label = "no trend (choppy)"

    if vol_ratio is None:
        vol_label = "n/a"
    elif vol_ratio >= 1.5:
        vol_label = "high"
    elif vol_ratio >= 0.8:
        vol_label = "normal"
    else:
        vol_label = "low"

    return {
        "symbol": symbol,
        "timeframe": tf,
        "candles": candles,
        "sma20": line("SMA20"),
        "sma50": line("SMA50"),
        "bb_upper": line("BBU"),
        "bb_lower": line("BBL"),
        "rsi": line("RSI"),
        "macd": line("MACD_12_26_9"),
        "macd_signal": line("MACDs_12_26_9"),
        "volumes": [
            {"time": c["time"], "value": c["volume"],
             "color": "rgba(38,166,154,0.5)" if c["close"] >= c["open"] else "rgba(239,83,80,0.5)"}
            for c in candles
        ],
        "levels": levels,
        "analysis": {
            "price": last_close,
            "trend_structure": structure,        # uptrend | downtrend | sideways
            "adx": last_adx,
            "trend_strength": trend_label,
            "atr": last_atr,
            "atr_pct": atr_pct,
            "expected_range": (
                {"low": round(last_close - last_atr, 2), "high": round(last_close + last_atr, 2)}
                if last_close and last_atr else None
            ),
            "volume": last_vol,
            "avg_volume": avg_vol,
            "volume_ratio": vol_ratio,
            "volume_label": vol_label,
        },
    }

def get_technicals(ticker: str, exchange: str = "NS") -> dict:
    """Fetch 6 months of prices and compute technical indicators (NSE/BSE)."""
    symbol = to_yf_symbol(ticker, exchange)
    df = yf.download(symbol, period="6mo", interval="1d", progress=False)
    if df.empty:
        raise ValueError(f"No price data for {symbol}")

    # Flatten the multi-level columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Calculate indicators (plain pandas)
    df["RSI"] = rsi(df["Close"], 14)
    df["MACD_12_26_9"], df["MACDs_12_26_9"] = macd(df["Close"])
    df["SMA20"] = sma(df["Close"], 20)
    df["SMA50"] = sma(df["Close"], 50)
    df["BBL_20_2.0"], df["BBM_20_2.0"], df["BBU_20_2.0"] = bollinger(df["Close"], 20)

    # Clean any NaN values that could break JSON conversion
    df = df.dropna()
    if df.empty:
        raise ValueError("Not enough historical data left after removing NaNs for indicators.")

    last = df.iloc[-1]
    
    return {
        "symbol": symbol,
        "price": round(float(last["Close"]), 2),
        "rsi": round(float(last["RSI"]), 1),
        "macd": round(float(last["MACD_12_26_9"]), 3),
        "macd_signal": round(float(last["MACDs_12_26_9"]), 3),
        "sma20": round(float(last["SMA20"]), 2),
        "sma50": round(float(last["SMA50"]), 2),
        "bb_upper": round(float(last["BBU_20_2.0"]), 2),
        "bb_lower": round(float(last["BBL_20_2.0"]), 2),
    }
