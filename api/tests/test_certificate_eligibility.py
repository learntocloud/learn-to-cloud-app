"""Tests for certificate eligibility and generation.

These tests use an isolated in-memory SQLite database,
so they don't affect your development database.
"""

import pytest
from sqlalchemy import select

from models import Certificate
from services.certificates import generate_verification_code
from services.progress import TOTAL_PHASES


class TestCertificateEligibility:
    """Test certificate eligibility checking logic."""

    @pytest.mark.asyncio
    async def test_user_not_eligible_with_no_progress(self, db_session, test_user):
        """User with no progress should not be eligible for certificate."""
        from services.certificates import check_eligibility

        result = await check_eligibility(db_session, test_user.id, "full_completion")

        assert result.is_eligible is False
        assert result.phases_completed == 0
        assert result.total_phases == TOTAL_PHASES
        assert result.completion_percentage == 0.0
        assert result.existing_certificate is None

    @pytest.mark.asyncio
    async def test_user_not_eligible_with_partial_progress(
        self, db_session, test_user_with_progress
    ):
        """User with partial progress should not be eligible."""
        from services.certificates import check_eligibility

        result = await check_eligibility(
            db_session, test_user_with_progress.id, "full_completion"
        )

        assert result.is_eligible is False
        assert result.phases_completed == 3
        assert result.total_phases == TOTAL_PHASES
        assert result.completion_percentage == pytest.approx(42.86, rel=0.1)
        assert result.existing_certificate is None

    @pytest.mark.asyncio
    async def test_user_eligible_with_full_completion(
        self, db_session, test_user_full_completion
    ):
        """User who completed all phases should be eligible."""
        from services.certificates import check_eligibility

        result = await check_eligibility(
            db_session, test_user_full_completion.id, "full_completion"
        )

        assert result.is_eligible is True
        assert result.phases_completed == TOTAL_PHASES
        assert result.total_phases == TOTAL_PHASES
        assert result.completion_percentage == 100.0
        assert result.existing_certificate is None


class TestCertificateGeneration:
    """Test certificate generation."""

    @pytest.mark.asyncio
    async def test_generate_certificate_for_eligible_user(
        self, db_session, test_user_full_completion
    ):
        """Eligible user can generate a certificate."""
        from datetime import UTC, datetime

        verification_code = generate_verification_code(
            test_user_full_completion.id, "full_completion"
        )

        certificate = Certificate(
            user_id=test_user_full_completion.id,
            certificate_type="full_completion",
            verification_code=verification_code,
            recipient_name="Test User",
            issued_at=datetime.now(UTC),
            phases_completed=TOTAL_PHASES,
            total_phases=TOTAL_PHASES,
        )
        db_session.add(certificate)
        await db_session.commit()

        result = await db_session.execute(
            select(Certificate).where(
                Certificate.user_id == test_user_full_completion.id
            )
        )
        saved_cert = result.scalar_one()

        assert saved_cert.certificate_type == "full_completion"
        assert saved_cert.phases_completed == TOTAL_PHASES
        assert saved_cert.verification_code.startswith("LTC-")

    @pytest.mark.asyncio
    async def test_existing_certificate_detected(
        self, db_session, test_user_full_completion
    ):
        """Existing certificate should be detected in eligibility check."""
        from datetime import UTC, datetime

        from services.certificates import check_eligibility

        certificate = Certificate(
            user_id=test_user_full_completion.id,
            certificate_type="full_completion",
            verification_code="LTC-EXISTING-TEST",
            recipient_name="Test User",
            issued_at=datetime.now(UTC),
            phases_completed=TOTAL_PHASES,
            total_phases=TOTAL_PHASES,
        )
        db_session.add(certificate)
        await db_session.commit()

        result = await check_eligibility(
            db_session, test_user_full_completion.id, "full_completion"
        )

        assert result.is_eligible is True
        assert result.existing_certificate is not None
        assert result.existing_certificate.verification_code == "LTC-EXISTING-TEST"


class TestVerificationCode:
    """Test verification code generation."""

    def test_verification_code_format(self):
        """Verification codes should have correct format."""
        code = generate_verification_code("user123", "full_completion")

        assert code.startswith("LTC-")
        parts = code.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 12
        assert all(c in "0123456789ABCDEF" for c in parts[1])
        assert len(parts[2]) == 8
        assert all(c in "0123456789ABCDEF" for c in parts[2])

    def test_verification_codes_are_unique(self):
        """Each call should generate a unique code."""
        codes = [
            generate_verification_code("user123", "full_completion") for _ in range(10)
        ]
        assert len(set(codes)) == 10
