# StockSense AI

A multi-agent stock-analysis API + dashboard for **Indian equities** (NSE/BSE).

- **Dashboard** — a single-page grid with a **live candlestick chart** (SMA20/50, Bollinger
  bands, RSI/MACD panels) and a **rule-based chart-pattern detector** that draws a
  measured-move **projection line** and target price.
- **Multi-agent `/analyze`** — three LLM analysts (fundamental, technical, sentiment) run in
  parallel via LangGraph, then an advisor synthesizes a buy/hold/sell call.

> ⚠️ Educational only — not financial advice. Price data via yfinance is delayed ~15 min.

## Requirements

- **Python 3.10+** (3.13 recommended — several deps and `pandas_ta` no longer support 3.9).
- API keys in a `.env` file (only needed for the `/analyze` LLM features, **not** for the dashboard):
  ```
  GROQ_API_KEY=...
  NEWSDATA_API_KEY=...
  ```

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.api:app --reload --port 8000
```

Then open **http://127.0.0.1:8000/** for the dashboard.

The dashboard endpoints (`/candles`, `/pattern`) work with only the lightweight data deps
installed (fastapi, uvicorn, yfinance, pandas, pandas_ta). The LLM/RAG stack is imported
lazily and is only required when you call `POST /analyze`.

## API

| Endpoint | Description |
|---|---|
| `GET /` | Redirects to the dashboard. |
| `GET /candles?ticker=&tf=` | OHLC + SMA20/50, Bollinger, RSI, MACD series. `tf` ∈ `1D`, `1W`, `5m`. |
| `GET /pattern?ticker=&tf=` | Detected chart pattern, signal, breakout level, measured target, projection line, confidence, rationale. |
| `GET /pattern-explain?ticker=&tf=` | Beginner plain-English explanation of the pattern (Groq when `GROQ_API_KEY` set, else a rule-based template). |
| `GET /fundamentals?ticker=&ai=` | Key metrics (always, via yfinance). `ai=true` adds the AI bullish/neutral/bearish signal. |
| `GET /sentiment?ticker=&ai=` | Recent headlines (always). `ai=true` adds the AI news-sentiment signal via the RAG pipeline. |
| `GET /recommendation?ticker=&risk=` | Full multi-agent buy/hold/sell call. Requires the LLM stack + `GROQ_API_KEY`. |
| `GET /symbols` | Full NSE equity list (symbol + name) for the ticker autocomplete. Bundled & loaded once at startup. |
| `GET /timeframes` | Available timeframes. |
| `POST /analyze` | Full multi-agent analysis `{ticker, risk}` → fundamental/technical/sentiment + buy/hold/sell. |

### AI usage / quota control (SSAI buttons)

To avoid burning LLM quota, **no AI call ever runs automatically** — not on ticker load and not on
the 30s live poll. The poll only refreshes free data: the candlestick chart, indicators, raw
fundamentals metrics, and news headlines.

Each AI-backed grid has its own **✦ SSAI** button that fires the AI call for *only that grid* when
clicked:

| Grid | SSAI button | Endpoint hit |
|---|---|---|
| Pattern + Prediction | Explain this pattern | `/pattern-explain` |
| Fundamentals | Analyse fundamentals | `/fundamentals?ai=true` |
| Sentiment | Analyse sentiment | `/sentiment?ai=true` |
| Recommendation | Run advisor | `/recommendation` |

AI results are cached client-side and re-injected after each poll re-render, so a result you fetched
stays on screen and is **not** re-requested every 30 seconds. The cache is cleared when you change
the ticker. Endpoints that need the LLM degrade gracefully when no key is present.

Tickers may be given bare (`RELIANCE`) — the `.NS` (NSE) suffix is added automatically.

## Architecture

```
Dashboard (app/static/index.html, Lightweight Charts)
    │  polls every 30s
    ▼
FastAPI (app/api.py)
    ├── /candles, /pattern ──► app/tools/technicals.py (yfinance + pandas_ta)
    │                          app/tools/patterns.py   (rule-based detection)
    └── /analyze ────────────► LangGraph (app/graph/) ─► agents (app/agents/)
                                                          ├ fundamental (yfinance)
                                                          ├ technical   (indicators)
                                                          ├ sentiment   (news RAG → Chroma)
                                                          └ advisor     (weighted by risk)
```

### Ticker autocomplete

The ticker box suggests matches as you type — e.g. `IC` surfaces `ICICIBANK`, `ICICIGI`, `ICRA`…
It matches on **both** the symbol and the company name, with symbol-prefix matches ranked first.

Suggestions are **instant**: the full NSE equity list (~2,000 symbols) is bundled at
`app/static/symbols.json` and fetched once on page load, then filtered in memory — no per-keystroke
API call. Tickers not in the list can still be typed in full (press Enter on the "no match" hint).

To refresh the list (new listings / delistings):

```bash
python scripts/refresh_symbols.py                 # downloads the latest list from NSE
python scripts/refresh_symbols.py --csv EQUITY_L.csv   # or build from a local CSV
```

### Playground (paper-trading)

A second tab — **StockSense · Playground** — is a virtual trading simulator for practising
intraday / futures / options with no real money. Toggle it from the header tabs.

- **Dummy wallet** (starts at ₹1,00,000) with *Add funds* and *Reset*. All state — wallet, positions,
  pending orders, trade history — lives in the browser's `localStorage`, so it survives refreshes.
- **Segments**: Intraday equity, Futures (20% margin / 5× leverage), Options (CE/PE with an estimated
  premium and a synthetic strike chain).
- **Order types** (each with a tooltip): **Market** (instant at LTP), **Limit** (fills at your price or
  better), **SL** (stop-loss limit), **SL-M** (stop-loss market). Limit/SL/SL-M sit as *pending* orders
  and fill when the polled price crosses the trigger.
- **Positions** with live P&L, an **order book**, **trade history**, and one-click square-off. Prices
  come from the existing `/candles` feed (delayed). It's fully client-side — entirely separate from the
  analysis dashboard.

### Pattern engine (`app/tools/patterns.py`)

Pure rule-based geometry — no LLM. Finds swing pivots, then matches the core set:
**double top/bottom, head & shoulders (+ inverse), ascending/descending/symmetrical
triangle, support/resistance breakout**. Each match computes a textbook **measured-move
target** and a confidence from how cleanly the geometry fits. Patterns whose target has
already been reached are flagged and down-weighted.
