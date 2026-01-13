"""Tests for certificate eligibility and generation.

These tests use an isolated in-memory SQLite database,
so they don't affect your development database.
"""

import pytest
from sqlalchemy import select

from shared.certificates import TOTAL_TOPICS, generate_verification_code
from shared.models import Certificate


class TestCertificateEligibility:
    """Test certificate eligibility checking logic."""

    @pytest.mark.asyncio
    async def test_user_not_eligible_with_no_progress(
        self, db_session, test_user
    ):
        """User with no progress should not be eligible for certificate."""
        from routes.certificates import _check_eligibility

        is_eligible, topics_completed, total_topics, percentage, existing = (
            await _check_eligibility(db_session, test_user.id, "full_completion")
        )

        assert is_eligible is False
        assert topics_completed == 0
        assert total_topics == TOTAL_TOPICS  # 40
        assert percentage == 0.0
        assert existing is None

    @pytest.mark.asyncio
    async def test_user_not_eligible_with_partial_progress(
        self, db_session, test_user_with_progress
    ):
        """User with partial progress should not be eligible."""
        from routes.certificates import _check_eligibility

        is_eligible, topics_completed, total_topics, percentage, existing = (
            await _check_eligibility(
                db_session, test_user_with_progress.id, "full_completion"
            )
        )

        assert is_eligible is False
        assert topics_completed == 3  # 3 topics completed
        assert total_topics == TOTAL_TOPICS
        assert percentage == pytest.approx(7.5, rel=0.1)  # 3/40 = 7.5%
        assert existing is None

    @pytest.mark.asyncio
    async def test_user_eligible_with_full_completion(
        self, db_session, test_user_full_completion
    ):
        """User who completed all topics should be eligible."""
        from routes.certificates import _check_eligibility

        is_eligible, topics_completed, total_topics, percentage, existing = (
            await _check_eligibility(
                db_session, test_user_full_completion.id, "full_completion"
            )
        )

        assert is_eligible is True
        assert topics_completed == 40
        assert total_topics == TOTAL_TOPICS
        assert percentage == 100.0
        assert existing is None


class TestCertificateGeneration:
    """Test certificate generation."""

    @pytest.mark.asyncio
    async def test_generate_certificate_for_eligible_user(
        self, db_session, test_user_full_completion
    ):
        """Eligible user can generate a certificate."""
        from datetime import UTC, datetime

        # Create certificate directly (simulating the endpoint logic)
        verification_code = generate_verification_code(
            test_user_full_completion.id, "full_completion"
        )

        certificate = Certificate(
            user_id=test_user_full_completion.id,
            certificate_type="full_completion",
            verification_code=verification_code,
            recipient_name="Test User",
            issued_at=datetime.now(UTC),
            topics_completed=40,
            total_topics=40,
        )
        db_session.add(certificate)
        await db_session.commit()

        # Verify it was created
        result = await db_session.execute(
            select(Certificate).where(
                Certificate.user_id == test_user_full_completion.id
            )
        )
        saved_cert = result.scalar_one()

        assert saved_cert.certificate_type == "full_completion"
        assert saved_cert.topics_completed == 40
        assert saved_cert.verification_code.startswith("LTC-")

    @pytest.mark.asyncio
    async def test_existing_certificate_detected(
        self, db_session, test_user_full_completion
    ):
        """Existing certificate should be detected in eligibility check."""
        from datetime import UTC, datetime

        from routes.certificates import _check_eligibility

        # Create an existing certificate
        certificate = Certificate(
            user_id=test_user_full_completion.id,
            certificate_type="full_completion",
            verification_code="LTC-EXISTING-TEST",
            recipient_name="Test User",
            issued_at=datetime.now(UTC),
            topics_completed=40,
            total_topics=40,
        )
        db_session.add(certificate)
        await db_session.commit()

        # Check eligibility - should detect existing certificate
        is_eligible, _, _, _, existing = await _check_eligibility(
            db_session, test_user_full_completion.id, "full_completion"
        )

        assert is_eligible is True  # Still eligible based on progress
        assert existing is not None  # But already has certificate
        assert existing.verification_code == "LTC-EXISTING-TEST"


class TestVerificationCode:
    """Test verification code generation."""

    def test_verification_code_format(self):
        """Verification codes should have correct format."""
        code = generate_verification_code("user123", "full_completion")

        assert code.startswith("LTC-")
        parts = code.split("-")
        assert len(parts) == 3
        # Hash part should be 12 chars uppercase hex
        assert len(parts[1]) == 12
        assert parts[1].isupper()
        # Random part should be 8 chars uppercase hex
        assert len(parts[2]) == 8
        assert parts[2].isupper()

    def test_verification_codes_are_unique(self):
        """Each call should generate a unique code."""
        codes = [
            generate_verification_code("user123", "full_completion")
            for _ in range(10)
        ]
        assert len(set(codes)) == 10  # All unique
