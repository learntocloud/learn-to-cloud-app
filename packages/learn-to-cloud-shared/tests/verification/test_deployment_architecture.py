"""Tests for the Phase 4 deployment-architecture deterministic gate and evidence."""

import httpx
import pytest

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.testing.requirement_factories import (
    deployment_architecture_requirement,
)
from learn_to_cloud_shared.verification.deployment_architecture import (
    collect_deployment_architecture_evidence,
    validate_deployment_architecture,
)
from learn_to_cloud_shared.verification.repo_files import InMemoryRepoFiles

_TARGET = GitHubTarget(owner="alice", repo="journal-starter")
_DEPLOY_SH = "#!/usr/bin/env bash\naz group create ...\n"
_LONG_DESCRIPTION = (
    "My deployment provisions a public API tier behind a load balancer and a "
    "private database tier in an isolated subnet. Inbound rules restrict the "
    "database to the API subnet only, and TLS terminates at the API gateway. "
    "The deploy.sh script is idempotent and creates the resource group, "
    "network, compute, and database."
)


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    response = httpx.Response(
        status_code=status_code,
        request=httpx.Request("GET", "https://api.github.com"),
    )
    return httpx.HTTPStatusError("error", request=response.request, response=response)


@pytest.mark.unit
class TestValidateDeploymentArchitecture:
    @pytest.mark.asyncio
    async def test_happy_path_passes(self):
        req = deployment_architecture_requirement(min_answer_length=100)
        repo_files = InMemoryRepoFiles({"deploy.sh": _DEPLOY_SH})

        result = await validate_deployment_architecture(
            req, _LONG_DESCRIPTION, _TARGET, repo_files=repo_files
        )

        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_short_description_fails_with_actionable_message(self):
        req = deployment_architecture_requirement(min_answer_length=200)
        repo_files = InMemoryRepoFiles({"deploy.sh": _DEPLOY_SH})

        result = await validate_deployment_architecture(
            req, "too short", _TARGET, repo_files=repo_files
        )

        assert result.is_valid is False
        assert result.verification_completed is True
        assert "200 characters" in result.message

    @pytest.mark.asyncio
    async def test_missing_deploy_script_fails(self):
        req = deployment_architecture_requirement(min_answer_length=100)
        repo_files = InMemoryRepoFiles({"README.md": "# project\n"})

        result = await validate_deployment_architecture(
            req, _LONG_DESCRIPTION, _TARGET, repo_files=repo_files
        )

        assert result.is_valid is False
        assert result.verification_completed is True
        assert "deploy.sh" in result.message

    @pytest.mark.asyncio
    async def test_missing_deploy_script_suggests_other_shell_script(self):
        req = deployment_architecture_requirement(min_answer_length=100)
        repo_files = InMemoryRepoFiles({"setup.sh": _DEPLOY_SH})

        result = await validate_deployment_architecture(
            req, _LONG_DESCRIPTION, _TARGET, repo_files=repo_files
        )

        assert result.is_valid is False
        assert "setup.sh" in result.message

    @pytest.mark.asyncio
    async def test_repo_not_found_fails_actionably(self):
        req = deployment_architecture_requirement(min_answer_length=100)
        repo_files = InMemoryRepoFiles(tree_error=_http_error(404))

        result = await validate_deployment_architecture(
            req, _LONG_DESCRIPTION, _TARGET, repo_files=repo_files
        )

        assert result.is_valid is False
        assert result.verification_completed is True
        assert result.repo_exists is False
        assert "not found" in result.message.lower()

    @pytest.mark.asyncio
    async def test_transient_github_error_reraises(self):
        req = deployment_architecture_requirement(min_answer_length=100)
        repo_files = InMemoryRepoFiles(tree_error=_http_error(500))

        with pytest.raises(httpx.HTTPStatusError):
            await validate_deployment_architecture(
                req, _LONG_DESCRIPTION, _TARGET, repo_files=repo_files
            )


@pytest.mark.unit
class TestCollectDeploymentArchitectureEvidence:
    @pytest.mark.asyncio
    async def test_bundles_deploy_script_and_description(self):
        repo_files = InMemoryRepoFiles({"deploy.sh": _DEPLOY_SH})

        bundle = await collect_deployment_architecture_evidence(
            "alice",
            "journal-starter",
            _LONG_DESCRIPTION,
            repo_files=repo_files,
        )

        assert bundle.source == "repo_files"
        paths = [item.path for item in bundle.items]
        assert "deploy.sh" in paths
        assert "architecture-description.md" in paths
        script_item = next(i for i in bundle.items if i.path == "deploy.sh")
        assert script_item.content == _DEPLOY_SH

    @pytest.mark.asyncio
    async def test_includes_description_even_when_script_missing(self):
        repo_files = InMemoryRepoFiles({})

        bundle = await collect_deployment_architecture_evidence(
            "alice",
            "journal-starter",
            _LONG_DESCRIPTION,
            repo_files=repo_files,
        )

        paths = [item.path for item in bundle.items]
        assert paths == ["architecture-description.md"]


@pytest.mark.unit
class TestJobTarget:
    def test_derives_target_from_username_and_required_repo(self):
        from uuid import uuid4

        from learn_to_cloud_shared.verification_job_executor import (
            PreparedVerificationJob,
        )

        req = deployment_architecture_requirement(
            required_repo="learntocloud/journal-starter"
        )
        job = PreparedVerificationJob(
            id=uuid4(),
            user_id=1,
            github_username="alice",
            requirement=req,
            submitted_value="my long architecture description",
        )

        target = job.target

        assert target is not None
        assert target.owner == "alice"
        assert target.repo == "journal-starter"

    def test_returns_none_when_username_missing(self):
        from uuid import uuid4

        from learn_to_cloud_shared.verification_job_executor import (
            PreparedVerificationJob,
        )

        req = deployment_architecture_requirement(
            required_repo="learntocloud/journal-starter"
        )
        job = PreparedVerificationJob(
            id=uuid4(),
            user_id=1,
            github_username="",
            requirement=req,
            submitted_value="my long architecture description",
        )

        assert job.target is None
