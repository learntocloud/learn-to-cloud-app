"""Tests for GitHub routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

# Mark all tests in this module as integration tests (database required)
pytestmark = pytest.mark.integration

from models import SubmissionType
from repositories.user_repository import UserRepository
from schemas import ClerkUserData


class TestSubmitGitHubValidation:
    """Tests for POST /api/github/submit endpoint."""

    @patch("services.submissions_service.validate_submission")
    async def test_successful_validation(
        self, mock_validate, authenticated_client: AsyncClient
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

        assert (
            response.status_code == 201
        )  # Still returns 201, just with is_valid=False
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

    @patch("services.users_service.fetch_user_data")
    async def test_returns_400_when_github_username_required(
        self,
        mock_fetch_user_data,
        app: FastAPI,
        authenticated_client: AsyncClient,
        test_user_id: str,
    ):
        """Test returns 400 when GitHub username required but user doesn't have one."""
        from services.phase_requirements_service import get_requirements_for_phase

        requirements = get_requirements_for_phase(1)
        requirement = next(
            (
                req
                for req in requirements
                if req.submission_type
                in (
                    SubmissionType.PROFILE_README,
                    SubmissionType.REPO_FORK,
                    SubmissionType.CTF_TOKEN,
                )
            ),
            None,
        )
        assert requirement is not None, "Expected a GitHub-username requirement"

        mock_fetch_user_data.return_value = ClerkUserData(
            email="test@example.com",
            first_name="Test",
            last_name="User",
            avatar_url="https://example.com/avatar.png",
            github_username=None,
        )

        async with app.state.session_maker() as session:
            user_repo = UserRepository(session)
            await user_repo.get_or_create(test_user_id)
            await session.commit()

        response = await authenticated_client.post(
            "/api/github/submit",
            json={
                "requirement_id": requirement.id,
                "submitted_value": requirement.example_url or "ctf-token-123",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "link your GitHub account" in data["detail"]

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
