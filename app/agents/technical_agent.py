from langchain_groq import ChatGroq
from app.config import DEFAULT_MODEL
from app.tools.technicals import get_technicals
from app.models.schemas import FundamentalView # reuse same shape

llm = ChatGroq(model=DEFAULT_MODEL, temperature=0)
structured_llm = llm.with_structured_output(FundamentalView)

PROMPT = """You are a technical analyst. Interpret these indicators into a
bullish, neutral, or bearish signal. Rules of thumb:
- RSI > 70 overbought, < 30 oversold
- MACD above signal line = bullish momentum
- Price above SMA20 & SMA50 = uptrend
- Price near lower Bollinger band = potentially oversold
Ticker: {ticker}
Indicators: {data}
Return your structured view."""

def analyze_technicals(ticker: str) -> FundamentalView:
    data = get_technicals(ticker)
    result = structured_llm.invoke(PROMPT.format(ticker=ticker, data=data))
    result.key_metrics = data
    return result