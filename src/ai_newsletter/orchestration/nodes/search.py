import logging
import httpx
from src.ai_newsletter.core.config import get_settings
from src.ai_newsletter.orchestration.states import GraphState
from src.ai_newsletter.utils.shared import update_status

settings = get_settings()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def node_tool_search(state: GraphState):
    await update_status(state, "running", "Searching Internet...")
    query = state["generated_query"]
    logger.info(f"Search query: {query}")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": settings.serper_page_num},
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        data = resp.json()

    search_links = []
    search_snippets = {}
    for item in data.get("organic", []):
        url = item.get("link")
        if not url:
            continue
        search_links.append(url)
        search_snippets[url] = item.get("snippet", "")

    logger.info(f"Search found {len(search_links)} links")
    return {"search_links": search_links, "search_snippets": search_snippets}
