import asyncio
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.ai_newsletter.database.engine import engine
from src.ai_newsletter.router import auth, digests, pages, pipeline, user
from src.ai_newsletter.utils.dependencies import settings

_is_production = os.getenv("APP_ENV") == "production"


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        https_only=_is_production,
        same_site="lax",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"]
        if not _is_production
        else ["https://dropread-912960397624.asia-south1.run.app"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(user.router, prefix="/api/user")
    app.include_router(digests.router, prefix="/api/digests")
    app.include_router(pipeline.router, prefix="/api/pipeline")

    return app


app = create_app()
