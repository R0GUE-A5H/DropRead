import uuid
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
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

settings = get_settings()
router = APIRouter()
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


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
async def get_digest_status(
    request: Request,
    digest_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = select(Digest).where(Digest.id == digest_id)
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(status_code=404, detail="Digest not found")

    return templates.TemplateResponse(
        request=request,
        name="partials/status_badge.html",
        context={
            "request": request,
            "item": item,
        },
    )


@router.post("/submitText", name="submit_text")
async def get_digest_text(request: Request):
    form = await request.form()
    topic = form["topic"]

    user = request.session.get("user")
    if not user:
        return HTMLResponse(
            status_code=200, headers={"HX-Trigger": f'{{"open-auth-modal": "{topic}"}}'}
        )

    query = urlencode({"topic": topic})

    response = Response()
    response.headers["HX-Redirect"] = f"{request.url_for('dashboard')}?{query}"
    return response


@router.post("/subscribe/{digest_id}", name="subscribe")
async def router_save_mailInfo(
    request: Request,
    emailInfoSave: EmailInfoSave,
    digest_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await save_digest_mail(request, digest_id, emailInfoSave, db)

    return result


@router.post("/unsubscribe/{digest_id}", name="unsubscribe")
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
