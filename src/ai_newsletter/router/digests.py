import json
import re
import uuid
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_newsletter.core.config import get_settings
from src.ai_newsletter.database.engine import get_db
from src.ai_newsletter.database.schemas import DigestRead, EmailInfoSave
from src.ai_newsletter.models import models
from src.ai_newsletter.models.models import Digest
from src.ai_newsletter.services.auth import get_current_user
from src.ai_newsletter.services.digest_mail import (
    get_subscription_status,
    save_digest_mail,
    unsubscribe_digest_mail,
)
from src.ai_newsletter.utils.limiter import limiter

settings = get_settings()
router = APIRouter()
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

MAX_TOPIC_LENGTH = 200
ALLOWED_TOPIC_RE = re.compile(r"^[\w\s\-.,!?()&]+$")


@router.post(
    "",
    response_model=list[DigestRead],
)
async def route_create_digests(
    current_user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    result = await db.execute(
        select(models.Digest)
        .where(models.Digest.user_id == current_user.id)
        .order_by(models.Digest.created_at.desc())
    )
    digests = result.scalars().all()
    return digests


@router.get("/{digest_id}/status", name="get_digest_status")
@limiter.limit("60/minute")
async def get_digest_status(
    request: Request,
    digest_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):

    user = request.session.get("user")

    stmt = select(Digest).where(
        Digest.id == digest_id,
        Digest.user_id == uuid.UUID(user["id"]),
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(status_code=404, detail="Digest not found")

    response = templates.TemplateResponse(
        request=request,
        name="partials/status_badge.html",
        context={"request": request, "item": item},
    )

    if item.status in ("ready", "failed"):
        response.headers["HX-Trigger"] = "digest-done"

    return response


"""@router.get("/{digest_id}/stream", name="stream_digest_status")
async def stream_digest_status(
    request: Request,
    digest_id: uuid.UUID,
):
    async def generator():
        while True:
            if await request.is_disconnected():
                break

            async with async_session() as session:
                result = await session.execute(
                    select(Digest).where(Digest.id == digest_id)
                )
                item = result.scalar_one_or_none()

            if not item:
                break

            html = templates.get_template("partials/status_badge.html").render(
                {"request": request, "item": item}
            )
            yield {"data": html}

            if item.status in ("ready", "failed"):
                break

            await asyncio.sleep(2)

    return EventSourceResponse(generator())"""


@router.post("/submitText", name="submit_text")
@limiter.limit("5/minute")
async def get_digest_text(request: Request):
    form = await request.form()
    topic = form.get("topic", "").strip()

    if not topic:
        return HTMLResponse(status_code=400, content="Topic is required")
    if len(topic) > MAX_TOPIC_LENGTH:
        return HTMLResponse(status_code=400, content="Topic too long")
    if not ALLOWED_TOPIC_RE.match(topic):
        return HTMLResponse(
            status_code=400, content="Topic contains invalid characters"
        )

    user = request.session.get("user")
    if not user:
        trigger_value = json.dumps({"open-auth-modal": topic})
        return HTMLResponse(status_code=200, headers={"HX-Trigger": trigger_value})

    query = urlencode({"topic": topic})
    response = Response()
    response.headers["HX-Redirect"] = f"{request.url_for('dashboard')}?{query}"
    return response


@router.post("/subscribe/{digest_id}", name="subscribe")
@limiter.limit("10/minute")
async def router_save_mailInfo(
    request: Request,
    emailInfoSave: EmailInfoSave,
    digest_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await save_digest_mail(request, digest_id, emailInfoSave, db)

    return result


@router.post("/unsubscribe/{digest_id}", name="unsubscribe")
@limiter.limit("10/minute")
async def router_unsubscribe_mail(
    request: Request,
    digest_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await unsubscribe_digest_mail(request, digest_id, db)
    return result


@router.get("/subscription_status/{digest_id}", name="subscription_status")
async def router_get_subscription_status(
    request: Request,
    digest_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await get_subscription_status(request, digest_id, db)
    return result


@router.delete("/{digest_id}", name="delete_digest")
@limiter.limit("10/minute")
async def delete_digest(
    request: Request,
    digest_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: models.User = Depends(get_current_user),
):
    result = await db.execute(
        select(Digest).where(
            Digest.id == digest_id,
            Digest.user_id == current_user.id,
        )
    )
    digest = result.scalar_one_or_none()

    if not digest:
        raise HTTPException(status_code=404, detail="Digest not found")
    await db.execute(
        delete(Digest).where(
            Digest.user_id == current_user.id, Digest.title == digest.title
        )
    )
    await db.commit()
    return Response(status_code=200)
