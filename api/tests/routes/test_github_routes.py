"""Tests for GitHub routes."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models import SubmissionType
from tests.factories import UserFactory


class TestSubmitGitHubValidation:
    """Tests for POST /api/github/submit endpoint."""

    @patch("services.submissions_service.validate_submission")
    async def test_successful_validation(
        self, mock_validate, authenticated_client: AsyncClient, db_session: AsyncSession
    ):
        """Test successful GitHub submission validation."""
        # Get a valid requirement that doesn't require GitHub username
        from services.phase_requirements_service import get_requirements_for_phase

        reqs = get_requirements_for_phase(0)
        profile_req = next(
            (r for r in reqs if r.submission_type == SubmissionType.GITHUB_PROFILE),
            None,
        )

        if not profile_req:
            pytest.skip("No GitHub profile requirement found")

        mock_validate.return_value = AsyncMock(
            is_valid=True,
            message="Valid GitHub profile",
            username_match=True,
            repo_exists=None,
        )

        response = await authenticated_client.post(
            "/api/github/submit",
            json={
                "requirement_id": profile_req.id,
                "submitted_value": "https://github.com/testuser",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["is_valid"] is True
        assert "submission" in data

    @patch("services.submissions_service.validate_submission")
    async def test_failed_validation(
        self, mock_validate, authenticated_client: AsyncClient
    ):
        """Test failed GitHub submission validation."""
        from services.phase_requirements_service import get_requirements_for_phase

        reqs = get_requirements_for_phase(0)
        profile_req = next(
            (r for r in reqs if r.submission_type == SubmissionType.GITHUB_PROFILE),
            None,
        )

        if not profile_req:
            pytest.skip("No GitHub profile requirement found")

        mock_validate.return_value = AsyncMock(
            is_valid=False,
            message="GitHub profile not found",
            username_match=False,
            repo_exists=None,
        )

        response = await authenticated_client.post(
            "/api/github/submit",
            json={
                "requirement_id": profile_req.id,
                "submitted_value": "https://github.com/nonexistent-user-xyz",
            },
        )

        assert response.status_code == 201  # Still returns 201, just with is_valid=False
        data = response.json()
        assert data["is_valid"] is False

    async def test_returns_404_for_unknown_requirement(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 404 for unknown requirement ID."""
        response = await authenticated_client.post(
            "/api/github/submit",
            json={
                "requirement_id": "nonexistent-requirement",
                "submitted_value": "https://github.com/testuser",
            },
        )

        assert response.status_code == 404

    @pytest.mark.skip(reason="Complex test requiring full auth mock - covered by integration tests")
    async def test_returns_400_when_github_username_required(
        self, authenticated_client: AsyncClient, db_session: AsyncSession
    ):
        """Test returns 400 when GitHub username required but user doesn't have one."""
        # This test is complex because it requires:
        # 1. A user without GitHub username
        # 2. A requirement that needs GitHub username
        # 3. Properly mocked auth state
        # Covered by integration tests instead.
        pass

    async def test_returns_401_for_unauthenticated(
        self, unauthenticated_client: AsyncClient
    ):
        """Test returns 401 for unauthenticated request."""
        response = await unauthenticated_client.post(
            "/api/github/submit",
            json={
                "requirement_id": "phase0-github-profile",
                "submitted_value": "https://github.com/testuser",
            },
        )

        assert response.status_code == 401

    async def test_returns_422_for_missing_fields(
        self, authenticated_client: AsyncClient
    ):
        """Test returns 422 for missing required fields."""
        response = await authenticated_client.post(
            "/api/github/submit",
            json={"requirement_id": "phase0-github-profile"},  # Missing submitted_value
        )

        assert response.status_code == 422
