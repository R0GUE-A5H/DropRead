from langgraph.graph import END, START, StateGraph

from src.ai_newsletter.orchestration.nodes.crawl import node_web_crawl
from src.ai_newsletter.orchestration.nodes.query import generate_search_query
from src.ai_newsletter.orchestration.nodes.search import node_tool_search
from src.ai_newsletter.orchestration.nodes.synthesis import synthesis_node
from src.ai_newsletter.orchestration.nodes.validate import validation_node
from src.ai_newsletter.orchestration.states import GraphState


def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("search_query", generate_search_query)
    graph.add_node("search_execution", node_tool_search)
    graph.add_node("web_crawl", node_web_crawl)
    graph.add_node("validation", validation_node)
    graph.add_node("synthesis", synthesis_node)

    graph.add_edge(START, "search_query")
    graph.add_edge("search_query", "search_execution")
    graph.add_edge("search_execution", "web_crawl")
    graph.add_edge("web_crawl", "validation")
    graph.add_edge("validation", "synthesis")
    graph.add_edge("synthesis", END)

    return graph.compile()


pipeline = build_graph()
