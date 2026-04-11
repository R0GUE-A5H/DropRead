import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.ai_newsletter.database.engine import SQLDATABASE_URL
from src.ai_newsletter.models.models import Digest
from src.ai_newsletter.orchestration.runner import run_pipeline


async def create_digest(topic: str, digest_id: str):
    engine = create_async_engine(SQLDATABASE_URL)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    try:
        final_state = await run_pipeline(topic, digest_id)

        async with AsyncSession() as db:
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
    finally:
        await engine.dispose()


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
