from app.agents.fundamental_agent import analyze_fundamentals
from app.agents.technical_agent import analyze_technicals
from app.agents.sentiment_agent import analyze_sentiment
from app.agents.advisor_agent import advise
def fundamental_node(state):
    return {"fundamental": analyze_fundamentals(state["ticker"])}

def technical_node(state):
    return {"technical": analyze_technicals(state["ticker"])}

def sentiment_node(state):
    return {"sentiment": analyze_sentiment(state["ticker"])}

def advisor_node(state):
    return {"sentiment": advise(state)}