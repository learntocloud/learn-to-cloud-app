"""Repository for certificate operations."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Certificate

class CertificateRepository:
    """Repository for certificate CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(
        self,
        certificate_id: int,
    ) -> Certificate | None:
        """Get a certificate by ID."""
        result = await self.db.execute(
            select(Certificate).where(Certificate.id == certificate_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_user(
        self,
        certificate_id: int,
        user_id: str,
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
        user_id: str,
    ) -> Sequence[Certificate]:
        """Get all certificates for a user, most recent first."""
        result = await self.db.execute(
            select(Certificate)
            .where(Certificate.user_id == user_id)
            .order_by(Certificate.issued_at.desc())
        )
        return result.scalars().all()

    async def get_by_user_and_type(
        self,
        user_id: str,
        certificate_type: str,
    ) -> Certificate | None:
        """Get a specific type of certificate for a user."""
        result = await self.db.execute(
            select(Certificate).where(
                Certificate.user_id == user_id,
                Certificate.certificate_type == certificate_type,
            )
        )
        return result.scalar_one_or_none()

    async def exists_for_user_and_type(
        self,
        user_id: str,
        certificate_type: str,
    ) -> bool:
        """Check if a user already has a specific certificate type."""
        cert = await self.get_by_user_and_type(user_id, certificate_type)
        return cert is not None

    async def create(
        self,
        user_id: str,
        certificate_type: str,
        verification_code: str,
        recipient_name: str,
        phases_completed: int,
        total_phases: int,
    ) -> Certificate:
        """Create a new certificate."""
        certificate = Certificate(
            user_id=user_id,
            certificate_type=certificate_type,
            verification_code=verification_code,
            recipient_name=recipient_name,
            issued_at=datetime.now(UTC),
            phases_completed=phases_completed,
            total_phases=total_phases,
        )
        self.db.add(certificate)
        await self.db.flush()
        return certificate
