"""User repository for database operations."""

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import User, utcnow


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

    async def get_by_ids(self, user_ids: Iterable[int]) -> list[User]:
        """Batch-fetch users by id in a single query.

        Order is unspecified; callers that need a stable order should sort
        the result. Returns an empty list for an empty id set.
        """
        ids = list(user_ids)
        if not ids:
            return []
        result = await self.db.execute(select(User).where(User.id.in_(ids)))
        return list(result.scalars().all())

    async def upsert(
        self,
        user_id: int,
        *,
        github_username: str,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        """Flush the whole session, then insert or refresh the user's profile.

        Provider fields override pending profile edits; unrelated changes survive.
        A clean session uses one statement. The caller owns commit or rollback.
        """
        await self.db.flush()
        values = {
            "id": user_id,
            "display_name": display_name,
            "avatar_url": avatar_url,
            "github_username": github_username,
        }
        update_values = {
            "display_name": display_name,
            "avatar_url": avatar_url,
            "github_username": github_username,
            "updated_at": utcnow(),
        }

        stmt = (
            pg_insert(User)
            .values(**values)
            .on_conflict_do_update(index_elements=["id"], set_=update_values)
            .returning(User)
        )
        result = await self.db.execute(
            stmt, execution_options={"populate_existing": True}
        )
        return result.scalar_one()

    async def delete(self, user_id: int) -> None:
        """Delete a user by ID. Cascades to related records."""
        await self.db.execute(delete(User).where(User.id == user_id))
