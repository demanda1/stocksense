import os

from fastapi import FastAPI, HTTPException, Query as Q
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.tools.technicals import get_technical_series, TIMEFRAMES
from app.tools.patterns import detect_pattern
from app.config import GROQ_API_KEY


def GROQ_AVAILABLE() -> bool:
    """True when the LLM features can run (key set + langchain-groq installed)."""
    if not GROQ_API_KEY:
        return False
    try:
        import langchain_groq  # noqa: F401
        return True
    except ImportError:
        return False

app = FastAPI(title="StockSense AI")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# The LLM/graph stack (langchain, groq, chroma…) is imported lazily so the
# dashboard endpoints (/candles, /pattern) can run without those heavy deps.
_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        from app.graph.build import build_graph
        _graph = build_graph()
    return _graph

# Pivot sensitivity per timeframe: longer/intraday series want a wider window.
PIVOT_WINDOW = {"1D": 5, "1W": 4, "5m": 8}


class Query(BaseModel):
    ticker: str
    risk: str = "moderate"


@app.post("/analyze")
def analyze(q: Query):
    from app.agents.advisor_agent import advise
    from app.observability import langfuse_handler
    state = _get_graph().invoke(
        {"ticker": q.ticker.upper(), "risk_profile": q.risk},
        config={"callbacks": [langfuse_handler]},
    )
    rec = advise(state)
    return {
        "recommendation": rec.model_dump(),
        "fundamental": state["fundamental"].model_dump(),
        "technical": state["technical"].model_dump(),
        "sentiment": state["sentiment"].model_dump(),
    }


@app.get("/candles")
def candles(ticker: str = Q(...), tf: str = Q("1D")):
    """OHLC + indicator series for the live chart."""
    try:
        return get_technical_series(ticker, tf)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/pattern")
def pattern(ticker: str = Q(...), tf: str = Q("1D")):
    """Rule-based chart pattern + measured-move projection for the chart."""
    try:
        series = get_technical_series(ticker, tf)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    candles_ = series["candles"]
    if len(candles_) < 20:
        raise HTTPException(status_code=400, detail="Not enough candles to detect a pattern.")

    closes = [c["close"] for c in candles_]
    highs = [c["high"] for c in candles_]
    lows = [c["low"] for c in candles_]
    times = [c["time"] for c in candles_]

    result = detect_pattern(closes, highs, lows, pivot_window=PIVOT_WINDOW.get(tf, 5))
    if result is None:
        raise HTTPException(status_code=400, detail="Not enough data to detect a pattern.")

    # Build a projection line: from the last candle to the measured target,
    # spread over `horizon_bars` using the series' average bar spacing.
    projection = []
    if result.get("target") is not None and len(times) >= 2:
        bar = (times[-1] - times[0]) / max(1, len(times) - 1)
        horizon = max(3, int(result.get("horizon_bars") or 10))
        start_t, start_p = times[-1], result["current_price"]
        end_t = start_t + int(bar * horizon)
        end_p = result["target"]
        projection = [
            {"time": start_t, "value": round(start_p, 2)},
            {"time": end_t, "value": round(end_p, 2)},
        ]
    result["projection"] = projection
    result["symbol"] = series["symbol"]
    result["timeframe"] = tf
    return result


@app.get("/pattern-explain")
def pattern_explain(ticker: str = Q(...), tf: str = Q("1D")):
    """Plain-English explanation of the detected pattern's numbers.

    Uses Groq when GROQ_API_KEY is set; otherwise a rule-based template.
    """
    from app.tools.explain import explain_pattern
    result = pattern(ticker=ticker, tf=tf)  # reuse detection (may raise HTTPException)
    return explain_pattern(result)


@app.get("/fundamentals")
def fundamentals(ticker: str = Q(...), ai: bool = Q(False)):
    """Key fundamental metrics (always, via yfinance). Optional AI signal."""
    from app.tools.fundamentals import get_fundamentals
    try:
        data = get_fundamentals(ticker)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    out = {"metrics": data, "signal": None, "reasoning": None, "ai": False}
    if ai and GROQ_AVAILABLE():
        try:
            from app.agents.fundamental_agent import analyze_fundamentals
            view = analyze_fundamentals(ticker)
            out.update(signal=view.signal, confidence=view.confidence,
                       reasoning=view.reasoning, ai=True)
        except Exception:
            pass
    return out


@app.get("/sentiment")
def sentiment(ticker: str = Q(...), ai: bool = Q(False)):
    """Recent headlines (always, structured with links). Optional AI signal."""
    from app.tools.news import get_news_items
    try:
        items = get_news_items(ticker)[:12]
    except Exception:
        items = []

    out = {"news": items, "signal": None, "reasoning": None, "ai": False}
    if ai and GROQ_AVAILABLE():
        try:
            from app.agents.sentiment_agent import analyze_sentiment
            view = analyze_sentiment(ticker)
            out.update(signal=view.signal, confidence=view.confidence,
                       reasoning=view.reasoning, ai=True)
        except Exception:
            pass
    return out


@app.get("/recommendation")
def recommendation(ticker: str = Q(...), risk: str = Q("moderate")):
    """Full multi-agent buy/hold/sell call (requires the LLM stack + key)."""
    if not GROQ_AVAILABLE():
        raise HTTPException(
            status_code=503,
            detail="AI recommendation needs GROQ_API_KEY and the LLM dependencies installed.",
        )
    try:
        from app.agents.advisor_agent import advise
        state = _get_graph().invoke({"ticker": ticker.upper(), "risk_profile": risk})
        rec = advise(state)
        return {
            "recommendation": rec.model_dump(),
            "fundamental": state["fundamental"].model_dump(),
            "technical": state["technical"].model_dump(),
            "sentiment": state["sentiment"].model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


_SYMBOLS_CACHE = None


def _load_symbols():
    """Load the bundled NSE symbol list once and cache it in memory."""
    global _SYMBOLS_CACHE
    if _SYMBOLS_CACHE is None:
        import json
        path = os.path.join(_STATIC_DIR, "symbols.json")
        try:
            with open(path, encoding="utf-8") as f:
                _SYMBOLS_CACHE = json.load(f)
        except (OSError, ValueError):
            _SYMBOLS_CACHE = []
    return _SYMBOLS_CACHE


@app.get("/symbols")
def symbols():
    """Full NSE equity list (symbol + name) for client-side autocomplete.

    Bundled and loaded once at startup — the frontend fetches this a single
    time on page load, then filters in memory (no per-keystroke calls).
    """
    data = _load_symbols()
    return {"count": len(data), "symbols": data}


@app.get("/timeframes")
def timeframes():
    return {"timeframes": list(TIMEFRAMES.keys())}


# --- Static dashboard ---------------------------------------------------------
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR, html=True), name="static")

    @app.get("/")
    def root():
        return RedirectResponse(url="/static/index.html")
