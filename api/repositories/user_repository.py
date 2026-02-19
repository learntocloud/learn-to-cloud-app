"""User repository for database operations."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import User


class UserRepository:
    """Repository for User database operations.

    Transaction Management:
        This repository does NOT commit. The caller (service layer)
        owns the transaction boundary. Use flush() for intermediate
        persistence within a transaction.

    GitHub Username Normalization:
        All methods expect github_username to be pre-normalized
        (lowercase) by the service layer.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: int) -> User | None:
        """Get a user by their ID (GitHub numeric user ID)."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_github_username(self, username: str) -> User | None:
        """Get a user by their GitHub username.

        Expects username to be pre-normalized (lowercase) by service layer.
        Uses indexed lookup on github_username (unique constraint ensures one).
        """
        result = await self.db.execute(
            select(User).where(User.github_username == username)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        user_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        avatar_url: str | None = None,
        github_username: str | None = None,
    ) -> User:
        """Get user from DB or create from GitHub OAuth data.

        Uses INSERT ... ON CONFLICT to handle concurrent requests safely.
        On conflict, updates profile fields from GitHub.

        Query strategy:
        - Existing user (common path): 1 SELECT
        - New user: 1 SELECT + 1 INSERT RETURNING = 2 queries
        - Race condition (rare): 1 SELECT + 1 INSERT (conflict) + 1 SELECT = 3 queries
        """
        user = await self.get_by_id(user_id)
        if user:
            return user

        values = {
            "id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "avatar_url": avatar_url,
            "github_username": github_username,
        }

        stmt = (
            pg_insert(User)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(User)
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user

        # Race condition: another request inserted between our SELECT and INSERT
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one()

    async def upsert(
        self,
        user_id: int,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        avatar_url: str | None = None,
        github_username: str | None = None,
    ) -> User:
        """Insert or update a user in a single query.

        Returns the upserted user. Expects github_username to be pre-normalized.
        """
        values = {
            "id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "avatar_url": avatar_url,
            "github_username": github_username,
        }
        update_values = {
            "first_name": first_name,
            "last_name": last_name,
            "avatar_url": avatar_url,
            "github_username": github_username,
            "updated_at": datetime.now(UTC),
        }

        stmt = (
            pg_insert(User)
            .values(**values)
            .on_conflict_do_update(index_elements=["id"], set_=update_values)
            .returning(User)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def clear_github_username(self, user_id: int) -> None:
        """Clear the github_username field for a specific user."""
        user = await self.get_by_id(user_id)
        if user is not None:
            user.github_username = None
            user.updated_at = datetime.now(UTC)
            await self.db.flush()

    async def delete(self, user_id: int) -> None:
        """Delete a user by ID. Cascades to related records."""
        await self.db.execute(delete(User).where(User.id == user_id))
