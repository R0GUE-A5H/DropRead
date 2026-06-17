import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_newsletter.database.engine import async_session
from src.ai_newsletter.models.models import Digest
from src.ai_newsletter.orchestration.runner import run_pipeline
from src.ai_newsletter.services.cache import get_cached_digest, save_to_cache

logging.basicConfig(level=logging.INFO)


async def create_digest(topic: str, digest_id: str, skip_cache: bool = False):
    logger = logging.getLogger(__name__)
    cached = None
    if not skip_cache:
        cached = await get_cached_digest(topic)
    if cached:
        async with async_session() as db:
            await db.execute(
                update(Digest)
                .where(Digest.id == uuid.UUID(digest_id))
                .values(
                    content=cached["content"],
                    status="ready",
                    extra_data=cached["extra_data"],
                    current_step=f"⚡ Cached from: {cached['cached_topic']}",
                )
            )
            await db.commit()
        return
    try:
        final_state = await run_pipeline(topic, digest_id)
        logger.info(f">>> BG TASK SUCCESS: {digest_id}")
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
        await save_to_cache(topic, digest_id)

    except Exception as e:
        logger.error(f">>> BG TASK FAILED: {digest_id} - {e}", exc_info=True)
        async with async_session() as db:
            await db.execute(
                update(Digest)
                .where(Digest.id == uuid.UUID(digest_id))
                .values(status="failed", current_step=str(e)[:200])
            )
            await db.commit()


async def get_digests(db: AsyncSession, user_id: str):

    stmt = (
        select(Digest)
        .where(Digest.user_id == uuid.UUID(user_id))
        .order_by(Digest.created_at.desc())
    )
    result = await db.execute(stmt)
    digests = result.scalars().all()

    return digests


async def get_digest_by_id(
    db: AsyncSession, digest_id: uuid.UUID, user_id: uuid.UUID
) -> Digest | None:
    stmt = select(Digest).where(Digest.id == digest_id).where(Digest.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_digests_per_topic(db: AsyncSession, user_id: str):
    stmt = (
        select(Digest)
        .where(Digest.user_id == uuid.UUID(user_id))
        .distinct(Digest.title)
        .order_by(Digest.title, Digest.created_at.asc())
    )
    result = await db.execute(stmt)
    digests = result.scalars().all()

    return sorted(digests, key=lambda d: d.created_at, reverse=True)


async def get_past_digests_by_topic(
    db: AsyncSession, user_id: str, topic: str, current_digest_id: uuid.UUID
):
    stmt = (
        select(Digest)
        .where(
            Digest.user_id == uuid.UUID(user_id),
            Digest.title == topic,
            Digest.id != current_digest_id,
            Digest.status == "ready",
            Digest.current_step == "Emailed",
        )
        .order_by(Digest.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
