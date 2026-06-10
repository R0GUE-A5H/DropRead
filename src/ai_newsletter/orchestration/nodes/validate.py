import json

# import os
from src.ai_newsletter.core.llm import llm
from src.ai_newsletter.orchestration.prompts import synth_prompt
from src.ai_newsletter.orchestration.states import GraphState, ValidatorAgent
from src.ai_newsletter.utils.shared import update_status


async def validation_node(state: GraphState):
    # print("-------Starting validation of crawled content------")
    # if os.getenv("FORCE_FAIL_RESUME_TEST") == "1":
    #     raise RuntimeError("Simulated failure AFTER crawl checkpoint committed")
    crawled_pages_data = state.get("state_result_page", {})
    if not crawled_pages_data:
        # print("Nothing to validate")
        await update_status(state, "running", "Nothing to validate.")
        return state
    await update_status(state, "running", "Validating content...")
    truncated_result = {
        url: page["content"][:300].replace("\n", " ").strip() + "..."
        for url, page in crawled_pages_data.items()
    }

    structured_validator = llm.with_structured_output(ValidatorAgent)

    validation_result = await structured_validator.ainvoke(
        synth_prompt.format(
            original_topic=state["topic"],
            page_content=json.dumps(truncated_result, indent=2),
        )
    )
    # print(f"Validation Result: {validation_result.final_url}")

    return {
        "final_search_links": validation_result.final_url,
    }
