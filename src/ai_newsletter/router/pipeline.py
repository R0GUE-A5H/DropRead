import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

import src.ai_newsletter.models.models as models
from src.ai_newsletter.core.config import get_settings
from src.ai_newsletter.database.engine import get_db
from src.ai_newsletter.services.digest import create_digest

settings = get_settings()
router = APIRouter()
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


# def run_pipeline_in_thread(topic: str, digest_id: str):
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     try:
#         loop.run_until_complete(create_digest(topic, digest_id))
#     finally:
#         loop.close()

"""
@router.post("/init")
async def init_pipeline(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    # frequency: str = Form(...),
    # time: str = Form(...),
    topic: str = Form(...),
):
    user = request.session.get("user")

    if not user:
        response = Response(status_code=204)
        response.headers["HX-Trigger"] = "open-auth-modal"
        return response

    new_digest = models.Digest(
        content="",
        user_id=uuid.UUID(user["id"]),
        title=topic,
        status="running",
    )
    db.add(new_digest)
    await db.commit()
    await db.refresh(new_digest)
    digest_id = str(new_digest.id)

    thread = threading.Thread(target=run_pipeline_in_thread, args=(topic, digest_id))
    thread.daemon = True
    thread.start()

    return templates.TemplateResponse(
        request=request,
        name="partials/status_badge.html",
        context={"request": request, "item": new_digest},
    )"""


@router.post("/init")
async def init_pipeline(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    topic: str = Form(...),
):
    user = request.session.get("user")

    if not user:
        response = Response(status_code=204)
        response.headers["HX-Trigger"] = "open-auth-modal"
        return response

    new_digest = models.Digest(
        content="",
        user_id=uuid.UUID(user["id"]),
        title=topic,
        status="running",
    )
    db.add(new_digest)
    await db.commit()
    await db.refresh(new_digest)

    background_tasks.add_task(create_digest, topic, str(new_digest.id))

    return templates.TemplateResponse(
        request=request,
        name="partials/status_badge.html",
        context={"request": request, "item": new_digest},
    )
