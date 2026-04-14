import uuid

from fastapi import HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_newsletter.database.schemas import EmailInfoSave
from src.ai_newsletter.models.models import Digest


async def save_digest_mail(
    request: Request,
    digest_id: uuid.UUID,
    emailInfoSave: EmailInfoSave,
    db: AsyncSession,
):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.execute(
        update(Digest)
        .where(Digest.id == digest_id)
        .values(
            auto_digest=True,
            delivery_day=emailInfoSave.day,
            delivery_time=emailInfoSave.time,
        )
    )

    await db.commit()

    return {"detail": "Subscribed"}


async def unsubscribe_digest_mail(
    request: Request,
    digest_id: uuid.UUID,
    db: AsyncSession,
):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.execute(
        update(Digest).where(Digest.id == digest_id).values(auto_digest=False)
    )

    await db.commit()

    return {"detail": "Unsubscribed"}


async def get_subscription_status(
    request: Request,
    digest_id: uuid.UUID,
    db: AsyncSession,
):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(select(Digest).where(Digest.id == digest_id))
    digest = result.scalar_one_or_none()

    if not digest:
        raise HTTPException(status_code=404, detail="Digest not found")

    return {
        "subscribed": digest.auto_digest,
        "day": digest.delivery_day,
        "time": digest.delivery_time,
    }
