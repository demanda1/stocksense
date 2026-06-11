#Pydantic models force the LLM to return clean, predictable data — the same discipline as a Java DTO
from pydantic import BaseModel, Field
from typing import Literal

class FundamentalView(BaseModel):
    ticker: str
    signal: Literal["bullish", "neutral", "bearish"]
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    key_metrics: dict

