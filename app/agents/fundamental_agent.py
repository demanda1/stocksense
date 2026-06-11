from langchain_groq import ChatGroq
from app.config import DEFAULT_MODEL
from app.tools.fundamentals import get_fundamentals
from app.models.schemas import FundamentalView

llm = ChatGroq(model=DEFAULT_MODEL, temperature=0)
structured_llm = llm.with_structured_output(FundamentalView)

PROMPT = """You are a value-investing analyst covering Indian equities (NSE/BSE).
Given these fundamentals (values in INR), judge whether the stock looks
bullish, neutral, or bearish on fundamentals alone.
Consider valuation (P/E vs sector norms), growth, margins, ROE, and debt.

Ticker: {ticker}
Fundamentals: {data}

Return your structured view."""

def analyze_fundamentals(ticker: str) -> FundamentalView:
    data = get_fundamentals(ticker) #Fetches the stock fundamentals
    msg = PROMPT.format(ticker=ticker, data=data) #adds the stock fundamentals in prompt
    result = structured_llm.invoke(msg) #llm predicts if it is bearish, neutral or bullish
    result.key_metrics = data
    return result