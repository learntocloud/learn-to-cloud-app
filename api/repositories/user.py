"""User repository for database operations."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import User


class UserRepository:
    """Repository for User database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: str) -> User | None:
        """Get a user by their ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_github_username(self, username: str) -> User | None:
        """Get a user by their GitHub username."""
        result = await self.db.execute(
            select(User).where(User.github_username == username)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: str) -> User:
        """Get user from DB or create placeholder.

        Uses INSERT ... ON CONFLICT to handle concurrent requests safely.
        The placeholder will be updated via Clerk webhook later.
        """
        user = await self.get_by_id(user_id)
        if user:
            return user

        bind = self.db.get_bind()
        dialect = bind.dialect.name if bind else ""

        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = (
                pg_insert(User)
                .values(id=user_id, email=f"{user_id}@placeholder.local")
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await self.db.execute(stmt)
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            stmt = (
                sqlite_insert(User)
                .values(id=user_id, email=f"{user_id}@placeholder.local")
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await self.db.execute(stmt)
        else:
            try:
                user = User(id=user_id, email=f"{user_id}@placeholder.local")
                self.db.add(user)
                await self.db.flush()
            except IntegrityError:
                await self.db.rollback()

        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one()

    async def create(
        self,
        user_id: str,
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
        avatar_url: str | None = None,
        github_username: str | None = None,
    ) -> User:
        """Create a new user."""
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
        """Update user fields. Only non-None values are updated."""
        if email is not None:
            user.email = email
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if avatar_url is not None:
            user.avatar_url = avatar_url
        if github_username is not None:
            user.github_username = github_username
        if is_admin is not None:
            user.is_admin = is_admin

        user.updated_at = datetime.now(UTC)
        return user

    async def delete(self, user_id: str) -> None:
        """Delete a user by ID. Cascades to related records."""
        await self.db.execute(delete(User).where(User.id == user_id))

    def is_placeholder(self, user: User) -> bool:
        """Check if user has placeholder data (not yet synced from Clerk)."""
        return user.email.endswith("@placeholder.local")

    def needs_sync(self, user: User) -> bool:
        """Check if user needs data sync from Clerk."""
        return (
            self.is_placeholder(user) or not user.avatar_url or not user.github_username
        )
