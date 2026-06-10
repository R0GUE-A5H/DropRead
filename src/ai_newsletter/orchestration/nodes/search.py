import logging

import requests
from langchain.tools import tool

from src.ai_newsletter.core.config import get_settings
from src.ai_newsletter.orchestration.states import GraphState
from src.ai_newsletter.utils.shared import update_status

settings = get_settings()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@tool
def search_tool(query: str):
    """
    Docstring for search_tool
    Calls with SERPER DEV API to get search results it returns raw hyperlinks

    :param query: Description
    :type query: str
    """
    serper_url = "https://google.serper.dev/search"
    payload = {"q": query, "num": settings.serper_page_num}
    headers = {"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"}

    try:
        response = requests.post(serper_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"search_tool: network/API error: {exc}")
        return []

    try:
        data = response.json()
    except ValueError:
        print("search_tool: response was not valid JSON")
        return []

    search_links = []
    search_snippets = {}

    for item in data.get("organic", []):
        url = item.get("link")

        if not url:
            continue
        search_links.append(url)
        search_snippets[url] = item.get("snippet", "")

    return {"search_links": search_links, "search_snippets": search_snippets}


async def node_tool_search(state: GraphState):
    await update_status(state, "running", "Crawling Internet...")
    logger.info(f"Search query: {state.get('generated_query')}")

    result = search_tool.invoke({"query": state["generated_query"]})

    logger.info(f"Search raw result type: {type(result)}")
    logger.info(f"Search raw result: {result}")

    return {
        "search_links": result["search_links"],
        "search_snippets": result["search_snippets"],
    }
