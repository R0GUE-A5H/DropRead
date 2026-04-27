import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_newsletter.database.engine import async_session
from src.ai_newsletter.models.models import Digest
from src.ai_newsletter.orchestration.runner import run_pipeline

logging.basicConfig(level=logging.INFO)


async def create_digest(topic: str, digest_id: str):
    try:
        final_state = await run_pipeline(topic, digest_id)

        logger = logging.getLogger(__name__)
        logger.info(
            f"Pipeline complete. Pages: {len(final_state.get('state_result_page', {}))}"
        )
        logger.info(f"Summary length: {len(final_state.get('synthesis_summary', ''))}")

        async with async_session() as db:
            await db.execute(
                update(Digest)
                .where(Digest.id == uuid.UUID(digest_id))
                .values(
                    content=final_state["synthesis_summary"],
                    status="ready",
                    extra_data=[
                        {"url": url, "title": page_data["title"]}
                        for url, page_data in final_state["state_result_page"].items()
                    ],
                )
            )
            await db.commit()
    except Exception as e:
        async with async_session() as db:
            await db.execute(
                update(Digest)
                .where(Digest.id == uuid.UUID(digest_id))
                .values(status="failed", current_step=str(e)[:200])
            )
            await db.commit()


async def get_digests(db: AsyncSession, user_id: str):

    stmt = select(Digest).where(Digest.user_id == uuid.UUID(user_id))
    result = await db.execute(stmt)
    digests = result.scalars().all()

    return digests


async def get_digest_by_id(
    db: AsyncSession, digest_id: uuid.UUID, user_id: uuid.UUID
) -> Digest | None:
    stmt = select(Digest).where(Digest.id == digest_id).where(Digest.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
