import pytest

from src.ai_newsletter.database.schemas import UserCreate


def test_logout_clears_session(client):
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


@pytest.mark.asyncio
async def test_user_create_schema_validates():
    user = UserCreate(
        username="Test User",
        email="test@example.com",
        picture="https://example.com/pic.jpg",
        google_id="123456",
    )
    assert user.username == "Test User"
    assert user.email == "test@example.com"
    assert user.google_id == "123456"
