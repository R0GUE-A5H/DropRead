import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    Request,
    Response,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import src.ai_newsletter.models.models as models
from src.ai_newsletter.core.config import get_settings
from src.ai_newsletter.database.engine import get_db
from src.ai_newsletter.services.cache import get_cached_digest
from src.ai_newsletter.services.digest import create_digest
from src.ai_newsletter.utils.limiter import limiter

settings = get_settings()
router = APIRouter()
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

logger = logging.getLogger(__name__)


@router.post("/init")
@limiter.limit("5/minute")
async def init_pipeline(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    topic: str = Form(..., min_length=3, max_length=200),
):
    user = request.session.get("user")
    if not user:
        response = Response(status_code=204)
        response.headers["HX-Trigger"] = "open-auth-modal"
        return response

    topic = topic.strip()
    logger.info(f">>> INIT called for topic: {topic}")

    def existing_response(item):
        r = templates.TemplateResponse(
            request=request,
            name="partials/status_badge.html",
            context={"request": request, "item": item},
        )
        r.headers["HX-Reswap"] = "outerHTML"
        r.headers["HX-Retarget"] = f"#row-{item.id}"
        return r

    def new_response(item):
        r = templates.TemplateResponse(
            request=request,
            name="partials/status_badge.html",
            context={"request": request, "item": item},
        )
        r.headers["HX-Reswap"] = "afterbegin"
        r.headers["HX-Retarget"] = "#digest-tbody"
        return r

    result = await db.execute(
        select(models.Digest)
        .where(
            models.Digest.user_id == uuid.UUID(user["id"]),
            models.Digest.title == topic,
        )
        .order_by(models.Digest.created_at.desc())
    )
    digest = result.scalar_one_or_none()

    if digest:
        if digest.status == "ready":
            logger.info(f">>> Already ready: {digest.id}")
            return existing_response(digest)

        if digest.status == "running":
            logger.info(f">>> Already running: {digest.id}")
            return existing_response(digest)
        logger.info(f">>> Resuming failed digest: {digest.id}")
        await db.execute(
            update(models.Digest)
            .where(models.Digest.id == digest.id)
            .values(
                status="running",
                current_step="🔄 Resuming from last checkpoint...",
                content="",
            )
        )
        await db.commit()
        await db.refresh(digest)
        background_tasks.add_task(create_digest, topic, str(digest.id))
        return existing_response(digest)

    cached = await get_cached_digest(topic)
    if cached:
        logger.info(f">>> Cache hit ({cached['similarity']}) for: {topic}")
        source_result = await db.execute(
            select(models.Digest).where(
                models.Digest.id == uuid.UUID(cached["digest_id"])
            )
        )
        source_digest = source_result.scalar_one_or_none()

        if source_digest:
            new_digest = models.Digest(
                content=source_digest.content,
                extra_data=source_digest.extra_data,
                user_id=uuid.UUID(user["id"]),
                title=topic,
                status="ready",
            )
            db.add(new_digest)
            await db.commit()
            await db.refresh(new_digest)
            logger.info(f">>> Created from cache: {new_digest.id}")
            return new_response(new_digest)

    logger.info(">>> Creating NEW digest")
    digest = models.Digest(
        content="",
        user_id=uuid.UUID(user["id"]),
        title=topic,
        status="running",
    )
    db.add(digest)
    await db.commit()
    await db.refresh(digest)
    background_tasks.add_task(create_digest, topic, str(digest.id))
    return new_response(digest)


# @router.post("/scheduler/run")
# async def trigger_scheduler_run(
#     request: Request,
#     x_scheduler_secret: Annotated[str | None, Header()] = None,
# ):
#     if x_scheduler_secret != settings.SECRET_KEY:
#         raise HTTPException(status_code=403, detail="Forbidden")
#     await run_scheduled_digests()
#     return {"status": "ok"}
