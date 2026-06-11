import yfinance as yf
from nselib import capital_market
from app.config import to_yf_symbol

def get_fundamentals(ticker: str, exchange: str = "NS") -> dict:
    """Fetch key fundamental metrics for an Indian stock (NSE/BSE)."""
    symbol = to_yf_symbol(ticker, exchange) # e.g. RELIANCE -> RELIANCE.NS
    info = yf.Ticker(symbol).info
    if not info or info.get("regularMarketPrice") is None:
        raise ValueError(f"No data for {symbol}. Check the ticker / exchange.")
    return {
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

