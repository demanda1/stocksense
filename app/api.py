from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.graph.build import build_graph
from app.agents.advisor_agent import advise
from app.observability import langfuse_handler

app = FastAPI(title="StockSense AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"],allow_methods=["*"], allow_headers=["*"])
graph = build_graph()

class Query(BaseModel):
    ticker: str
    risk: str = "moderate"


@app.post("/analyze")
def analyze(q: Query):
    state = graph.invoke({"ticker": q.ticker.upper()},
    config={"callbacks": [langfuse_handler]})
    rec = advise(state)
    return {
        "recommendation": rec.model_dump(),
        "fundamental": state["fundamental"].model_dump(),
        "technical": state["technical"].model_dump(),
        "sentiment": state["sentiment"].model_dump(),
    }