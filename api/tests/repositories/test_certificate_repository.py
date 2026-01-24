"""Tests for certificate repository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.certificate_repository import CertificateRepository
from tests.factories import CertificateFactory, UserFactory

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration


class TestCertificateRepository:
    """Tests for CertificateRepository."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    @pytest.fixture
    async def certificate(self, db_session: AsyncSession, user):
        """Create a test certificate."""
        cert = CertificateFactory.build(user_id=user.id)
        db_session.add(cert)
        await db_session.flush()
        return cert

    async def test_get_by_id_and_user_found(
        self, db_session: AsyncSession, user, certificate
    ):
        """Test getting certificate by ID and user ID."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_id_and_user(certificate.id, user.id)
        assert result is not None
        assert result.id == certificate.id
        assert result.user_id == user.id

    async def test_get_by_id_and_user_wrong_user(
        self, db_session: AsyncSession, user, certificate
    ):
        """Test getting certificate with wrong user ID returns None."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_id_and_user(certificate.id, "wrong-user-id")
        assert result is None

    async def test_get_by_id_and_user_not_found(self, db_session: AsyncSession, user):
        """Test getting non-existent certificate returns None."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_id_and_user(99999, user.id)
        assert result is None

    async def test_get_by_verification_code_found(
        self, db_session: AsyncSession, certificate
    ):
        """Test getting certificate by verification code."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_verification_code(certificate.verification_code)
        assert result is not None
        assert result.verification_code == certificate.verification_code

    async def test_get_by_verification_code_not_found(self, db_session: AsyncSession):
        """Test getting certificate with non-existent verification code."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_verification_code("INVALID-CODE")
        assert result is None

    async def test_get_by_user(self, db_session: AsyncSession, user):
        """Test getting all certificates for a user."""
        repo = CertificateRepository(db_session)

        # Create multiple certificates
        cert1 = CertificateFactory.build(user_id=user.id, certificate_type="type1")
        cert2 = CertificateFactory.build(user_id=user.id, certificate_type="type2")
        db_session.add_all([cert1, cert2])
        await db_session.flush()

        result = await repo.get_by_user(user.id)
        assert len(result) == 2

    async def test_get_by_user_empty(self, db_session: AsyncSession, user):
        """Test getting certificates for user with none."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_user(user.id)
        assert len(result) == 0

    async def test_get_by_user_respects_limit(self, db_session: AsyncSession, user):
        """Test that limit parameter is respected."""
        repo = CertificateRepository(db_session)

        # Create 5 certificates
        for i in range(5):
            cert = CertificateFactory.build(
                user_id=user.id, certificate_type=f"type{i}"
            )
            db_session.add(cert)
        await db_session.flush()

        result = await repo.get_by_user(user.id, limit=3)
        assert len(result) == 3

    async def test_get_by_user_and_type_found(
        self, db_session: AsyncSession, user, certificate
    ):
        """Test getting certificate by user and type."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_user_and_type(user.id, certificate.certificate_type)
        assert result is not None
        assert result.certificate_type == certificate.certificate_type

    async def test_get_by_user_and_type_not_found(
        self, db_session: AsyncSession, user, certificate
    ):
        """Test getting certificate by user and non-existent type."""
        repo = CertificateRepository(db_session)
        result = await repo.get_by_user_and_type(user.id, "nonexistent_type")
        assert result is None

    async def test_create(self, db_session: AsyncSession, user):
        """Test creating a new certificate."""
        repo = CertificateRepository(db_session)

        result = await repo.create(
            user_id=user.id,
            certificate_type="full_completion",
            verification_code="LTC-TEST123-ABCD",
            recipient_name="Test User",
            phases_completed=7,
            total_phases=7,
        )

        assert result.id is not None
        assert result.user_id == user.id
        assert result.certificate_type == "full_completion"
        assert result.verification_code == "LTC-TEST123-ABCD"
        assert result.recipient_name == "Test User"
        assert result.phases_completed == 7
        assert result.total_phases == 7
        assert result.issued_at is not None

    async def test_create_sets_issued_at(self, db_session: AsyncSession, user):
        """Test that create sets issued_at to current UTC time."""
        repo = CertificateRepository(db_session)

        result = await repo.create(
            user_id=user.id,
            certificate_type="full_completion",
            verification_code="LTC-TEST456-EFGH",
            recipient_name="Test User",
            phases_completed=7,
            total_phases=7,
        )

        assert result.issued_at is not None
        # Should be recent (within last minute)
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        assert now - result.issued_at < timedelta(minutes=1)
