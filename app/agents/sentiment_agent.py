from langchain_groq import ChatGroq
from app.config import DEFAULT_MODEL
from app.tools.rag import build_news_index, retrieve
from app.models.schemas import FundamentalView

llm = ChatGroq(model=DEFAULT_MODEL, temperature=0)
structured_llm = llm.with_structured_output(FundamentalView)

PROMPT = """You are a market sentiment analyst covering Indian equities.
Based ONLY on these recent news excerpts, judge sentiment as bullish,
neutral, or bearish. Cite themes you see. Do not invent facts.
Ticker: {ticker}
News excerpts:
{news}
Return your structured view."""

def analyze_sentiment(ticker: str) -> FundamentalView:
    store = build_news_index(ticker)
    excerpts = retrieve(store, f"{ticker} outlook risk earnings growth")
    joined = "\n- ".join(excerpts)
    result = structured_llm.invoke(PROMPT.format(ticker=ticker, news=joined))
    result.key_metrics = {"excerpts_used": len(excerpts)}
    return result

