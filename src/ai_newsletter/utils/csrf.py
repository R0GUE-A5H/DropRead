import os
import secrets

from starlette.responses import JSONResponse

from src.ai_newsletter.core.config import get_settings

settings = get_settings()
_is_production = os.getenv("APP_ENV") == "production"


def generate_csrf_token():
    return secrets.token_hex(32)


def set_csrf_cookie(response: JSONResponse, token: str):
    response.set_cookie(
        "csrf_token",
        token,
        httponly=False,
        secure=_is_production,
        samesite="lax",
        max_age=86400,
    )
