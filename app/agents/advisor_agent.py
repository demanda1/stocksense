from langchain_groq import ChatGroq
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Union
from app.config import DEFAULT_MODEL
from app.models.risk import RISK_WEIGHTS

class Recommendation(BaseModel):
    ticker: str
    action: Literal["buy", "hold", "sell"]
    # Coerce string/float confidence (LLMs are inconsistent) to a clamped int.
    confidence: Union[int, float, str] = Field(default=50)
    reasoning: str
    risk_profile: str = "moderate"

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            return 50
        return max(0, min(100, n))

llm = ChatGroq(model=DEFAULT_MODEL, temperature=0)
structured_llm = llm.with_structured_output(Recommendation)

PROMPT = """You are a portfolio advisor for a {risk} investor.
Weigh these three analyses using the importance weights, then give a final
buy / hold / sell call with clear reasoning a beginner can follow.

Weights: {weights}
Fundamental: {f}
Technical: {t}
Sentiment: {s}

Return the structured recommendation."""

def advise(state) -> Recommendation:
    risk = state.get("risk_profile", "moderate")
    msg = PROMPT.format(
        risk=risk, weights=RISK_WEIGHTS[risk],
        f=state["fundamental"].model_dump(),
        t=state["technical"].model_dump(),
        s=state["sentiment"].model_dump(),
    )
    # LLM structured output is occasionally flaky; retry once before giving up.
    try:
        return structured_llm.invoke(msg)
    except Exception:
        return structured_llm.invoke(msg)