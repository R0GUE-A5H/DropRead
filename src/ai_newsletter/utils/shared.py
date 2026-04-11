from src.ai_newsletter.orchestration.state_manager import update_digest_status


def estimate_read_time(content: str) -> int:
    words = len(content.split())
    return max(1, round(words / 200))


async def update_status(state: dict, status: str, current_step: str | None = None):
    await update_digest_status(state["digest_id"], status, current_step)
