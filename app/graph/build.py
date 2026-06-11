from langgraph.graph import StateGraph, START, END
from app.graph.state import AnalysisState
from app.graph.nodes import fundamental_node, technical_node, sentiment_node, advisor_node

def build_graph():
    g = StateGraph(AnalysisState)
    g.add_node("fundamental", fundamental_node)
    g.add_node("technical", technical_node)
    g.add_node("sentiment", sentiment_node)
    # All three run from START (parallel fan-out)
    g.add_edge(START, "fundamental")
    g.add_edge(START, "technical")
    g.add_edge(START, "sentiment")
    # conceptual shape of the edits:
    g.add_node("advisor", advisor_node)
    g.add_edge("fundamental", "advisor")
    g.add_edge("technical", "advisor")
    g.add_edge("sentiment", "advisor")
    g.add_edge("advisor", END)
    return g.compile()
