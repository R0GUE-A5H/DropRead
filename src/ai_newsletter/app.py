# ruff: noqa: E402
import logging
import os

from src.ai_newsletter.router import digest_router
from src.ai_newsletter.utils.csrf import generate_csrf_token, set_csrf_cookie
from src.ai_newsletter.utils.logging_config import setup_logging

_is_production = os.getenv("APP_ENV") == "production"
if _is_production:
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
setup_logging()
logger = logging.getLogger(__name__)
import asyncio
import sys
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import update
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.ai_newsletter.database.engine import async_session, engine
from src.ai_newsletter.models.models import Digest
from src.ai_newsletter.orchestration.graph import init_pipeline, pool
from src.ai_newsletter.router import auth, digests, pages, user
from src.ai_newsletter.services.auth import get_current_user
from src.ai_newsletter.services.scheduler import run_scheduled_digests
from src.ai_newsletter.utils.dependencies import settings, verify_csrf
from src.ai_newsletter.utils.limiter import limiter
from src.ai_newsletter.utils.metrics import MetricsMiddleware

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

    app.add_middleware(MetricsMiddleware)
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
        allow_credentials=False if not _is_production else True,
    )
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    # @app.post("/api/scheduler/run")
    # async def trigger_scheduler_run(
    #     request: Request,
    #     x_scheduler_secret: Annotated[str | None, Header()] = None,
    # ):
    #     if x_scheduler_secret != settings.SECRET_KEY:
    #         raise HTTPException(status_code=403, detail="Forbidden")

    #     # grab any ready digest + user
    #     async with async_session() as db:
    #         result = await db.execute(
    #             select(Digest, User)
    #             .join(User, Digest.user_id == User.id)
    #             .where(Digest.status == "ready")
    #             .limit(1)
    #         )
    #         row = result.first()

    #     if not row:
    #         return {"status": "no ready digest found"}

    #     d, u = row
    #     new_digest_id = str(uuid.uuid4())

    #     async with async_session() as db:
    #         new_digest = Digest(
    #             id=uuid.UUID(new_digest_id),
    #             user_id=d.user_id,
    #             title=d.title,
    #             content="",
    #             status="running",
    #             auto_digest=False,
    #         )
    #         db.add(new_digest)
    #         await db.commit()

    #     await create_digest(d.title, new_digest_id, skip_cache=True)

    #     async with async_session() as db:
    #         result = await db.execute(
    #             select(Digest).where(Digest.id == uuid.UUID(new_digest_id))
    #         )
    #         fresh = result.scalar_one_or_none()

    #     if not fresh or fresh.status != "ready":
    #         return {"status": "pipeline failed", "digest_id": new_digest_id}

    #     await send_digest_email(
    #         to_email=u.email,
    #         topic=fresh.title,
    #         content=fresh.content,
    #         digest_id=str(fresh.id),
    #     )
    #     return {
    #         "status": "sent",
    #         "to": u.email,
    #         "topic": fresh.title,
    #         "digest_id": new_digest_id,
    #     }
    @app.middleware("http")
    async def ensure_csrf_cookie(request: Request, call_next):
        response = await call_next(request)
        if (
            request.method == "GET"
            and "text/html" in response.headers.get("content-type", "")
            and not request.cookies.get("csrf_token")
        ):
            set_csrf_cookie(response, generate_csrf_token())
        return response

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
        digest_router.router,
        prefix="/api/pipeline",
        dependencies=[Depends(get_current_user), Depends(verify_csrf)],
    )

    return app


app = create_app()
