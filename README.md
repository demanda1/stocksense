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

### Sector & market context

The Market Structure box shows the stock's move today vs. its **sector average** and the **Nifty 200**
(relative strength), labelled leading / lagging / in-line. Piggybacks on the cached `/movers` computation
(grouped by the sector field in `app/data/nifty200.json`) — `GET /sector-context`. A stock rising less than
its sector is flagged as weak.

### Price / RSI alerts

The Alerts box lets you set conditions (price or RSI crosses above/below a value) per ticker. They're stored
in `localStorage`, checked on every refresh, and fire a **browser notification** (plus a status banner) when
hit. Fully client-side — no backend or polling service.

### Overall verdict (multi-signal)

A weighted **bull/bear verdict** that combines five technical signals — chart pattern, RSI, MACD, trend,
volume — into one call (Strong Sell … Strong Buy) with a gauge, an **agreement %**, and a per-signal
contribution breakdown. The weighting depends on the risk profile (conservative leans on trend/volume,
aggressive on pattern/momentum), configurable in the box and defined in
[app/models/risk.py](app/models/risk.py) `SIGNAL_WEIGHTS`. Pure math ([app/tools/verdict.py](app/tools/verdict.py),
`GET /verdict`) — no LLM, refreshes every poll.

### Market structure & chart analysis

The chart now overlays **support/resistance levels** (clustered swing pivots, labelled with touch count) and a
**volume histogram**. A **Market Structure** box summarises:
- **Trend structure** — uptrend (HH+HL) / downtrend (LH+LL) / sideways
- **Trend strength** — ADX (>25 trending, <18 choppy)
- **Volatility** — ATR (₹ and % per day) and an expected daily range (price ± ATR)
- **Volume** — today vs. 20-day average (high/normal/low), as move-confirmation

It also prints a plain-English note (e.g. "choppy/rangebound — patterns less reliable; low volume — moves
lack conviction"). All computed in plain pandas in [app/tools/technicals.py](app/tools/technicals.py) and returned
via `/candles`.

### Risk & position sizing

Inside the Pattern box, a risk panel turns the detected pattern into a concrete, personalised plan:
enter capital (defaults to your Playground wallet) and risk %, and it computes **shares to buy**,
**risk:reward ratio** (color-coded), **capital deployed**, **max loss if the stop hits**, and
**potential gain at target**. Pure math — no extra data calls.

### Pattern backtest

The Pattern box also shows how the *currently-detected pattern* played out on the stock's own history
([app/tools/backtest.py](app/tools/backtest.py), `GET /pattern-backtest`): it slides the detector over the
maximum daily history, counts prior occurrences, and reports **how often price reached the measured
target** and the **average move after**, with an honest small-sample warning. Cached 1 hour. Educational —
past behaviour doesn't guarantee future results.

### Top Movers panel

A panel at the top of the dashboard shows **Top 5 being bought** (biggest gainers) and
**Top 5 being sold** (biggest losers) across the **Nifty 200**, with click-to-load.

> ⚠️ This is a *price-change proxy* for buy/sell pressure — **not** real broker order-flow data
> (that requires a paid exchange/broker feed). It ranks stocks by today's % price move.

Served by `GET /movers` ([app/tools/movers.py](app/tools/movers.py)): it batch-downloads the Nifty 200 in
chunks (to respect Yahoo's rate limits), computes % change from the last two closes, and **caches the
result for ~5 minutes** with a stale-fallback if Yahoo throttles. The constituent list lives at
`app/data/nifty200.json` and is regenerated by `scripts/refresh_symbols.py`.

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
- **Inference grading** — when you place a trade, the dashboard's pattern signal + target for that symbol
  is captured (a free `/pattern` call) and shown on the open position. On square-off, the trade is graded
  4 ways: **✓ correct** (followed the signal and profited), **✗ wrong** (followed it but lost — the read
  failed), **! ignored** (signal was right, you traded against it), **⚠ lucky** (profited against the
  signal). Each closed trade gets a badge in History, plus a **scorecard** of your overall inference
  accuracy — so you learn where your judgment (or the dashboard's) went wrong.

### Pattern engine (`app/tools/patterns.py`)

Pure rule-based geometry — no LLM. Finds swing pivots, then matches the core set:
**double top/bottom, head & shoulders (+ inverse), ascending/descending/symmetrical
triangle, support/resistance breakout**. Each match computes a textbook **measured-move
target** and a confidence from how cleanly the geometry fits. Patterns whose target has
already been reached are flagged and down-weighted.
