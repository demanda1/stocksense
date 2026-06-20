"""Plain-English explanation of a detected chart pattern.

Turns the raw pattern numbers (current price, breakout level, target, move %)
into a beginner-friendly paragraph. Uses Groq when GROQ_API_KEY is set, and
always falls back to a rule-based template so the dashboard works offline.
"""
from __future__ import annotations

from app.config import GROQ_API_KEY, DEFAULT_MODEL

_PROMPT = """You are explaining a technical-analysis chart pattern to a complete \
beginner who does not know trading jargon.

Pattern: {pattern}
Signal: {signal}
Current price: ₹{current}
Breakout/neckline level: ₹{breakout}
Measured target: ₹{target}
Projected move: {move}%

Write ONE short paragraph (3-4 sentences, no headings, no bullet points) in \
plain English that explains what these specific numbers mean for this stock. \
Describe what the pattern suggests about buyers vs sellers, what needs to happen \
at the breakout level for the move to confirm, and what the target implies. \
End with a brief note that the reader should wait for a confirmed breakout. \
Do not give financial advice or tell them to buy/sell. Do not repeat the raw \
numbers as a list."""


def _template(p: dict) -> str:
    """Rule-based fallback explanation built from the numbers."""
    pattern = p.get("pattern", "pattern")
    signal = p.get("signal", "neutral")
    cur = p.get("current_price")
    brk = p.get("breakout_level")
    tgt = p.get("target")
    move = p.get("projected_move_pct")

    if signal == "bullish":
        pressure = ("This pattern suggests sellers are losing control and buyers "
                    "are starting to step in.")
        confirm = (
            f"If the price breaks above the ₹{brk} level on strong trading volume, "
            f"it would confirm a possible upward trend toward roughly ₹{tgt}"
            if brk is not None and tgt is not None else
            "A confirmed breakout above the key level would support the bullish case.")
    elif signal == "bearish":
        pressure = ("This pattern suggests buyers are losing control and sellers "
                    "are starting to take over.")
        confirm = (
            f"If the price breaks below the ₹{brk} level on strong trading volume, "
            f"it would confirm a possible downward move toward roughly ₹{tgt}"
            if brk is not None and tgt is not None else
            "A confirmed breakdown below the key level would support the bearish case.")
    else:
        pressure = ("This pattern is neutral — buyers and sellers are roughly "
                    "balanced for now.")
        confirm = "Watch the key level to see which side takes control next."

    move_txt = (f" — a move of about {move}% from the current price of ₹{cur}."
                if move is not None and cur is not None else ".")

    return (f"{pressure} {confirm}{move_txt} "
            "Because patterns can fail, it is important to wait for a confirmed "
            "breakout past that level (ideally with higher-than-usual volume) "
            "rather than acting early.")


def _llm_explain(p: dict) -> str | None:
    """Try Groq; return None on any failure so the caller can fall back."""
    if not GROQ_API_KEY:
        return None
    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=DEFAULT_MODEL, temperature=0.3)
        msg = _PROMPT.format(
            pattern=p.get("pattern"), signal=p.get("signal"),
            current=p.get("current_price"), breakout=p.get("breakout_level"),
            target=p.get("target"), move=p.get("projected_move_pct"),
        )
        text = llm.invoke(msg).content
        return text.strip() if text else None
    except Exception:
        return None


def explain_pattern(p: dict) -> dict:
    """Return {explanation, source} for a pattern result.

    source is 'ai' when the LLM produced it, else 'template'.
    """
    if not p or p.get("target") is None:
        return {
            "explanation": ("No clear chart pattern was detected, so there is no "
                            "measured target to explain right now. Try another "
                            "timeframe or check back as new price data forms."),
            "source": "template",
        }
    ai = _llm_explain(p)
    if ai:
        return {"explanation": ai, "source": "ai"}
    return {"explanation": _template(p), "source": "template"}
