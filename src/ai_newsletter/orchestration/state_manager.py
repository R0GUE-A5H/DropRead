import uuid

from sqlalchemy import update

from src.ai_newsletter.database.engine import async_session


async def update_digest_status(
    digest_id: str, status: str, current_step: str | None = None
):
    from src.ai_newsletter.models.models import Digest

    values = {"status": status}
    if current_step is not None:
        values["current_step"] = current_step.strip()

    async with async_session() as db:
        await db.execute(
            update(Digest).where(Digest.id == uuid.UUID(digest_id)).values(**values)
        )
        await db.commit()
