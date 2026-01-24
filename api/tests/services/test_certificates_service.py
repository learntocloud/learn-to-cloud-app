"""Tests for certificates service."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.certificates_service import (
    CertificateAlreadyExistsError,
    NotEligibleError,
    check_eligibility,
    create_certificate,
    generate_verification_code,
    get_certificate_by_id,
    get_user_certificates_with_eligibility,
    verify_certificate,
    verify_certificate_with_message,
)
from tests.factories import CertificateFactory, UserFactory

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration


class TestGenerateVerificationCode:
    """Tests for generate_verification_code."""

    def test_generates_code_with_correct_format(self):
        """Test that verification code has correct format."""
        code = generate_verification_code("user-123", "full_completion")
        assert code.startswith("LTC-")
        parts = code.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 12  # Hash part
        assert len(parts[2]) == 8  # Random part

    def test_generates_unique_codes(self):
        """Test that generated codes are unique."""
        codes = set()
        for _ in range(100):
            code = generate_verification_code("user-123", "full_completion")
            codes.add(code)
        # All codes should be unique (timestamp + random makes collisions unlikely)
        assert len(codes) == 100

    def test_different_users_get_different_codes(self):
        """Test that different users get different codes."""
        code1 = generate_verification_code("user-1", "full_completion")
        code2 = generate_verification_code("user-2", "full_completion")
        assert code1 != code2


class TestCheckEligibility:
    """Tests for check_eligibility."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_raises_for_unknown_certificate_type(
        self, db_session: AsyncSession, user
    ):
        """Test that unknown certificate type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown certificate type"):
            await check_eligibility(db_session, user.id, "unknown_type")

    @patch("services.certificates_service.fetch_user_progress")
    async def test_not_eligible_when_phases_incomplete(
        self, mock_progress, db_session: AsyncSession, user
    ):
        """Test user is not eligible when phases are incomplete."""
        mock_progress.return_value = AsyncMock(
            phases_completed=3,
            total_phases=7,
            is_program_complete=False,
        )

        result = await check_eligibility(db_session, user.id, "full_completion")

        assert result.is_eligible is False
        assert result.phases_completed == 3
        assert result.total_phases == 7
        assert "Complete all phases" in result.message

    @patch("services.certificates_service.fetch_user_progress")
    async def test_eligible_when_program_complete(
        self, mock_progress, db_session: AsyncSession, user
    ):
        """Test user is eligible when program is complete."""
        mock_progress.return_value = AsyncMock(
            phases_completed=7,
            total_phases=7,
            is_program_complete=True,
        )

        result = await check_eligibility(db_session, user.id, "full_completion")

        assert result.is_eligible is True
        assert "Congratulations" in result.message

    @patch("services.certificates_service.fetch_user_progress")
    async def test_returns_existing_certificate(
        self, mock_progress, db_session: AsyncSession, user
    ):
        """Test that existing certificate is returned."""
        # Create existing certificate
        cert = CertificateFactory.build(
            user_id=user.id, certificate_type="full_completion"
        )
        db_session.add(cert)
        await db_session.flush()

        mock_progress.return_value = AsyncMock(
            phases_completed=7,
            total_phases=7,
            is_program_complete=True,
        )

        result = await check_eligibility(db_session, user.id, "full_completion")

        assert result.existing_certificate is not None
        assert "already issued" in result.message


class TestCreateCertificate:
    """Tests for create_certificate."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    @patch("services.certificates_service.fetch_user_progress")
    async def test_raises_when_already_exists(
        self, mock_progress, db_session: AsyncSession, user
    ):
        """Test raises CertificateAlreadyExistsError if certificate exists."""
        cert = CertificateFactory.build(
            user_id=user.id, certificate_type="full_completion"
        )
        db_session.add(cert)
        await db_session.flush()

        mock_progress.return_value = AsyncMock(
            phases_completed=7,
            total_phases=7,
            is_program_complete=True,
        )

        with pytest.raises(CertificateAlreadyExistsError):
            await create_certificate(
                db_session, user.id, "full_completion", "Test User"
            )

    @patch("services.certificates_service.fetch_user_progress")
    async def test_raises_when_not_eligible(
        self, mock_progress, db_session: AsyncSession, user
    ):
        """Test raises NotEligibleError when user not eligible."""
        mock_progress.return_value = AsyncMock(
            phases_completed=3,
            total_phases=7,
            is_program_complete=False,
        )

        with pytest.raises(NotEligibleError) as exc_info:
            await create_certificate(
                db_session, user.id, "full_completion", "Test User"
            )

        assert exc_info.value.phases_completed == 3
        assert exc_info.value.total_phases == 7

    @patch("services.certificates_service.fetch_user_progress")
    async def test_creates_certificate_when_eligible(
        self, mock_progress, db_session: AsyncSession, user
    ):
        """Test creates certificate when user is eligible."""
        mock_progress.return_value = AsyncMock(
            phases_completed=7,
            total_phases=7,
            is_program_complete=True,
        )

        result = await create_certificate(
            db_session, user.id, "full_completion", "Test User"
        )

        assert result.certificate is not None
        assert result.certificate.recipient_name == "Test User"
        assert result.certificate.certificate_type == "full_completion"
        assert result.verification_code is not None


