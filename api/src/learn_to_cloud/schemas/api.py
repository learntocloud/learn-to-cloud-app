"""HTTP response models for users and health checks."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    """Base user schema."""

    display_name: str | None = None
    avatar_url: str | None = None
    github_username: str | None = None


class UserResponse(UserBase):
    """User response schema (also used as service-layer response model)."""

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: int
    is_admin: bool = False
    created_at: datetime


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str
    curriculum_version: int | None = None
    artifact_schema_version: int | None = None
    content_hash: str | None = None
