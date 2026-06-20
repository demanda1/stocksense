#Pydantic models force the LLM to return clean, predictable data — the same discipline as a Java DTO
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Union

class FundamentalView(BaseModel):
    ticker: str
    signal: Literal["bullish", "neutral", "bearish"]
    # LLMs sometimes emit confidence as a string ("60") or float (60.0).
    # Accept those and coerce to a clamped int so structured output never fails.
    confidence: Union[int, float, str] = Field(default=50)
    reasoning: str
    key_metrics: dict = Field(default_factory=dict)

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            return 50
        return max(0, min(100, n))