class TestGetCertificateById:
    """Tests for get_certificate_by_id."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_returns_certificate_for_owner(self, db_session: AsyncSession, user):
        """Test returns certificate when user owns it."""
        cert = CertificateFactory.build(user_id=user.id)
        db_session.add(cert)
        await db_session.flush()

        result = await get_certificate_by_id(db_session, cert.id, user.id)

        assert result is not None
        assert result.id == cert.id

    async def test_returns_none_for_non_owner(self, db_session: AsyncSession, user):
        """Test returns None when user doesn't own certificate."""
        cert = CertificateFactory.build(user_id=user.id)
        db_session.add(cert)
        await db_session.flush()

        result = await get_certificate_by_id(db_session, cert.id, "other-user")

        assert result is None

    async def test_returns_none_for_nonexistent(self, db_session: AsyncSession, user):
        """Test returns None for non-existent certificate."""
        result = await get_certificate_by_id(db_session, 99999, user.id)
        assert result is None


class TestGetUserCertificatesWithEligibility:
    """Tests for get_user_certificates_with_eligibility."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    @patch("services.certificates_service.fetch_user_progress")
    async def test_returns_certificates_and_eligibility(
        self, mock_progress, db_session: AsyncSession, user
    ):
        """Test returns certificates list and eligibility status."""
        cert = CertificateFactory.build(user_id=user.id, certificate_type="test_type")
        db_session.add(cert)
        await db_session.flush()

        mock_progress.return_value = AsyncMock(
            phases_completed=3,
            total_phases=7,
            is_program_complete=False,
        )

        certs, eligible = await get_user_certificates_with_eligibility(
            db_session, user.id
        )

        assert len(certs) == 1
        assert eligible is False  # Not complete yet


class TestVerifyCertificate:
    """Tests for verify_certificate."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_returns_certificate_for_valid_code(
        self, db_session: AsyncSession, user
    ):
        """Test returns certificate for valid verification code."""
        cert = CertificateFactory.build(
            user_id=user.id, verification_code="LTC-VALID123-CODE"
        )
        db_session.add(cert)
        await db_session.flush()

        result = await verify_certificate(db_session, "LTC-VALID123-CODE")

        assert result is not None
        assert result.verification_code == "LTC-VALID123-CODE"

    async def test_returns_none_for_invalid_code(self, db_session: AsyncSession):
        """Test returns None for invalid verification code."""
        result = await verify_certificate(db_session, "INVALID-CODE")
        assert result is None


class TestVerifyCertificateWithMessage:
    """Tests for verify_certificate_with_message."""

    @pytest.fixture
    async def user(self, db_session: AsyncSession):
        """Create a test user."""
        user = UserFactory.build()
        db_session.add(user)
        await db_session.flush()
        return user

    async def test_returns_valid_result_for_valid_code(
        self, db_session: AsyncSession, user
    ):
        """Test returns valid result for valid verification code."""
        cert = CertificateFactory.build(
            user_id=user.id,
            verification_code="LTC-VALID456-CODE",
            certificate_type="full_completion",
        )
        db_session.add(cert)
        await db_session.flush()

        result = await verify_certificate_with_message(db_session, "LTC-VALID456-CODE")

        assert result.is_valid is True
        assert result.certificate is not None
        assert "Valid certificate" in result.message

    async def test_returns_invalid_result_for_invalid_code(
        self, db_session: AsyncSession
    ):
        """Test returns invalid result for invalid verification code."""
        result = await verify_certificate_with_message(db_session, "INVALID-CODE")

        assert result.is_valid is False
        assert result.certificate is None
        assert "not found" in result.message


class TestNotEligibleError:
    """Tests for NotEligibleError exception."""

    def test_default_message(self):
        """Test default error message."""
        exc = NotEligibleError(phases_completed=3, total_phases=7)
        assert "3/7" in str(exc)

    def test_custom_message(self):
        """Test custom error message."""
        exc = NotEligibleError(
            phases_completed=3,
            total_phases=7,
            message="Custom message",
        )
        assert str(exc) == "Custom message"
