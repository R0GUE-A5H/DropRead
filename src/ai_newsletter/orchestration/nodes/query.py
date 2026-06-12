from src.ai_newsletter.core.llm import llm
from src.ai_newsletter.orchestration.prompts import system_prompt_serper
from src.ai_newsletter.orchestration.states import GraphState
from src.ai_newsletter.utils.shared import update_status


async def generate_search_query(state: GraphState) -> dict:
    await update_status(state, "running", "Generating search query...")
    chain = system_prompt_serper | llm
    response = await chain.ainvoke({"user_topic": state["topic"]})
    return {"generated_query": response.content}
