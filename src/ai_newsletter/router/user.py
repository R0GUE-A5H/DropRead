from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_newsletter.database.engine import get_db
from src.ai_newsletter.database.schemas import UserSettings
from src.ai_newsletter.models import models
from src.ai_newsletter.services.auth import get_current_user
from src.ai_newsletter.utils.limiter import limiter

router = APIRouter()


@router.get("/getUserSettings", name="get_user_settings")
@limiter.limit("2/minute")
async def get_user_settings(
    current_user: models.User = Depends(get_current_user),
):
    return {
        # "delivery_time": current_user.delivery_time,
        # "email_notifications": current_user.email_notifications,
    }


@router.patch("/updateSettings", name="update_profile_setting")
@limiter.limit("10/minute")
async def update_profile_setting(
    payload: UserSettings,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)],
):

    if payload.delivery_time is not None:
        current_user.delivery_time = payload.delivery_time
    if payload.email_notifications is not None:
        current_user.email_notifications = payload.email_notifications

    await db.commit()
    await db.refresh(current_user)
    return {
        "delivery_time": current_user.delivery_time,
        "email_notifications": current_user.email_notifications,
    }


@router.post("/deleteUser", name="delete_user")
@limiter.limit("2/minute")
async def delete_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)],
):
    await db.delete(current_user)
    await db.commit()
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
