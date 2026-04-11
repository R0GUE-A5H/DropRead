from contextlib import asynccontextmanager

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src.ai_newsletter.core.config import get_settings
from src.ai_newsletter.database.engine import Base, engine
from src.ai_newsletter.router import auth, digests, pages, pipeline, user

settings = get_settings()

templates = Jinja2Templates(directory="templates")
oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(SessionMiddleware, secret_key=settings.google_client_secret)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(user.router, prefix="/api/user")
    app.include_router(digests.router, prefix="/api/digests")
    app.include_router(pipeline.router, prefix="/api/pipeline")

    return app


app = create_app()
