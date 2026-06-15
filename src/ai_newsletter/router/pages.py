import uuid
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_newsletter.database.engine import get_db
from src.ai_newsletter.models.models import Digest
from src.ai_newsletter.services.digest import (
    get_digest_by_id,
    get_digests_per_topic,
    get_past_digests_by_topic,
)
from src.ai_newsletter.utils.dependencies import templates
from src.ai_newsletter.utils.shared import estimate_read_time

router = APIRouter()


@router.get("/")
async def home(request: Request):
    # Get user from session
    user = request.session.get("user")

    return templates.TemplateResponse(
        request=request, name="index.html", context={"user": user}
    )


@router.get("/dashboard", name="dashboard")
async def dashboard(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    user = request.session.get("user")
    topic = request.query_params.get("topic", "")
    if not user:
        return RedirectResponse(url=request.url_for("login_google"))
    all_digests = await get_digests_per_topic(db, str(user["id"]))
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "user": user,
            "items": all_digests,
            "topic": topic,
        },
    )


@router.get("/digests/{digest_id}", name="view_digest")
async def view_digest(
    request: Request,
    digest_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url=request.url_for("login_google"))

    digest = await get_digest_by_id(
        db,
        digest_id=digest_id,
        user_id=uuid.UUID(user["id"]),
    )

    if not digest:
        return RedirectResponse(url=request.url_for("dashboard"))

    if request.query_params.get("latest") == "true":
        stmt = (
            select(Digest)
            .where(
                Digest.user_id == uuid.UUID(user["id"]),
                Digest.title == digest.title,
                Digest.status == "ready",
            )
            .order_by(Digest.created_at.desc())
        )
        latest_digest = (await db.execute(stmt)).scalars().first()

        if latest_digest and latest_digest.id != digest.id:
            return RedirectResponse(
                url=request.url_for("view_digest", digest_id=latest_digest.id)
            )

    is_archive = digest.current_step == "Emailed"
    parent_digest_id = None

    if is_archive:
        parent_stmt = (
            select(Digest)
            .where(
                Digest.user_id == uuid.UUID(user["id"]),
                Digest.title == digest.title,
                Digest.current_step != "Emailed",
            )
            .order_by(Digest.created_at.desc())
        )

        parent = (await db.execute(parent_stmt)).scalar_one_or_none()
        if parent:
            parent_digest_id = str(parent.id)

    web_info = digest.extra_data or []
    source_count = len(web_info)
    read_time = estimate_read_time(digest.content)

    for source in web_info:
        if "url" in source:
            source["domain"] = urlparse(source["url"]).netloc
        else:
            source["domain"] = ""

    past_digests_raw = await get_past_digests_by_topic(
        db, user_id=str(user["id"]), current_digest_id=digest.id, topic=digest.title
    )

    previous_digests = [
        {
            "id": p.id,
            "created_at": p.created_at,
            "read_time": estimate_read_time(p.content),
        }
        for p in past_digests_raw
    ]

    return templates.TemplateResponse(
        request=request,
        name="digest.html",
        context={
            "request": request,
            "user": user,
            "digest": digest,
            "web_info": web_info,
            "source": source_count,
            "read_time": read_time,
            "previous_digests": previous_digests,
            "parent_digest_id": parent_digest_id,
            "is_archive": is_archive,
        },
    )
