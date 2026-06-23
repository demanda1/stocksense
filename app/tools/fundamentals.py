import time
import yfinance as yf
from nselib import capital_market
from app.config import to_yf_symbol

# Fundamentals barely change intraday (P/E, EPS, ROE update quarterly), but
# yf.Ticker().info is Yahoo's heaviest, most rate-limited call. Cache results
# per symbol so repeated polls reuse them instead of re-hitting Yahoo (which
# returns 429 / "Too Many Requests" once you exceed its informal IP limit).
_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 3600  # seconds (1 hour)


def get_fundamentals(ticker: str, exchange: str = "NS", force: bool = False) -> dict:
    """Fetch key fundamental metrics for an Indian stock (NSE/BSE), cached.

    Returns a cached result within _CACHE_TTL to avoid Yahoo rate limits.
    Pass force=True to bypass the cache.
    """
    symbol = to_yf_symbol(ticker, exchange)  # e.g. RELIANCE -> RELIANCE.NS

    cached = _CACHE.get(symbol)
    if cached and not force and (time.time() - cached[0]) < _CACHE_TTL:
        return cached[1]

    info = yf.Ticker(symbol).info
    if not info or info.get("regularMarketPrice") is None:
        # If Yahoo throttled us but we have a stale cache, serve it rather than fail.
        if cached:
            return cached[1]
        raise ValueError(f"No data for {symbol}. Check the ticker / exchange.")
    result = {
        "symbol": symbol,
        "name": info.get("longName", ticker),
        "industry": info.get("industry", "n/a"),
        "currency": info.get("currency", "INR"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "eps_ttm": info.get("trailingEps"),
        "revenue_growth": info.get("revenueGrowth"),
        "profit_margin": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "roe": info.get("returnOnEquity"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
        "beta": info.get("beta"),
        "dividend_yield": info.get("dividendYield"),
    }
    _CACHE[symbol] = (time.time(), result)
    return result


def get_quote_nse(ticker: str) -> dict:
    """Fallback: live price/volume direct from NSE (no Yahoo)."""
    df = capital_market.price_volume_and_deliverable_position_data(symbol=ticker.upper(), period="1M")
    last = df.iloc[-1]
    return {
        "symbol": ticker.upper(), 
        "source": "nselib",
        "last_price": last.get("ClosePrice"),
        "high_52w": last.get("HighPrice"),
        "low_52w": last.get("LowPrice")
}

