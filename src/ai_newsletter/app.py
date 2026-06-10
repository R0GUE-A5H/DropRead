import os

# os.environ["TRANSFORMERS_OFFLINE"] = "1"
# os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.ai_newsletter.database.engine import async_session, engine
from src.ai_newsletter.models.models import Digest
from src.ai_newsletter.orchestration.graph import init_pipeline, pool
from src.ai_newsletter.router import auth, digests, pages, pipeline, user
from src.ai_newsletter.services.scheduler import run_scheduled_digests
from src.ai_newsletter.utils.dependencies import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
_is_production = os.getenv("APP_ENV") == "production"


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with async_session() as db:
        result = await db.execute(
            update(Digest)
            .where(Digest.status == "running")
            .values(status="failed", current_step="Server restarted, please retry")
        )
        await db.commit()
        logger.info(f"Marked {result.rowcount} orphaned digests as failed")

    await pool.open()
    await init_pipeline()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_scheduled_digests,
        "interval",
        minutes=15,
    )
    scheduler.start()
    logger.info("Scheduler started for auto-delivery of digests")
    yield

    scheduler.shutdown()
    await pool.close()
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
        else [
            "https://dropread-912960397624.asia-south1.run.app"
        ],  # remember to change it
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
