import pandas as pd
import yfinance as yf
import pandas_ta as ta
from app.config import to_yf_symbol

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
