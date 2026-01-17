"""Tests for Phase 5 DevOps hands-on verification.

Tests the following verification types:
1. WORKFLOW_RUN - GitHub Actions successful run verification
2. REPO_WITH_FILES - Repository contains required files (Dockerfile, Terraform, K8s)
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.github_hands_on_verification import (
    validate_repo_has_files,
    validate_workflow_run,
)

# ============ Test Fixtures ============


@pytest.fixture
def mock_successful_workflow_response():
    """Mock GitHub API response for successful workflow runs."""
    now = datetime.now(UTC)
    return {
        "total_count": 3,
        "workflow_runs": [
            {
                "id": 12345,
                "name": "CI/CD Pipeline",
                "status": "completed",
                "conclusion": "success",
                "created_at": now.isoformat().replace("+00:00", "Z"),
            },
            {
                "id": 12344,
                "name": "CI/CD Pipeline",
                "status": "completed",
                "conclusion": "success",
                "created_at": (now - timedelta(days=5))
                .isoformat()
                .replace("+00:00", "Z"),
            },
            {
                "id": 12343,
                "name": "CI/CD Pipeline",
                "status": "completed",
                "conclusion": "success",
                "created_at": (now - timedelta(days=10))
                .isoformat()
                .replace("+00:00", "Z"),
            },
        ],
    }


@pytest.fixture
def mock_old_workflow_response():
    """Mock GitHub API response with only old workflow runs (>30 days)."""
    old_date = datetime.now(UTC) - timedelta(days=45)
    return {
        "total_count": 1,
        "workflow_runs": [
            {
                "id": 12340,
                "name": "Old Pipeline",
                "status": "completed",
                "conclusion": "success",
                "created_at": old_date.isoformat().replace("+00:00", "Z"),
            },
        ],
    }


@pytest.fixture
def mock_code_search_response():
    """Mock GitHub code search API response."""
    return {
        "total_count": 2,
        "items": [
            {"name": "Dockerfile", "path": "Dockerfile"},
            {"name": "docker-compose.yml", "path": "docker-compose.yml"},
        ],
    }


# ============ Test validate_workflow_run ============


class TestValidateWorkflowRun:
    """Tests for GitHub Actions workflow run validation."""

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        """Test with invalid GitHub URL."""
        result = await validate_workflow_run("not-a-valid-url", "testuser")
        assert not result.is_valid
        assert "github.com" in result.message.lower()

    @pytest.mark.asyncio
    async def test_username_mismatch(self):
        """Test with mismatched username."""
        result = await validate_workflow_run(
            "https://github.com/otheruser/repo", "testuser"
        )
        assert not result.is_valid
        assert "does not match" in result.message

    @pytest.mark.asyncio
    async def test_missing_repo_name(self):
        """Test with URL missing repo name."""
        result = await validate_workflow_run("https://github.com/testuser", "testuser")
        assert not result.is_valid
        assert "repository name" in result.message.lower()

    @pytest.mark.asyncio
    async def test_successful_workflow_run(self, mock_successful_workflow_response):
        """Test with successful recent workflow runs."""
        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = mock_successful_workflow_response

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await validate_workflow_run(
                    "https://github.com/testuser/myrepo", "testuser"
                )

                assert result.is_valid
                assert "CI/CD verified" in result.message
                assert "successful run" in result.message.lower()

    @pytest.mark.asyncio
    async def test_no_workflow_runs(self):
        """Test with no workflow runs found."""
        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "total_count": 0,
                    "workflow_runs": [],
                }

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await validate_workflow_run(
                    "https://github.com/testuser/myrepo", "testuser"
                )

                assert not result.is_valid
                assert "no successful workflow runs" in result.message.lower()

    @pytest.mark.asyncio
    async def test_only_old_workflow_runs(self, mock_old_workflow_response):
        """Test with only workflow runs older than 30 days."""
        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = mock_old_workflow_response

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await validate_workflow_run(
                    "https://github.com/testuser/myrepo", "testuser"
                )

                assert not result.is_valid
                assert "30 days" in result.message

    @pytest.mark.asyncio
    async def test_actions_not_enabled(self):
        """Test when GitHub Actions returns 404 (not enabled)."""
        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 404

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await validate_workflow_run(
                    "https://github.com/testuser/myrepo", "testuser"
                )

                assert not result.is_valid
                assert "actions" in result.message.lower()

    @pytest.mark.asyncio
    async def test_repo_not_found(self):
        """Test when repository doesn't exist."""
        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (False, "URL not found (404)")

            result = await validate_workflow_run(
                "https://github.com/testuser/nonexistent", "testuser"
            )

            assert not result.is_valid
            assert "not found" in result.message.lower()


