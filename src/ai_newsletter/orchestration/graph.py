import psycopg_pool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg.rows import dict_row

from src.ai_newsletter.core.config import get_settings
from src.ai_newsletter.orchestration.nodes.crawl import node_web_crawl
from src.ai_newsletter.orchestration.nodes.query import generate_search_query
from src.ai_newsletter.orchestration.nodes.rerank import rerank_node
from src.ai_newsletter.orchestration.nodes.search import node_tool_search
from src.ai_newsletter.orchestration.nodes.synthesis import synthesis_node
from src.ai_newsletter.orchestration.nodes.validate import validation_node
from src.ai_newsletter.orchestration.states import GraphState

settings = get_settings()
DB_URI = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

pool = psycopg_pool.AsyncConnectionPool(
    conninfo=DB_URI,
    max_size=20,
    kwargs={"autocommit": True, "row_factory": dict_row},
    open=False,
)

checkpointer: AsyncPostgresSaver | None = None
pipeline = None


def build_graph(cp: AsyncPostgresSaver):
    graph = StateGraph(GraphState)

    graph.add_node("search_query", generate_search_query)
    graph.add_node("search_execution", node_tool_search)
    graph.add_node("web_crawl", node_web_crawl)
    graph.add_node("validation", validation_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("synthesis", synthesis_node)

    graph.add_edge(START, "search_query")
    graph.add_edge("search_query", "search_execution")
    graph.add_edge("search_execution", "web_crawl")
    graph.add_edge("web_crawl", "validation")
    graph.add_edge("validation", "rerank")
    graph.add_edge("rerank", "synthesis")
    graph.add_edge("synthesis", END)

    return graph.compile(checkpointer=cp)


async def init_pipeline():
    """Call this once inside the lifespan, after the event loop is running."""
    global checkpointer, pipeline
    # await pool.open()
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    pipeline = build_graph(checkpointer)


async def close_pipeline():
    global pool
    await pool.close()
