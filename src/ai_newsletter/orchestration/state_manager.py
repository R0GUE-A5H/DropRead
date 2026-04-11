import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.ai_newsletter.core.config import get_settings

settings = get_settings()


async def update_digest_status(
    digest_id: str, status: str, current_step: str | None = None
):
    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    from src.ai_newsletter.models.models import Digest

    values = {"status": status}
    if current_step is not None:
        values["current_step"] = current_step.strip()

    async with AsyncSession() as db:
        await db.execute(
            update(Digest).where(Digest.id == uuid.UUID(digest_id)).values(**values)
        )
        await db.commit()
    await engine.dispose()
