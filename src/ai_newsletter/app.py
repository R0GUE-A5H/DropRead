import os

from src.ai_newsletter.services.auth import get_current_user

# os.environ["TRANSFORMERS_OFFLINE"] = "1"
# os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import update
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.ai_newsletter.database.engine import async_session, engine
from src.ai_newsletter.models.models import Digest
from src.ai_newsletter.orchestration.graph import init_pipeline, pool
from src.ai_newsletter.router import auth, digests, pages, pipeline, user
from src.ai_newsletter.services.scheduler import run_scheduled_digests
from src.ai_newsletter.utils.dependencies import settings, verify_csrf
from src.ai_newsletter.utils.limiter import limiter

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

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    allowed_origins = [
        o.strip() for o in settings.allowed_origins.split(",") if o.strip()
    ]

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        https_only=_is_production,
        same_site="lax",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not _is_production else allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(
        user.router,
        prefix="/api/user",
        dependencies=[Depends(get_current_user), Depends(verify_csrf)],
    )
    app.include_router(
        digests.router,
        prefix="/api/digests",
        dependencies=[Depends(get_current_user), Depends(verify_csrf)],
    )
    app.include_router(
        pipeline.router,
        prefix="/api/pipeline",
        dependencies=[Depends(get_current_user), Depends(verify_csrf)],
    )

    return app


app = create_app()
