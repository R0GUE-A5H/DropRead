from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_newsletter.database.engine import get_db
from src.ai_newsletter.database.schemas import UserCreate
from src.ai_newsletter.services.auth import create_google_user
from src.ai_newsletter.utils.csrf import generate_csrf_token, set_csrf_cookie
from src.ai_newsletter.utils.dependencies import oauth
from src.ai_newsletter.utils.limiter import limiter

router = APIRouter()


@router.get("/login/google", name="login_google")
@limiter.limit("5/minute")
async def login_google(request: Request, topic: str = ""):
    redirect_uri = request.url_for("auth_google_callback")
    state = topic or "none"
    return await oauth.google.authorize_redirect(request, redirect_uri, state=state)


@router.get("/auth/google/callback")
@limiter.limit("5/minute")
async def auth_google_callback(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")
    topic = request.query_params.get("state", "")
    if topic == "none":
        topic = ""

    user_model = UserCreate(
        username=user_info["name"],
        email=user_info["email"],
        picture=user_info["picture"],
        google_id=user_info["sub"],
    )

    db_user = await create_google_user(user_model, db)

    request.session["user"] = {
        "id": str(db_user.id),
        "email": db_user.email,
        "name": db_user.name,
        "picture": db_user.profile_picture,
    }

    next_url = request.session.pop("next", None)

    if next_url and next_url.startswith("/digests/"):
        redirect_url = next_url
    elif topic:
        redirect_url = f"{request.url_for('dashboard')}?{urlencode({'topic': topic})}"
    else:
        redirect_url = "/"

    response = RedirectResponse(url=redirect_url, status_code=303)
    set_csrf_cookie(response, generate_csrf_token())
    return response


@router.get("/logout", name="logout")
@limiter.limit("5/minute")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session")
    return response
