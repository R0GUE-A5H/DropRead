from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import torch
from sentence_transformers import CrossEncoder

from src.ai_newsletter.utils.shared import update_status

if TYPE_CHECKING:
    from src.ai_newsletter.orchestration.states import GraphState

logger = logging.getLogger(__name__)
MAX_CONTENT_CHARS = 1200
TOP_N = 6

_reranker: CrossEncoder | None = None


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        logger.info("Loading reranker model...")
        _reranker = CrossEncoder("BAAI/bge-reranker-base", max_length=512, device="cpu")
        torch.set_num_threads(2)
        logger.info("Reranker model loaded.")
    return _reranker


async def rerank_node(state: GraphState):
    await update_status(state, "running", "Ranking sources by relevance...")
    topic = state.get("topic", "")
    pages = state.get("state_result_page", {})

    if not pages:
        return {"final_search_links": [], "state_result_page": {}}

    pairs = []
    urls = []

    for url, data in pages.items():
        content = (data.get("content") or "")[:MAX_CONTENT_CHARS]
        title = data.get("title") or ""
        doc_text = f"{title}\n{content}".strip()
        pairs.append((topic, doc_text))
        urls.append(url)

    def _score():
        return _get_reranker().predict(pairs)

    loop = asyncio.get_running_loop()
    scores = await loop.run_in_executor(None, _reranker.predict, pairs)

    scored_urls = sorted(
        zip(urls, scores, strict=True), key=lambda x: x[1], reverse=True
    )
    top_urls = [url for url, score in scored_urls[:TOP_N]]
    ranked_pages = {url: pages[url] for url in top_urls if url in pages}

    logger.info(f"Reranked {len(pages)} sources - kept top {len(ranked_pages)}")
    return {
        "final_search_links": top_urls,
        "state_result_page": ranked_pages,
    }
