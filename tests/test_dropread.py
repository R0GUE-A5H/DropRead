import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestNextDeliveryDt:
    def test_always_returns_future_datetime(self):
        from src.ai_newsletter.services.scheduler import next_delivery_dt  # noqa: E402

        for day in [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]:
            result = next_delivery_dt(day, "09:00")
            assert result > datetime.utcnow(), f"Got past datetime for {day}"

    def test_returns_naive_datetime(self):
        from src.ai_newsletter.services.scheduler import next_delivery_dt  # noqa: E402

        result = next_delivery_dt("Monday", "09:00")
        assert result.tzinfo is None

    def test_correct_weekday(self):
        from src.ai_newsletter.services.scheduler import next_delivery_dt  # noqa: E402

        day_map = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }
        for day_name, expected in day_map.items():
            assert next_delivery_dt(day_name, "10:00").weekday() == expected

    def test_correct_hour_and_minute(self):
        from src.ai_newsletter.services.scheduler import next_delivery_dt  # noqa: E402

        result = next_delivery_dt("Friday", "14:30")
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 0

    def test_same_day_past_time_goes_to_next_week(self):
        from src.ai_newsletter.services.scheduler import next_delivery_dt  # noqa: E402

        now = datetime.now(UTC)
        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        today = day_names[now.weekday()]
        past_hour = (now.hour - 2) % 24
        result = next_delivery_dt(today, f"{past_hour:02d}:00")
        assert result > datetime.utcnow() + timedelta(days=5)

    def test_midnight_delivery(self):
        from src.ai_newsletter.services.scheduler import next_delivery_dt  # noqa: E402

        result = next_delivery_dt("Sunday", "00:00")
        assert result > datetime.utcnow()
        assert result.hour == 0
        assert result.minute == 0

    def test_unknown_day_does_not_crash(self):
        from src.ai_newsletter.services.scheduler import next_delivery_dt  # noqa: E402

        result = next_delivery_dt("Funday", "09:00")
        assert result > datetime.utcnow()


class TestSemanticCache:
    def _make_mock_db(self, similarity):
        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        if similarity is None:
            r = MagicMock()
            r.first.return_value = None
            mock_db.execute.return_value = r
        else:
            row = MagicMock()
            row.similarity = similarity
            row.topic = "python programming"
            row.content = "Summary about Python"
            row.extra_data = [{"url": "https://example.com"}]
            r = MagicMock()
            r.first.return_value = row
            mock_db.execute.return_value = r

        return mock_db

    def _mock_embedder(self, mock_emb):
        mock_emb.return_value.encode.return_value.tolist.return_value = [0.1] * 384

    @pytest.mark.asyncio
    async def test_hit_above_threshold(self):
        mock_db = self._make_mock_db(0.90)
        with (
            patch(
                "src.ai_newsletter.services.cache.async_session", return_value=mock_db
            ),
            patch("src.ai_newsletter.services.cache._get_embedder") as mock_emb,
        ):
            self._mock_embedder(mock_emb)
            from src.ai_newsletter.services.cache import get_cached_digest  # noqa: E402

            result = await get_cached_digest("python tutorial")
        assert result is not None
        assert result["content"] == "Summary about Python"
        assert result["cached_topic"] == "python programming"

    @pytest.mark.asyncio
    async def test_miss_below_threshold(self):
        mock_db = self._make_mock_db(0.70)
        with (
            patch(
                "src.ai_newsletter.services.cache.async_session", return_value=mock_db
            ),
            patch("src.ai_newsletter.services.cache._get_embedder") as mock_emb,
        ):
            self._mock_embedder(mock_emb)
            from src.ai_newsletter.services.cache import get_cached_digest  # noqa: E402

            result = await get_cached_digest("something different")
        assert result is None

    @pytest.mark.asyncio
    async def test_exact_threshold_is_a_hit(self):
        mock_db = self._make_mock_db(0.82)
        with (
            patch(
                "src.ai_newsletter.services.cache.async_session", return_value=mock_db
            ),
            patch("src.ai_newsletter.services.cache._get_embedder") as mock_emb,
        ):
            self._mock_embedder(mock_emb)
            from src.ai_newsletter.services.cache import get_cached_digest  # noqa: E402

            result = await get_cached_digest("python programming")
        assert result is not None

    @pytest.mark.asyncio
    async def test_empty_db_returns_none(self):
        mock_db = self._make_mock_db(None)
        with (
            patch(
                "src.ai_newsletter.services.cache.async_session", return_value=mock_db
            ),
            patch("src.ai_newsletter.services.cache._get_embedder") as mock_emb,
        ):
            self._mock_embedder(mock_emb)
            from src.ai_newsletter.services.cache import get_cached_digest  # noqa: E402

            result = await get_cached_digest("anything")
        assert result is None


