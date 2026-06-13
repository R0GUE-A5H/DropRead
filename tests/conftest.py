import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

pytest_plugins = ["pytest_asyncio"]


@pytest.fixture
def client():
    app = FastAPI()
    from src.ai_newsletter.router.auth import router

    app.include_router(router)
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    return TestClient(app, raise_server_exceptions=False)
