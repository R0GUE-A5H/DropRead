import logging
import uuid

from sqlalchemy import select

from src.ai_newsletter.core.llm import llm
from src.ai_newsletter.database.engine import async_session
from src.ai_newsletter.models.models import Digest
from src.ai_newsletter.orchestration.prompts import summarization_prompt
from src.ai_newsletter.orchestration.state_manager import update_digest_status
from src.ai_newsletter.orchestration.states import GraphState
from src.ai_newsletter.utils.shared import update_status

logger = logging.getLogger(__name__)


async def synthesis_node(state: GraphState):
    async with async_session() as db:
        digest_exists = await db.execute(
            select(Digest.id).where(Digest.id == uuid.UUID(state["digest_id"]))
        )
        if not digest_exists.scalar_one_or_none():
            logger.warning(
                f"Kill switch: Digest {state['digest_id']} deleted. Halting synthesis."
            )
            raise RuntimeError("Digest deleted by user. Halting to save LLM tokens.")

    crawled_data = state.get("state_result_page", {})

    validated_list = [
        crawled_data[url]["content"][:5000].replace("\n", " ").strip() + "..."
        for url in state["final_search_links"]
        if url in crawled_data
    ]

    if not validated_list:
        await update_status(state, "failed", "No content to synthesize")
        await update_digest_status(
            state["digest_id"], "failed", current_step="No valid sources found"
        )
        return {"synthesis_summary": "No content available"}

    synth_chain = summarization_prompt | llm
    synthesized_summary = await synth_chain.ainvoke(
        {
            "original_topic": state["topic"],
            "validated_contents": "\n\n".join(validated_list),
        }
    )

    await update_status(state, "running", "Synthesis complete.")
    return {
        "synthesis_summary": synthesized_summary.content,
    }
