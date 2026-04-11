from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr = Field(max_length=120)
    picture: str | None = None
    google_id: str | None = None


class UserRead(BaseModel):
    id: str
    email: EmailStr
    name: str
    picture: str | None = None

    model_config = ConfigDict(from_attributes=True)


# name should match the frontend field name
class UserSettings(BaseModel):
    delivery_time: str = None
    email_notifications: bool = None


class DigestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=10, max_length=1000)
    sources: dict[str, Any]
