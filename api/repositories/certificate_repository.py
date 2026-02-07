"""Repository for certificate operations."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Certificate


class CertificateRepository:
    """Repository for certificate CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id_and_user(
        self,
        certificate_id: int,
        user_id: int,
    ) -> Certificate | None:
        """Get a certificate by ID that belongs to a specific user."""
        result = await self.db.execute(
            select(Certificate).where(
                Certificate.id == certificate_id,
                Certificate.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_verification_code(
        self,
        verification_code: str,
    ) -> Certificate | None:
        """Get a certificate by its verification code (for public verification)."""
        result = await self.db.execute(
            select(Certificate).where(
                Certificate.verification_code == verification_code
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user(
        self,
        user_id: int,
    ) -> Certificate | None:
        """Get the certificate for a user (only one per user)."""
        result = await self.db.execute(
            select(Certificate).where(
                Certificate.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        verification_code: str,
        recipient_name: str,
        phases_completed: int,
        total_phases: int,
    ) -> Certificate:
        """Create a new certificate.

        Sets issued_at to current UTC time. Calls flush() but does NOT commit;
        the caller is responsible for transaction management.
        """
        certificate = Certificate(
            user_id=user_id,
            verification_code=verification_code,
            recipient_name=recipient_name,
            issued_at=datetime.now(UTC),
            phases_completed=phases_completed,
            total_phases=total_phases,
        )
        self.db.add(certificate)
        await self.db.flush()
        return certificate
