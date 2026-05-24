"""Test factories for hands-on requirements (issue #470).

After the discriminated-union refactor, ``HandsOnRequirement`` is no
longer a direct constructor -- it's a Pydantic union alias. Tests use
these per-type factories instead. Each factory generates a fresh UUID
by default so test assertions don't have to manage one.

Example::

    from learn_to_cloud_shared.testing.requirement_factories import (
        repo_fork_requirement,
    )

    req = repo_fork_requirement(
        id="my-fork",
        name="Fork the repo",
        required_repo="owner/repo",
    )

For tests that need to dispatch on a ``submission_type`` parameter, use
``make_requirement`` which picks the right per-type factory.
"""

from __future__ import annotations

from uuid import uuid4

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import (
    CtfTokenConfig,
    CtfTokenRequirement,
    DeployedApiConfig,
    DeployedApiRequirement,
    DevopsAnalysisConfig,
    DevopsAnalysisRequirement,
    GithubProfileRequirement,
    JournalApiVerifierConfig,
    JournalApiVerifierRequirement,
    NetworkingTokenConfig,
    NetworkingTokenRequirement,
    ProfileReadmeRequirement,
    RepoForkConfig,
    RepoForkRequirement,
    SecurityScanningConfig,
    SecurityScanningRequirement,
)


def github_profile_requirement(
    *,
    id: str = "github-profile",
    name: str = "Test GitHub profile requirement",
    description: str = "Test description",
) -> GithubProfileRequirement:
    return GithubProfileRequirement(
        uuid=uuid4(),
        id=id,
        submission_type=SubmissionType.GITHUB_PROFILE,
        name=name,
        description=description,
    )


def profile_readme_requirement(
    *,
    id: str = "profile-readme",
    name: str = "Test profile README requirement",
    description: str = "Test description",
) -> ProfileReadmeRequirement:
    return ProfileReadmeRequirement(
        uuid=uuid4(),
        id=id,
        submission_type=SubmissionType.PROFILE_README,
        name=name,
        description=description,
    )


def repo_fork_requirement(
    *,
    id: str = "test-fork",
    name: str = "Test repo fork requirement",
    description: str = "Test description",
    required_repo: str = "owner/test-repo",
) -> RepoForkRequirement:
    return RepoForkRequirement(
        uuid=uuid4(),
        id=id,
        submission_type=SubmissionType.REPO_FORK,
        name=name,
        description=description,
        type_config=RepoForkConfig(required_repo=required_repo),
    )


def ctf_token_requirement(
    *,
    id: str = "ctf-token",
    name: str = "Test CTF token requirement",
    description: str = "Test description",
    placeholder: str | None = None,
) -> CtfTokenRequirement:
    return CtfTokenRequirement(
        uuid=uuid4(),
        id=id,
        submission_type=SubmissionType.CTF_TOKEN,
        name=name,
        description=description,
        type_config=CtfTokenConfig(placeholder=placeholder),
    )


def networking_token_requirement(
    *,
    id: str = "networking-token",
    name: str = "Test networking token requirement",
    description: str = "Test description",
    placeholder: str | None = None,
) -> NetworkingTokenRequirement:
    return NetworkingTokenRequirement(
        uuid=uuid4(),
        id=id,
        submission_type=SubmissionType.NETWORKING_TOKEN,
        name=name,
        description=description,
        type_config=NetworkingTokenConfig(placeholder=placeholder),
    )


def journal_api_verifier_requirement(
    *,
    id: str = "journal-api",
    name: str = "Test Journal API requirement",
    description: str = "Test description",
    required_repo: str = "owner/journal-repo",
) -> JournalApiVerifierRequirement:
    return JournalApiVerifierRequirement(
        uuid=uuid4(),
        id=id,
        submission_type=SubmissionType.JOURNAL_API_VERIFIER,
        name=name,
        description=description,
        type_config=JournalApiVerifierConfig(required_repo=required_repo),
    )


def deployed_api_requirement(
    *,
    id: str = "deployed-api",
    name: str = "Test deployed API requirement",
    description: str = "Test description",
    placeholder: str | None = None,
) -> DeployedApiRequirement:
    return DeployedApiRequirement(
        uuid=uuid4(),
        id=id,
        submission_type=SubmissionType.DEPLOYED_API,
        name=name,
        description=description,
        type_config=DeployedApiConfig(placeholder=placeholder),
    )


def devops_analysis_requirement(
    *,
    id: str = "devops-analysis",
    name: str = "Test devops analysis requirement",
    description: str = "Test description",
    required_repo: str = "owner/devops-repo",
) -> DevopsAnalysisRequirement:
    return DevopsAnalysisRequirement(
        uuid=uuid4(),
        id=id,
        submission_type=SubmissionType.DEVOPS_ANALYSIS,
        name=name,
        description=description,
        type_config=DevopsAnalysisConfig(required_repo=required_repo),
    )


def security_scanning_requirement(
    *,
    id: str = "security-scanning",
    name: str = "Test security scanning requirement",
    description: str = "Test description",
    required_repo: str = "owner/sec-repo",
) -> SecurityScanningRequirement:
    return SecurityScanningRequirement(
        uuid=uuid4(),
        id=id,
        submission_type=SubmissionType.SECURITY_SCANNING,
        name=name,
        description=description,
        type_config=SecurityScanningConfig(required_repo=required_repo),
    )


def make_requirement(
    submission_type: SubmissionType,
    *,
    id: str = "test-req",
    name: str = "Test requirement",
    description: str = "Test description",
    required_repo: str | None = None,
    placeholder: str | None = None,
):
    """Dispatch helper: pick the right per-type factory by ``submission_type``.

    For tests that parameterize over submission_type. Passes through
    the optional ``required_repo`` and ``placeholder`` to the relevant
    factory; ignores them for types that don't use them. Caller is
    responsible for passing the right combinations.
    """
    match submission_type:
        case SubmissionType.GITHUB_PROFILE:
            return github_profile_requirement(id=id, name=name, description=description)
        case SubmissionType.PROFILE_README:
            return profile_readme_requirement(id=id, name=name, description=description)
        case SubmissionType.REPO_FORK:
            return repo_fork_requirement(
                id=id,
                name=name,
                description=description,
                required_repo=required_repo or "owner/test-repo",
            )
        case SubmissionType.CTF_TOKEN:
            return ctf_token_requirement(
                id=id, name=name, description=description, placeholder=placeholder
            )
        case SubmissionType.NETWORKING_TOKEN:
            return networking_token_requirement(
                id=id, name=name, description=description, placeholder=placeholder
            )
        case SubmissionType.JOURNAL_API_VERIFIER:
            return journal_api_verifier_requirement(
                id=id,
                name=name,
                description=description,
                required_repo=required_repo or "owner/journal-repo",
            )
        case SubmissionType.DEPLOYED_API:
            return deployed_api_requirement(
                id=id, name=name, description=description, placeholder=placeholder
            )
        case SubmissionType.DEVOPS_ANALYSIS:
            return devops_analysis_requirement(
                id=id,
                name=name,
                description=description,
                required_repo=required_repo or "owner/devops-repo",
            )
        case SubmissionType.SECURITY_SCANNING:
            return security_scanning_requirement(
                id=id,
                name=name,
                description=description,
                required_repo=required_repo or "owner/sec-repo",
            )
        case _:
            raise ValueError(
                f"No test factory for SubmissionType.{submission_type.name}. "
                "Curriculum doesn't support this type -- see issue #470."
            )
