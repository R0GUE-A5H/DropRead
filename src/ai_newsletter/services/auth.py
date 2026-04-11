from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_newsletter.database.engine import get_db
from src.ai_newsletter.database.schemas import UserCreate
from src.ai_newsletter.models.models import User


async def create_google_user(user: UserCreate, db: AsyncSession):

    stmt = select(User).where(User.email == user.email)
    result = await db.execute(stmt)

    existing_user = result.scalar_one_or_none()

    if existing_user:
        # print(f"User with email {user.email} already exists.")
        return existing_user

    new_user = User(
        email=user.email,
        name=user.username,
        google_id=user.google_id,
        profile_picture=user.picture,
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


async def get_current_user(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=401, detail="Not authenticated")

    stmt = select(User).where(User.email == user_data["email"])
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user
