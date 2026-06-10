from src.ai_newsletter.core.config import get_settings

settings = get_settings()


async def run_pipeline(topic: str, digest_id: str) -> dict:
    from src.ai_newsletter.orchestration.graph import pipeline

    config = {"configurable": {"thread_id": digest_id}}

    return await pipeline.ainvoke(
        {
            "topic": topic,
            "digest_id": digest_id,
            "generated_query": "",
            "search_links": [],
            "state_result_page": {},
            "final_search_links": [],
            "synthesis_summary": "",
        },
        config=config,
    )
