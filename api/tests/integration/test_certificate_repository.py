"""Integration tests for repositories/certificate_repository.py.

Uses real PostgreSQL database with transaction rollback for isolation.
"""

from datetime import UTC, datetime

import pytest

from models import Certificate, User
from repositories.certificate_repository import CertificateRepository


@pytest.mark.asyncio
class TestCertificateRepositoryIntegration:
    """Integration tests for CertificateRepository."""

    async def _create_user(self, db_session, user_id: str = "test-user"):
        """Helper to create a user for FK constraint."""
        user = User(id=user_id, email=f"{user_id}@example.com")
        db_session.add(user)
        await db_session.flush()
        return user

    async def _create_certificate(
        self,
        db_session,
        user_id: str = "test-user",
        certificate_type: str = "phase_1_completion",
        verification_code: str = "ABC123",
    ):
        """Helper to create a certificate."""
        cert = Certificate(
            user_id=user_id,
            certificate_type=certificate_type,
            verification_code=verification_code,
            recipient_name="Test User",
            issued_at=datetime.now(UTC),
            phases_completed=1,
            total_phases=7,
        )
        db_session.add(cert)
        await db_session.flush()
        return cert

    async def test_get_by_id_returns_certificate(self, db_session):
        """get_by_id returns existing certificate."""
        await self._create_user(db_session)
        cert = await self._create_certificate(db_session)

        repo = CertificateRepository(db_session)
        result = await repo.get_by_id(cert.id)

        assert result is not None
        assert result.id == cert.id
        assert result.user_id == "test-user"

    async def test_get_by_id_returns_none_for_missing(self, db_session):
        """get_by_id returns None for non-existent certificate."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_id(99999)
        assert result is None

    async def test_get_by_id_and_user_returns_certificate(self, db_session):
        """get_by_id_and_user returns certificate for matching user."""
        await self._create_user(db_session)
        cert = await self._create_certificate(db_session)

        repo = CertificateRepository(db_session)
        result = await repo.get_by_id_and_user(cert.id, "test-user")

        assert result is not None
        assert result.id == cert.id

    async def test_get_by_id_and_user_returns_none_wrong_user(self, db_session):
        """get_by_id_and_user returns None for wrong user."""
        await self._create_user(db_session)
        cert = await self._create_certificate(db_session)

        repo = CertificateRepository(db_session)
        result = await repo.get_by_id_and_user(cert.id, "other-user")

        assert result is None

    async def test_get_by_verification_code(self, db_session):
        """get_by_verification_code finds certificate by code."""
        await self._create_user(db_session)
        await self._create_certificate(db_session, verification_code="XYZ789")

        repo = CertificateRepository(db_session)
        result = await repo.get_by_verification_code("XYZ789")

        assert result is not None
        assert result.verification_code == "XYZ789"

    async def test_get_by_verification_code_returns_none(self, db_session):
        """get_by_verification_code returns None for unknown code."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_verification_code("NONEXISTENT")
        assert result is None

    async def test_get_by_user_returns_certificates(self, db_session):
        """get_by_user returns all certificates for a user."""
        await self._create_user(db_session)
        await self._create_certificate(
            db_session, certificate_type="phase_1", verification_code="A1"
        )
        await self._create_certificate(
            db_session, certificate_type="phase_2", verification_code="A2"
        )

        repo = CertificateRepository(db_session)
        results = await repo.get_by_user("test-user")

        assert len(results) == 2

    async def test_get_by_user_returns_empty_for_no_certificates(self, db_session):
        """get_by_user returns empty list for user with no certificates."""
        repo = CertificateRepository(db_session)
        results = await repo.get_by_user("nonexistent-user")
        assert len(results) == 0

    async def test_get_by_user_respects_limit(self, db_session):
        """get_by_user respects the limit parameter."""
        await self._create_user(db_session)
        for i in range(5):
            await self._create_certificate(
                db_session,
                certificate_type=f"phase_{i}",
                verification_code=f"CODE{i}",
            )

        repo = CertificateRepository(db_session)
        results = await repo.get_by_user("test-user", limit=3)

        assert len(results) == 3

    async def test_get_by_user_and_type(self, db_session):
        """get_by_user_and_type finds specific certificate type."""
        await self._create_user(db_session)
        await self._create_certificate(
            db_session, certificate_type="phase_1", verification_code="A1"
        )
        await self._create_certificate(
            db_session, certificate_type="phase_2", verification_code="A2"
        )

        repo = CertificateRepository(db_session)
        result = await repo.get_by_user_and_type("test-user", "phase_1")

        assert result is not None
        assert result.certificate_type == "phase_1"

    async def test_get_by_user_and_type_returns_none(self, db_session):
        """get_by_user_and_type returns None for non-existent type."""
        await self._create_user(db_session)
        await self._create_certificate(db_session, certificate_type="phase_1")

        repo = CertificateRepository(db_session)
        result = await repo.get_by_user_and_type("test-user", "phase_99")

        assert result is None

    async def test_exists_for_user_and_type_returns_true(self, db_session):
        """exists_for_user_and_type returns True when certificate exists."""
        await self._create_user(db_session)
        await self._create_certificate(db_session, certificate_type="phase_1")

        repo = CertificateRepository(db_session)
        result = await repo.exists_for_user_and_type("test-user", "phase_1")

        assert result is True

    async def test_exists_for_user_and_type_returns_false(self, db_session):
        """exists_for_user_and_type returns False when certificate doesn't exist."""
        await self._create_user(db_session)

        repo = CertificateRepository(db_session)
        result = await repo.exists_for_user_and_type("test-user", "phase_1")

        assert result is False

    async def test_create_certificate(self, db_session):
        """create creates a new certificate."""
        await self._create_user(db_session)

        repo = CertificateRepository(db_session)
        cert = await repo.create(
            user_id="test-user",
            certificate_type="phase_1_completion",
            verification_code="NEW123",
            recipient_name="New User",
            phases_completed=1,
            total_phases=7,
        )

        assert cert.id is not None
        assert cert.user_id == "test-user"
        assert cert.certificate_type == "phase_1_completion"
        assert cert.verification_code == "NEW123"
        assert cert.recipient_name == "New User"
        assert cert.phases_completed == 1
        assert cert.total_phases == 7
        assert cert.issued_at is not None
