import os
from dotenv import load_dotenv
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY")
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Indian tickers use a suffix: .NS = NSE, .BO = BSE.
# Helper: turn "RELIANCE" into "RELIANCE.NS" if no suffix given.
def to_yf_symbol(ticker: str, exchange: str = "NS") -> str:
    t = ticker.upper().strip()
    return t if t.endswith((".NS", ".BO")) else f"{t}.{exchange}"