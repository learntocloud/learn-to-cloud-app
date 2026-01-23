"""Tests for certificates routes."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration

from models import Certificate
from repositories.user_repository import UserRepository
from tests.factories import CertificateFactory, create_async


async def _clear_user_certificates(app: FastAPI, user_id: str) -> None:
    async with app.state.session_maker() as session:
        await session.execute(delete(Certificate).where(Certificate.user_id == user_id))
        await session.commit()


class TestGenerateCertificate:
    """Tests for POST /api/certificates endpoint."""

    @patch("services.certificates_service.fetch_user_progress")
    async def test_creates_certificate_when_eligible(
        self, mock_progress, authenticated_client: AsyncClient, app: FastAPI
    ):
        """Test creates certificate when user is eligible."""
        await _clear_user_certificates(app, "user_test_123456789")
        # Mock the progress object with proper structure
        progress_mock = MagicMock()
        progress_mock.phases_completed = 7
        progress_mock.total_phases = 7
        progress_mock.is_program_complete = True
        mock_progress.return_value = progress_mock

        response = await authenticated_client.post(
            "/api/certificates",
            json={
                "certificate_type": "full_completion",
                "recipient_name": "Test User",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["recipient_name"] == "Test User"
        assert data["certificate_type"] == "full_completion"
        assert "verification_code" in data

    @patch("services.certificates_service.fetch_user_progress")
    async def test_returns_403_when_not_eligible(
        self, mock_progress, authenticated_client: AsyncClient, app: FastAPI
    ):
        """Test returns 403 when user is not eligible."""
        await _clear_user_certificates(app, "user_test_123456789")
        progress_mock = MagicMock()
        progress_mock.phases_completed = 3
        progress_mock.total_phases = 7
        progress_mock.is_program_complete = False
        mock_progress.return_value = progress_mock

        response = await authenticated_client.post(
            "/api/certificates",
            json={
                "certificate_type": "full_completion",
                "recipient_name": "Test User",
            },
        )

        assert response.status_code == 403

    @patch("services.certificates_service.fetch_user_progress")
    async def test_returns_409_when_already_exists(
        self,
        mock_progress,
        authenticated_client: AsyncClient,
        app: FastAPI,
        test_user_id: str,
    ):
        """Test returns 409 when certificate already exists."""
        await _clear_user_certificates(app, test_user_id)
        progress_mock = MagicMock()
        progress_mock.phases_completed = 7
        progress_mock.total_phases = 7
        progress_mock.is_program_complete = True
        mock_progress.return_value = progress_mock

        async with app.state.session_maker() as session:
            user_repo = UserRepository(session)
            await user_repo.get_or_create(test_user_id)
            await create_async(
                CertificateFactory,
                session,
                user_id=test_user_id,
                certificate_type="full_completion",
                recipient_name="Test User",
                phases_completed=7,
                total_phases=7,
            )
            await session.commit()

        response = await authenticated_client.post(
            "/api/certificates",
            json={
                "certificate_type": "full_completion",
                "recipient_name": "Test User",
            },
        )

        assert response.status_code == 409

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.post(
            "/api/certificates",
            json={
                "certificate_type": "full_completion",
                "recipient_name": "Test User",
            },
        )

        assert response.status_code == 401


class TestGetUserCertificates:
    """Tests for GET /api/certificates endpoint."""

    @patch("services.certificates_service.fetch_user_progress")
    async def test_returns_certificates_list(
        self, mock_progress, authenticated_client: AsyncClient
    ):
        """Test returns list of user certificates."""
        progress_mock = MagicMock()
        progress_mock.phases_completed = 3
        progress_mock.total_phases = 7
        progress_mock.is_program_complete = False
        mock_progress.return_value = progress_mock

        response = await authenticated_client.get("/api/certificates")

        assert response.status_code == 200
        data = response.json()
        assert "certificates" in data
        assert "full_completion_eligible" in data

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.get("/api/certificates")

        assert response.status_code == 401


class TestCheckEligibility:
    """Tests for GET /api/certificates/eligibility/{certificate_type} endpoint."""

    @patch("services.certificates_service.fetch_user_progress")
    async def test_returns_eligibility_status(
        self, mock_progress, authenticated_client: AsyncClient
    ):
        """Test returns eligibility status."""
        progress_mock = MagicMock()
        progress_mock.phases_completed = 5
        progress_mock.total_phases = 7
        progress_mock.is_program_complete = False
        mock_progress.return_value = progress_mock

        response = await authenticated_client.get(
            "/api/certificates/eligibility/full_completion"
        )

        assert response.status_code == 200
        data = response.json()
        assert "is_eligible" in data
        assert "phases_completed" in data
        assert "total_phases" in data

    async def test_returns_400_for_invalid_type(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 400 for invalid certificate type."""
        response = await authenticated_client.get(
            "/api/certificates/eligibility/invalid_type"
        )

        assert response.status_code == 400


class TestVerifyCertificate:
    """Tests for GET /api/certificates/verify/{verification_code} endpoint."""

    async def test_returns_valid_for_existing_certificate(
        self, unauthenticated_client: AsyncClient, app: FastAPI
    ):
        """Test returns valid for existing certificate (public endpoint)."""
        verification_code = f"LTC-VALID-{uuid4().hex.upper()}"

        async with app.state.session_maker() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_or_create(f"user_verify_{uuid4().hex[:12]}")
            certificate = await create_async(
                CertificateFactory,
                session,
                user_id=user.id,
                verification_code=verification_code,
                certificate_type="full_completion",
                recipient_name="Test User",
                phases_completed=7,
                total_phases=7,
            )
            await session.commit()

        response = await unauthenticated_client.get(
            f"/api/certificates/verify/{verification_code}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["certificate"] is not None
        assert data["certificate"]["id"] == certificate.id
        assert data["certificate"]["verification_code"] == verification_code

    async def test_returns_invalid_for_nonexistent_code(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns invalid for non-existent verification code."""
        response = await unauthenticated_client.get(
            "/api/certificates/verify/INVALID-CODE-12345"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert data["certificate"] is None


class TestGetCertificatePdf:
    """Tests for GET /api/certificates/{certificate_id}/pdf endpoint."""

    async def test_returns_404_for_nonexistent_certificate(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for non-existent certificate."""
        response = await authenticated_client.get("/api/certificates/99999/pdf")

        assert response.status_code == 404

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.get("/api/certificates/1/pdf")

        assert response.status_code == 401


class TestGetCertificatePng:
    """Tests for GET /api/certificates/{certificate_id}/png endpoint."""

    async def test_returns_404_for_nonexistent_certificate(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for non-existent certificate."""
        response = await authenticated_client.get("/api/certificates/99999/png")

        assert response.status_code == 404

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.get("/api/certificates/1/png")

        assert response.status_code == 401
