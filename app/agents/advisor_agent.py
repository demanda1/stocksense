from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from typing import Literal
from app.config import DEFAULT_MODEL
from app.models.risk import RISK_WEIGHTS

class Recommendation(BaseModel):
    ticker: str
    action: Literal["buy", "hold", "sell"]
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    risk_profile: str

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
    return structured_llm.invoke(PROMPT.format(
    risk=risk, weights=RISK_WEIGHTS[risk],
    f=state["fundamental"].model_dump(),
    t=state["technical"].model_dump(),
    s=state["sentiment"].model_dump(),
    ))