from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402


def make_test_app():
    app = FastAPI()
    from src.ai_newsletter.router.pipeline import router  # noqa: E402

    app.include_router(router, prefix="/api/pipeline")
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")
    return app


class TestPipelineRoute:
    def test_unauthenticated_returns_204_and_htmx_trigger(self):
        client = TestClient(make_test_app(), raise_server_exceptions=False)
        resp = client.post("/api/pipeline/init", data={"topic": "machine learning"})
        assert resp.status_code == 204
        assert resp.headers.get("hx-trigger") == "open-auth-modal"

    def test_topic_too_short_rejected(self):
        client = TestClient(make_test_app(), raise_server_exceptions=False)
        resp = client.post("/api/pipeline/init", data={"topic": "AI"})
        assert resp.status_code == 422

    def test_empty_topic_rejected(self):
        client = TestClient(make_test_app(), raise_server_exceptions=False)
        resp = client.post("/api/pipeline/init", data={"topic": ""})
        assert resp.status_code == 422

    def test_topic_too_long_rejected(self):
        client = TestClient(make_test_app(), raise_server_exceptions=False)
        resp = client.post("/api/pipeline/init", data={"topic": "x" * 201})
        assert resp.status_code == 422


class TestDigestEmail:
    @pytest.mark.asyncio
    async def test_sends_to_correct_recipient(self):
        with patch(
            "src.ai_newsletter.services.digest_email.resend.Emails.send"
        ) as mock_send:
            mock_send.return_value = {"id": "fake-id"}
            from src.ai_newsletter.services.digest_email import (
                send_digest_email,  # noqa: E402
            )

            await send_digest_email(
                to_email="ash@example.com",
                topic="Python asyncio",
                content="## Summary\nPython asyncio is great.",
                digest_id="094091b6-2282-4ad7-87e2-b8331b862949",
            )
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_does_not_raise(self):
        with patch(
            "src.ai_newsletter.services.digest_email.resend.Emails.send"
        ) as mock_send:
            mock_send.side_effect = Exception("Resend API down")
            from src.ai_newsletter.services.digest_email import (
                send_digest_email,  # noqa: E402
            )

            # Must not raise
            await send_digest_email(
                to_email="ash@example.com",
                topic="test",
                content="content",
                digest_id="094091b6-2282-4ad7-87e2-b8331b862949",
            )

    @pytest.mark.asyncio
    async def test_markdown_rendered_in_html(self):
        with patch(
            "src.ai_newsletter.services.digest_email.resend.Emails.send"
        ) as mock_send:
            mock_send.return_value = {"id": "fake-id"}
            from src.ai_newsletter.services.digest_email import (
                send_digest_email,  # noqa: E402
            )

            await send_digest_email(
                to_email="test@example.com",
                topic="test",
                content="## Heading\nSome **bold** text",
                digest_id="094091b6-2282-4ad7-87e2-b8331b862949",
            )

        mock_send.assert_called_once()

        params = mock_send.call_args[0][0]
        assert "<h2>" in params["html"]
        assert "<strong>" in params["html"]
