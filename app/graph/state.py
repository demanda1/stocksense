from typing import TypedDict, Optional
from app.models.schemas import FundamentalView
class AnalysisState(TypedDict, total=False):
    ticker: str
    risk_profile: str
    fundamental: Optional[FundamentalView]
    technical: Optional[FundamentalView]
    sentiment: Optional[FundamentalView]
    recommendation: Optional[dict]