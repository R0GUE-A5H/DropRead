from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class GraphState(TypedDict):
    topic: str
    generated_query: str
    search_links: list[str]
    state_result_page: dict
    final_search_links: list[str]
    synthesis_summary: str
    digest_id: str


class SearchQuery(BaseModel):
    topic: str = Field(
        "A SINGLE-LINE combined advanced search query. No newlines. No lists. No explanations."
    )


class ValidatorAgent(BaseModel):
    final_url: list[str] = Field(
        description="A list of URLs that are relevant to the original topic. The URLs should be directly related to the topic and provide substantial information about it."
    )
