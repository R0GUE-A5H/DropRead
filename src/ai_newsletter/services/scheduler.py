import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from src.ai_newsletter.database.engine import async_session
from src.ai_newsletter.models.models import Digest, User
from src.ai_newsletter.services.digest import create_digest
from src.ai_newsletter.services.digest_email import send_digest_email

logger = logging.getLogger(__name__)
DAYS = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def next_delivery_dt(delivery_day: str, delivery_time: str) -> datetime:
    now = datetime.now(UTC)
    target_weekday = DAYS.get(delivery_day, 0)
    hour, minute = map(int, delivery_time.split(":"))

    days_ahead = (target_weekday - now.weekday()) % 7

    if days_ahead == 0 and (now.hour, now.minute) >= (hour, minute):
        days_ahead = 7

    next_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    next_dt += timedelta(days=days_ahead)

    return next_dt.replace(tzinfo=None)


async def run_scheduled_digests():
    now = datetime.utcnow()
    logger.info(f"Scheduler running at {now}")

    async with async_session() as db:
        result = await db.execute(
            select(Digest, User)
            .join(User, Digest.user_id == User.id)
            .where(
                Digest.auto_digest.is_(True),
                Digest.next_delivery <= now,
                Digest.status == "ready",
            )
        )
        # extract everything before session closes
        due = [
            {
                "id": d.id,
                "title": d.title,
                "delivery_day": d.delivery_day,
                "delivery_time": d.delivery_time,
                "email": u.email,
            }
            for d, u in result.all()
        ]

    logger.info(f"Found {len(due)} digests due")

    for item in due:
        try:
            await create_digest(item["title"], str(item["id"]), skip_cache=True)

            async with async_session() as db:
                result = await db.execute(select(Digest).where(Digest.id == item["id"]))
                fresh = result.scalar_one_or_none()

            if not fresh or fresh.status != "ready":
                logger.error(f"Digest {item['id']} not ready after pipeline, skipping")
                continue

            await send_digest_email(
                to_email=item["email"],
                topic=fresh.title,
                content=fresh.content,
                digest_id=str(fresh.id),
            )

            async with async_session() as db:
                await db.execute(
                    update(Digest)
                    .where(Digest.id == item["id"])
                    .values(
                        next_delivery=next_delivery_dt(
                            item["delivery_day"], item["delivery_time"]
                        )
                    )
                )
                await db.commit()

        except Exception as e:
            logger.error(f"Scheduler failed for {item['id']}: {e}")
            continue
