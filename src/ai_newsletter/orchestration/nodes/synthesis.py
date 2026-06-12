from src.ai_newsletter.core.llm import llm
from src.ai_newsletter.orchestration.prompts import summarization_prompt
from src.ai_newsletter.orchestration.state_manager import update_digest_status
from src.ai_newsletter.orchestration.states import GraphState
from src.ai_newsletter.utils.shared import update_status


async def synthesis_node(state: GraphState):
    # print("-------Starting synthesis of validated content------")

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
    # print("Synthesis completed. Generated newsletter summary.")
    await update_status(state, "running", "Synthesis complete.")
    return {
        "synthesis_summary": synthesized_summary.content,
    }
