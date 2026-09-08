"""Complete built-in check catalog, independent of caller import order."""

from learn_to_cloud_shared.verification.checks.career import (
    CareerReflectionGateParams,
    CareerReflectionReviewParams,
    _check_career_reflection_gate,
    _check_career_reflection_review,
)
from learn_to_cloud_shared.verification.checks.deployed_api import (
    DeployedApiCheckParams,
    _check_deployed_api,
)
from learn_to_cloud_shared.verification.checks.deployment_architecture import (
    DeploymentArchitectureGateParams,
    DeploymentArchitectureReviewParams,
    _check_deployment_architecture_gate,
    _check_deployment_architecture_review,
)
from learn_to_cloud_shared.verification.checks.devops import (
    DevopsRequiredFilesParams,
    PublicGhcrImageParams,
    _check_devops_required_files,
    _check_public_ghcr_image,
)
from learn_to_cloud_shared.verification.checks.github import (
    CIStatusParams,
    ProfileReadmeCheckParams,
    RepoForkCheckParams,
    _check_github_ci_passing,
    _check_profile_readme,
    _check_repo_fork,
)
from learn_to_cloud_shared.verification.checks.rubric import (
    LLMRubricReviewParams,
    _check_llm_rubric_review,
)
from learn_to_cloud_shared.verification.checks.security import (
    CodeQLStatusParams,
    SecurityScanningReviewParams,
    _check_codeql_status,
    _check_security_scanning_review,
)
from learn_to_cloud_shared.verification.checks.tokens import (
    CtfTokenCheckParams,
    NetworkingTokenCheckParams,
    _check_ctf_token,
    _check_networking_token,
)
from learn_to_cloud_shared.verification.core import CheckRegistry

CHECK_REGISTRY = CheckRegistry(
    (
        (CIStatusParams, _check_github_ci_passing),
        (ProfileReadmeCheckParams, _check_profile_readme),
        (RepoForkCheckParams, _check_repo_fork),
        (CtfTokenCheckParams, _check_ctf_token),
        (NetworkingTokenCheckParams, _check_networking_token),
        (DeployedApiCheckParams, _check_deployed_api),
        (DeploymentArchitectureGateParams, _check_deployment_architecture_gate),
        (DeploymentArchitectureReviewParams, _check_deployment_architecture_review),
        (DevopsRequiredFilesParams, _check_devops_required_files),
        (PublicGhcrImageParams, _check_public_ghcr_image),
        (LLMRubricReviewParams, _check_llm_rubric_review),
        (CodeQLStatusParams, _check_codeql_status),
        (SecurityScanningReviewParams, _check_security_scanning_review),
        (CareerReflectionGateParams, _check_career_reflection_gate),
        (CareerReflectionReviewParams, _check_career_reflection_review),
    )
)
