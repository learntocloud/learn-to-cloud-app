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

    def __init__(self, db: AsyncSession):
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
        email: str = "",
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
            "email": email,
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
        email: str,
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
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "avatar_url": avatar_url,
            "github_username": github_username,
        }
        update_values = {
            "email": email,
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

    async def get_many_by_ids(self, user_ids: list[int]) -> list[User]:
        """Get multiple users by their IDs in a single query.

        Returns users in no guaranteed order. Missing IDs are silently skipped.
        """
        if not user_ids:
            return []
        result = await self.db.execute(select(User).where(User.id.in_(user_ids)))
        return list(result.scalars().all())

    async def create(
        self,
        user_id: int,
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
        avatar_url: str | None = None,
        github_username: str | None = None,
    ) -> User:
        """Create a new user.

        Expects github_username to be pre-normalized (lowercase) by service layer.
        """
        user = User(
            id=user_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            avatar_url=avatar_url,
            github_username=github_username,
        )
        self.db.add(user)
        return user

    async def update(
        self,
        user: User,
        *,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        avatar_url: str | None = None,
        github_username: str | None = None,
        is_admin: bool | None = None,
    ) -> User:
        """Update user fields. Only non-None values are updated.

        If github_username is being set and another user already has it,
        clears the github_username from the other user first.

        Expects github_username to be pre-normalized (lowercase) by service layer.
        """
        if email is not None:
            user.email = email
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if avatar_url is not None:
            user.avatar_url = avatar_url
        if github_username is not None:
            existing = await self.get_by_github_username(github_username)
            if existing and existing.id != user.id:
                existing.github_username = None
                await self.db.flush()
            user.github_username = github_username
        if is_admin is not None:
            user.is_admin = is_admin

        user.updated_at = datetime.now(UTC)
        return user

    async def delete(self, user_id: int) -> None:
        """Delete a user by ID. Cascades to related records."""
        await self.db.execute(delete(User).where(User.id == user_id))