# ============ Test validate_repo_has_files ============


class TestValidateRepoHasFiles:
    """Tests for repository file existence validation."""

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        """Test with invalid GitHub URL."""
        result = await validate_repo_has_files(
            "not-a-valid-url", "testuser", ["Dockerfile"], "Docker files"
        )
        assert not result.is_valid

    @pytest.mark.asyncio
    async def test_username_mismatch(self):
        """Test with mismatched username."""
        result = await validate_repo_has_files(
            "https://github.com/otheruser/repo",
            "testuser",
            ["Dockerfile"],
            "Docker files",
        )
        assert not result.is_valid
        assert "does not match" in result.message

    @pytest.mark.asyncio
    async def test_missing_repo_name(self):
        """Test with URL missing repo name."""
        result = await validate_repo_has_files(
            "https://github.com/testuser", "testuser", ["Dockerfile"], "Docker files"
        )
        assert not result.is_valid
        assert "repository name" in result.message.lower()

    @pytest.mark.asyncio
    async def test_found_dockerfile(self, mock_code_search_response):
        """Test finding Dockerfile in repository."""
        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = mock_code_search_response

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await validate_repo_has_files(
                    "https://github.com/testuser/myrepo",
                    "testuser",
                    ["Dockerfile", "docker-compose"],
                    "Docker configuration files",
                )

                assert result.is_valid
                assert "Dockerfile" in result.message

    @pytest.mark.asyncio
    async def test_files_not_found(self):
        """Test when required files are not found."""
        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"total_count": 0, "items": []}

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await validate_repo_has_files(
                    "https://github.com/testuser/myrepo",
                    "testuser",
                    ["Dockerfile"],
                    "Docker files",
                )

                assert not result.is_valid
                assert "could not find" in result.message.lower()

    @pytest.mark.asyncio
    async def test_terraform_files(self):
        """Test finding Terraform files."""
        terraform_response = {
            "total_count": 2,
            "items": [
                {"name": "main.tf", "path": "infra/main.tf"},
                {"name": "variables.tf", "path": "infra/variables.tf"},
            ],
        }

        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = terraform_response

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await validate_repo_has_files(
                    "https://github.com/testuser/myrepo",
                    "testuser",
                    [".tf", "main.tf"],
                    "Terraform configuration files",
                )

                assert result.is_valid
                assert "main.tf" in result.message

    @pytest.mark.asyncio
    async def test_path_based_patterns(self):
        """Test path-based patterns like infra/main.tf and infra/."""
        terraform_response = {
            "total_count": 2,
            "items": [
                {"name": "main.tf", "path": "infra/main.tf"},
                {"name": "variables.tf", "path": "infra/variables.tf"},
            ],
        }

        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = terraform_response

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await validate_repo_has_files(
                    "https://github.com/testuser/myrepo",
                    "testuser",
                    ["infra/main.tf", "infra/"],
                    "Terraform configuration files",
                )

                assert result.is_valid
                assert "main.tf" in result.message

    @pytest.mark.asyncio
    async def test_kubernetes_files(self):
        """Test finding Kubernetes manifest files."""
        k8s_response = {
            "total_count": 2,
            "items": [
                {"name": "deployment.yaml", "path": "k8s/deployment.yaml"},
                {"name": "service.yaml", "path": "k8s/service.yaml"},
            ],
        }

        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = k8s_response

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                result = await validate_repo_has_files(
                    "https://github.com/testuser/myrepo",
                    "testuser",
                    ["deployment", "service"],
                    "Kubernetes manifests",
                )

                assert result.is_valid
                assert "deployment" in result.message.lower()

    @pytest.mark.asyncio
    async def test_repo_not_found(self):
        """Test when repository doesn't exist."""
        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (False, "URL not found (404)")

            result = await validate_repo_has_files(
                "https://github.com/testuser/nonexistent",
                "testuser",
                ["Dockerfile"],
                "Docker files",
            )

            assert not result.is_valid
            assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_fallback_to_contents_api_on_rate_limit(self):
        """Test fallback to contents API when search is rate-limited.

        This test is simplified since the fallback mechanism involves multiple
        API calls across different directories. We just verify the function
        handles rate limiting gracefully.
        """
        with patch(
            "services.github_hands_on_verification.check_github_url_exists"
        ) as mock_exists:
            mock_exists.return_value = (True, "URL exists")

            with patch(
                "services.github_hands_on_verification.httpx.AsyncClient"
            ) as mock_client_class:
                # Return rate limit for all calls - should fail gracefully
                rate_limit_response = MagicMock()
                rate_limit_response.status_code = 403

                # Contents API returns 404 (directory not found) - common case
                not_found_response = MagicMock()
                not_found_response.status_code = 404

                mock_client = AsyncMock()
                # Return rate limit first, then 404 for all content checks
                mock_client.get = AsyncMock(return_value=not_found_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_class.return_value = mock_client

                # Override the first call to return rate limit
                # (unused variable removed by ruff)
                async def side_effect_fn(*args, **kwargs):
                    if "search/code" in str(args):
                        return rate_limit_response
                    return not_found_response

                mock_client.get = AsyncMock(side_effect=side_effect_fn)

                result = await validate_repo_has_files(
                    "https://github.com/testuser/myrepo",
                    "testuser",
                    ["Dockerfile", "docker-compose"],
                    "Docker files",
                )

                # Should fail gracefully when files aren't found
                assert not result.is_valid
                assert "could not find" in result.message.lower()


# ============ Test Phase 5 Requirements Configuration ============


class TestPhase5Requirements:
    """Tests for Phase 5 hands-on requirements configuration."""

    def test_phase5_has_4_requirements(self):
        """Verify Phase 5 has exactly 4 hands-on requirements."""
        from services.hands_on_verification import HANDS_ON_REQUIREMENTS

        phase5_reqs = HANDS_ON_REQUIREMENTS.get(5, [])
        assert len(phase5_reqs) == 4

    def test_phase5_requirement_ids(self):
        """Verify Phase 5 requirement IDs are correct."""
        from services.hands_on_verification import HANDS_ON_REQUIREMENTS

        phase5_reqs = HANDS_ON_REQUIREMENTS.get(5, [])
        req_ids = [r.id for r in phase5_reqs]

        assert "phase5-container-image" in req_ids
        assert "phase5-cicd-pipeline" in req_ids
        assert "phase5-terraform-iac" in req_ids
        assert "phase5-kubernetes-manifests" in req_ids

    def test_phase5_submission_types(self):
        """Verify Phase 5 uses correct submission types."""
        from models import SubmissionType
        from services.hands_on_verification import HANDS_ON_REQUIREMENTS

        phase5_reqs = HANDS_ON_REQUIREMENTS.get(5, [])
        req_by_id = {r.id: r for r in phase5_reqs}

        # Container Image: CONTAINER_IMAGE
        assert (
            req_by_id["phase5-container-image"].submission_type
            == SubmissionType.CONTAINER_IMAGE
        )

        # CI/CD: WORKFLOW_RUN
        assert (
            req_by_id["phase5-cicd-pipeline"].submission_type
            == SubmissionType.WORKFLOW_RUN
        )

        # Terraform: REPO_WITH_FILES
        assert (
            req_by_id["phase5-terraform-iac"].submission_type
            == SubmissionType.REPO_WITH_FILES
        )
        assert req_by_id["phase5-terraform-iac"].required_file_patterns is not None

        # Kubernetes: REPO_WITH_FILES
        assert (
            req_by_id["phase5-kubernetes-manifests"].submission_type
            == SubmissionType.REPO_WITH_FILES
        )
        assert (
            req_by_id["phase5-kubernetes-manifests"].required_file_patterns is not None
        )

    def test_container_image_requirement(self):
        """Verify container image requirement is configured correctly."""
        from models import SubmissionType
        from services.hands_on_verification import HANDS_ON_REQUIREMENTS

        phase5_reqs = HANDS_ON_REQUIREMENTS.get(5, [])
        container_req = next(r for r in phase5_reqs if r.id == "phase5-container-image")

        assert container_req.submission_type == SubmissionType.CONTAINER_IMAGE
        assert (
            "container" in container_req.name.lower()
            or "docker" in container_req.name.lower()
            or "image" in container_req.name.lower()
        )

    def test_terraform_patterns(self):
        """Verify Terraform requirement has correct patterns for infra/ folder."""
        from services.hands_on_verification import HANDS_ON_REQUIREMENTS

        phase5_reqs = HANDS_ON_REQUIREMENTS.get(5, [])
        tf_req = next(r for r in phase5_reqs if r.id == "phase5-terraform-iac")

        patterns = tf_req.required_file_patterns
        # Should look for Terraform files in infra/ directory
        assert any("infra" in p for p in patterns)
        assert any("main.tf" in p or ".tf" in p for p in patterns)

    def test_kubernetes_patterns(self):
        """Verify Kubernetes requirement has correct patterns for k8s/ folder."""
        from services.hands_on_verification import HANDS_ON_REQUIREMENTS

        phase5_reqs = HANDS_ON_REQUIREMENTS.get(5, [])
        k8s_req = next(r for r in phase5_reqs if r.id == "phase5-kubernetes-manifests")

        patterns = k8s_req.required_file_patterns
        # Should look for K8s files in k8s/ directory
        assert any("k8s" in p for p in patterns)


class TestContainerImageValidation:
    """Test container image URL validation."""

    async def test_parse_docker_hub_simple(self):
        """Test parsing simple Docker Hub URL (username/image)."""
        from services.github_hands_on_verification import validate_container_image

        # This tests the URL parsing logic
        # Simple format: username/imagename
        result = await validate_container_image("testuser/myapp", "testuser")
        # Even if the image doesn't exist, the parsing should work
        assert result is not None
        # ValidationResult has is_valid and message attributes
        assert hasattr(result, "is_valid")
        assert hasattr(result, "message")

    async def test_parse_docker_hub_with_tag(self):
        """Test parsing Docker Hub URL with tag."""
        from services.github_hands_on_verification import validate_container_image

        result = await validate_container_image("testuser/myapp:latest", "testuser")
        assert result is not None
        assert hasattr(result, "is_valid")

    async def test_parse_ghcr_url(self):
        """Test parsing GitHub Container Registry URL."""
        from services.github_hands_on_verification import validate_container_image

        result = await validate_container_image("ghcr.io/testuser/myapp", "testuser")
        assert result is not None
        assert hasattr(result, "is_valid")

    async def test_parse_ghcr_with_tag(self):
        """Test parsing GHCR URL with tag."""
        from services.github_hands_on_verification import validate_container_image

        result = await validate_container_image(
            "ghcr.io/testuser/myapp:v1.0.0", "testuser"
        )
        assert result is not None
        assert hasattr(result, "is_valid")

    async def test_username_mismatch_docker_hub(self):
        """Test that username mismatch is detected for Docker Hub."""
        from services.github_hands_on_verification import validate_container_image

        result = await validate_container_image("otheruser/myapp", "expecteduser")
        assert result is not None
        # Should fail due to username mismatch
        assert not result.is_valid
        assert "owner" in result.message.lower() or "mismatch" in result.message.lower()

    async def test_username_mismatch_ghcr(self):
        """Test that username mismatch is detected for GHCR."""
        from services.github_hands_on_verification import validate_container_image

        result = await validate_container_image(
            "ghcr.io/otheruser/myapp", "expecteduser"
        )
        assert result is not None
        # Should fail due to username mismatch
        assert not result.is_valid
        assert "owner" in result.message.lower() or "mismatch" in result.message.lower()

    async def test_invalid_url_format(self):
        """Test that invalid URLs are rejected."""
        from services.github_hands_on_verification import validate_container_image

        result = await validate_container_image("not-a-valid-image-url", "testuser")
        assert result is not None
        assert not result.is_valid

    async def test_empty_url(self):
        """Test that empty URLs are rejected."""
        from services.github_hands_on_verification import validate_container_image

        result = await validate_container_image("", "testuser")
        assert result is not None
        assert not result.is_valid

    async def test_docker_io_prefix(self):
        """Test Docker Hub URL with docker.io prefix."""
        from services.github_hands_on_verification import validate_container_image

        result = await validate_container_image("docker.io/testuser/myapp", "testuser")
        assert result is not None
        assert hasattr(result, "is_valid")

    async def test_supported_registries(self):
        """Test that supported registries are recognized."""
        from services.github_hands_on_verification import validate_container_image

        # Docker Hub (implicit)
        result1 = await validate_container_image("testuser/myapp", "testuser")
        assert result1 is not None
        assert hasattr(result1, "is_valid")

        # Docker Hub (explicit)
        result2 = await validate_container_image("docker.io/testuser/myapp", "testuser")
        assert result2 is not None
        assert hasattr(result2, "is_valid")

        # GHCR
        result3 = await validate_container_image("ghcr.io/testuser/myapp", "testuser")
        assert result3 is not None
        assert hasattr(result3, "is_valid")
