from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.ai_newsletter.database.engine import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    profile_picture: Mapped[str | None] = mapped_column(String)
    google_id: Mapped[str | None] = mapped_column(String, unique=True)
    email_notifications: Mapped[bool] = mapped_column(
        default=True, server_default="true"
    )


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    current_step: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
    auto_digest: Mapped[bool] = mapped_column(default=False, server_default="false")
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    next_delivery: Mapped[datetime | None] = mapped_column(nullable=True)
    delivery_time: Mapped[str] = mapped_column(String, nullable=False, default="08:00")
    delivery_day: Mapped[str] = mapped_column(String, nullable=False, default="Monday")
    extra_data: Mapped[list[dict] | None] = mapped_column(JSONB)


class DigestCache(Base):
    __tablename__ = "digest_cache"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    topic_embedding: Mapped[Vector] = mapped_column(Vector(384), nullable=False)
    digest_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("digests.id", ondelete="CASCADE"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
