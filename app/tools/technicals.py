import pandas as pd
import yfinance as yf
import pandas_ta as ta
from app.config import to_yf_symbol

# Timeframe presets for the dashboard: (yfinance period, interval).
TIMEFRAMES = {
    "1D": ("6mo", "1d"),    # daily candles, 6 months of history
    "1W": ("2y", "1wk"),    # weekly candles, 2 years
    "5m": ("5d", "5m"),     # intraday 5-minute, last 5 days
}


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

    df["SMA20"] = ta.sma(df["Close"], length=20)
    df["SMA50"] = ta.sma(df["Close"], length=50)
    df["RSI"] = ta.rsi(df["Close"], length=14)
    macd = ta.macd(df["Close"])
    if macd is not None:
        df = df.join(macd)
    bb = ta.bbands(df["Close"], length=20)
    if bb is not None:
        bb.columns = ["BBL", "BBM", "BBU", "BBB", "BBP"]
        df = df.join(bb)

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

    # Calculate indicators
    df["RSI"] = ta.rsi(df["Close"], length=14)
    
    macd = ta.macd(df["Close"])
    if macd is not None:
        df = df.join(macd)

    df["SMA20"] = ta.sma(df["Close"], length=20)
    df["SMA50"] = ta.sma(df["Close"], length=50)
    
    bb = ta.bbands(df["Close"], length=20)
    if bb is not None:
        # Rename Bollinger Bands columns explicitly to match your output keys exactly
        bb.columns = ["BBL_20_2.0", "BBM_20_2.0", "BBU_20_2.0", "BBB_20_2.0", "BBP_20_2.0"]
        df = df.join(bb)

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
