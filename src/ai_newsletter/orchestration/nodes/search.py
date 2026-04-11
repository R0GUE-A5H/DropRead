import requests
from langchain.tools import tool

from src.ai_newsletter.core.config import get_settings
from src.ai_newsletter.orchestration.states import GraphState
from src.ai_newsletter.utils.shared import update_status

settings = get_settings()


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
    except requests.RequestException:
        # print(f"search_tool: network/API error: {exc}")
        return []

    try:
        data = response.json()
    except ValueError:
        print("search_tool: response was not valid JSON")
        return []

    search_links = [item["link"] for item in data.get("organic", []) if "link" in item]
    return search_links


async def node_tool_search(state: GraphState):
    # print(
    #     f"-------Starting Serper API search with query: {state['generated_query']}------"
    # )
    await update_status(state, "running", "Crawling Internet...")
    search_links = search_tool.invoke({"query": state["generated_query"]})
    return {"search_links": search_links}
