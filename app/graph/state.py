from typing import TypedDict, Optional
from app.models.schemas import FundamentalView
class AnalysisState(TypedDict):
    ticker: str
    fundamental: Optional[FundamentalView]
    technical: Optional[FundamentalView]
    sentiment: Optional[FundamentalView]
    recommendation: Optional[dict]