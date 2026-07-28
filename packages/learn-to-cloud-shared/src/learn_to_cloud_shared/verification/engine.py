"""The declarative verification engine.

Plain shared-package code (no Durable imports) that the Durable activities
call. A submission type maps to a :class:`VerificationProfile`: an ordered
list of :class:`Step`s whose typed params select a registered **check**.
:func:`run_profile` looks up the profile, runs its steps in order,
short-circuits on a failed gate, accumulates
:class:`EvidenceBundle`s, and produces one aggregate ``ValidationResult``.

Checks are registered by params type in ``_CHECK_REGISTRY`` via
:func:`register_check`. The params type is the single dispatch key, so adding a
verification behavior cannot drift across a separate union, registry name, and
profile step name.

Every submission type resolves to a :class:`VerificationProfile`; a
registry-exhaustiveness test guarantees no type is left unmapped.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import ClassVar

import httpx
from opentelemetry import trace
from pydantic import Field, model_validator

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import FrozenModel, TaskResult, ValidationResult
from learn_to_cloud_shared.verification.career_reflection import (
    collect_career_reflection_evidence,
    validate_career_reflection,
)
from learn_to_cloud_shared.verification.ci_status import verify_ci_status
from learn_to_cloud_shared.verification.codeql_status import verify_codeql_status
from learn_to_cloud_shared.verification.deployed_api import validate_deployed_api
from learn_to_cloud_shared.verification.deployment_architecture import (
    collect_deployment_architecture_evidence,
    validate_deployment_architecture,
)
from learn_to_cloud_shared.verification.devops_analysis import (
    verify_required_devops_files,
)
from learn_to_cloud_shared.verification.errors import github_error_to_result
from learn_to_cloud_shared.verification.evidence import (
    collect_repo_file_evidence,
    collect_repo_pattern_evidence,
)
from learn_to_cloud_shared.verification.ghcr import verify_public_ghcr_image
from learn_to_cloud_shared.verification.github_http import RETRIABLE_EXCEPTIONS
from learn_to_cloud_shared.verification.github_profile import (
    validate_profile_readme,
    validate_repo_fork,
)
from learn_to_cloud_shared.verification.grading_requests import (
    LLMGradingRequest,
    build_repo_rubric_message,
    build_text_rubric_message,
)
from learn_to_cloud_shared.verification.repo_files import RepoFiles, default_repo_files
from learn_to_cloud_shared.verification.security_scanning import (
    collect_security_scanning_evidence,
)
from learn_to_cloud_shared.verification.tasks.base import (
    EvidenceBundle,
    LLMRubricGraderConfig,
    VerificationTask,
)
from learn_to_cloud_shared.verification.tasks.phase3 import (
    JOURNAL_API_FINAL_RUBRIC_TASK,
    JOURNAL_API_IMPORTANT_PATHS,
)
from learn_to_cloud_shared.verification.tasks.phase4 import (
    DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase5 import (
    DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase6 import (
    SECURITY_SCANNING_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.tasks.phase7 import (
    CAREER_REFLECTION_RUBRIC_TASK,
)
from learn_to_cloud_shared.verification.token_base import (
    verify_ctf_token,
    verify_networking_token,
)
from learn_to_cloud_shared.verification_workflow import (
    GradingDisposition,
    PreparedVerificationAttempt,
    VerificationRunResult,
)

_tracer = trace.get_tracer(__name__)

# ---------------------------------------------------------------------------
# Step params: each model type selects exactly one registered check.
# ---------------------------------------------------------------------------


class CheckParams(FrozenModel):
    """Base for typed check configuration and its stable diagnostic name."""

    check_name: ClassVar[str]


class CIStatusParams(CheckParams):
    """Params for the ``github_ci_passing`` gate (workflow file is fixed)."""

    check_name = "github_ci_passing"


class LLMRubricReviewParams(CheckParams):
    """Params for the terminal ``llm_rubric_review`` step.

    Carries the rubric ``task`` (criteria + grader). Existing profiles fetch
    exact ``evidence_paths``; profiles with dynamic filenames may discover
    files from the task's bounded ``path_patterns``.
    """

    check_name = "llm_rubric_review"
    task: VerificationTask
    evidence_paths: tuple[str, ...] = ()
    discover_paths: bool = False

    @model_validator(mode="after")
    def _validate_evidence_selection(self) -> LLMRubricReviewParams:
        if self.discover_paths == bool(self.evidence_paths):
            raise ValueError(
                "Choose exactly one LLM evidence mode: exact paths or discovery"
            )
        return self


class DeploymentArchitectureGateParams(CheckParams):
    """Params for the Phase 4 ``deployment_architecture_gate`` (no config).

    The gate reads the description length and deploy-script path from the
    requirement's ``type_config`` at runtime, so it carries no data.
    """

    check_name = "deployment_architecture_gate"


class DeploymentArchitectureReviewParams(CheckParams):
    """Params for the Phase 4 ``deployment_architecture_review`` rubric step.

    Bundles the learner's forked ``deploy.sh`` with their architecture
    description for the LLM rubric grader.
    """

    check_name = "deployment_architecture_review"
    task: VerificationTask


class DeployedApiCheckParams(CheckParams):
    """Params for the deterministic ``deployed_api_check`` (no config).

    The check probes the submitted base URL's health surface; the target URL
    is the submitted value, so it carries no data.
    """

    check_name = "deployed_api_check"


class DevopsRequiredFilesParams(CheckParams):
    """Params for the Phase 5 required-files gate."""

    check_name = "devops_required_files"


class PublicGhcrImageParams(CheckParams):
    """Params for the Phase 5 public GHCR image gate."""

    check_name = "public_ghcr_image"


class CodeQLStatusParams(CheckParams):
    """Params for the Phase 6 ``codeql_status`` gate (no config).

    The gate verifies the fork's CodeQL workflow ran green on the current
    ``main`` HEAD; the target is resolved from the requirement plus username,
    so it carries no data.
    """

    check_name = "codeql_status"


class SecurityScanningReviewParams(CheckParams):
    """Params for the Phase 6 ``security_scanning_review`` rubric step.

    Bundles the fork's security-scanning config files for the LLM rubric
    grader; carries the rubric ``task``.
    """

    check_name = "security_scanning_review"
    task: VerificationTask


class CareerReflectionGateParams(CheckParams):
    """Params for the Phase 7 ``career_reflection_gate`` (no config).

    The gate only rejects empty submissions; the rubric does the real grading.
    """

    check_name = "career_reflection_gate"


class CareerReflectionReviewParams(CheckParams):
    """Params for the Phase 7 ``career_reflection_review`` text rubric step.

    Bundles the learner's free-text reflection as evidence; carries the rubric
    ``task``. Text-only, so the grading request uses the no-repo prompt.
    """

    check_name = "career_reflection_review"
    task: VerificationTask


class ProfileReadmeCheckParams(CheckParams):
    """Params for the deterministic Phase 0 ``profile_readme_check`` (no config).

    The check confirms the learner's ``<username>/<username>`` profile README
    repo resolves; the target is built from the username, so it carries no data.
    """

    check_name = "profile_readme_check"


class RepoForkCheckParams(CheckParams):
    """Params for the deterministic Phase 1/2 ``repo_fork_check`` (no config).

    The check confirms the learner's repo is a fork of the required upstream;
    fork identity and upstream come from the target, so it carries no data.
    """

    check_name = "repo_fork_check"


class CtfTokenCheckParams(CheckParams):
    """Params for the deterministic Phase 1 ``ctf_token_check`` (no config).

    The check verifies the submitted CTF token against the learner's username.
    """

    check_name = "ctf_token_check"


class NetworkingTokenCheckParams(CheckParams):
    """Params for the deterministic Phase 2 ``networking_token_check`` (no config).

    The check verifies the submitted networking token against the username.
    """

    check_name = "networking_token_check"


# ---------------------------------------------------------------------------
# Engine primitives.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Step:
    """One ordered profile step selected by its typed params."""

    params: CheckParams
    task_id: str


class StepResult(FrozenModel):
    """Outcome of running one step.

    ``evidence`` is contributed to the run's bundle and made visible to later
    steps. ``stop_on_fail`` lets a failed gate short-circuit the remaining
    steps. ``validation_result`` is the authoritative passthrough a
    deterministic gate uses to carry its full result unchanged.
    ``grading_task`` marks that this step requested LLM rubric grading; the
    engine turns it into a recorded grading request once the deterministic
    result is aggregated.
    """

    passed: bool
    task_result: TaskResult | None = None
    evidence: list[EvidenceBundle] = Field(default_factory=list)
    stop_on_fail: bool = True
    validation_result: ValidationResult | None = None
    grading_task: VerificationTask | None = None


@dataclass(frozen=True, slots=True)
class StepContext:
    """Everything a check may read. Carries runtime clients, so not a model."""

    job: PreparedVerificationAttempt
    repository: GitHubTarget | None
    submitted_value: str
    evidence_so_far: tuple[EvidenceBundle, ...] = ()
    repo_files: RepoFiles | None = None


@dataclass(frozen=True)
class VerificationProfile:
    """A submission type's declared verification workflow.

    An ordered list of :class:`Step`s plus the terminal LLM step's rubric and
    optional persona. ``requires_username`` guards types whose steps need the
    learner's GitHub username; :func:`run_profile` short-circuits when it is
    missing.
    """

    requires_username: bool
    steps: tuple[Step, ...] = ()
    system_prompt: str | None = None
    rubric: LLMRubricGraderConfig | None = None


CheckFn = Callable[[StepContext, CheckParams], Awaitable[StepResult]]

_CHECK_REGISTRY: dict[type[CheckParams], CheckFn] = {}


def register_check(
    params_type: type[CheckParams],
) -> Callable[[CheckFn], CheckFn]:
    """Register the check selected by ``params_type``."""

    def decorator(fn: CheckFn) -> CheckFn:
        if params_type in _CHECK_REGISTRY:
            raise ValueError(f"Check already registered: {params_type.check_name}")
        _CHECK_REGISTRY[params_type] = fn
        return fn

    return decorator


def check_for(params: CheckParams) -> CheckFn:
    """Return the check registered for ``params`` or raise ``KeyError``."""
    try:
        return _CHECK_REGISTRY[type(params)]
    except KeyError:
        raise KeyError(f"No check registered for {params.check_name!r}") from None


# ---------------------------------------------------------------------------
# Reusable checks.
# ---------------------------------------------------------------------------


@register_check(CIStatusParams)
async def _check_github_ci_passing(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Gate on a green CI run on the fork's ``main`` branch."""
    target = context.repository
    if target is None or not target.repo:
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=ValidationResult(
                is_valid=False,
                message="Requirement configuration error: missing required_repo",
                username_match=True,
                repo_exists=False,
            ),
        )
    result = await verify_ci_status(target.owner, target.repo)
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(LLMRubricReviewParams)
async def _check_llm_rubric_review(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Fetch bounded repository evidence for a terminal LLM rubric review.

    Never a gate: it gathers the bundle the LLM will grade and marks the task
    for grading. The actual LLM call runs later in the separate durable
    ``run_llm_grading`` activity, so this step stays pure of any model call.
    """
    assert isinstance(params, LLMRubricReviewParams)
    target = context.repository
    if target is None or not target.repo:
        return StepResult(passed=True, stop_on_fail=False)
    repo_files = context.repo_files or default_repo_files()
    if params.discover_paths:
        try:
            bundle = await collect_repo_pattern_evidence(
                repo_files,
                target.owner,
                target.repo,
                params.task,
            )
        except (httpx.HTTPStatusError, *RETRIABLE_EXCEPTIONS) as exc:
            result = github_error_to_result(
                exc,
                event="llm_rubric_review.repo_tree_error",
                context={"owner": target.owner, "repo": target.repo},
            )
            return StepResult(
                passed=False,
                stop_on_fail=True,
                validation_result=result,
            )
        if not bundle.items:
            return StepResult(
                passed=False,
                stop_on_fail=True,
                validation_result=ValidationResult(
                    is_valid=False,
                    message=(
                        "Could not collect repository evidence for automated review."
                    ),
                    verification_completed=False,
                ),
            )
    else:
        bundle = await collect_repo_file_evidence(
            repo_files,
            target.owner,
            target.repo,
            list(params.evidence_paths),
            params.task,
        )
    return StepResult(
        passed=True,
        stop_on_fail=False,
        evidence=[bundle],
        grading_task=params.task,
    )


@register_check(DeployedApiCheckParams)
async def _check_deployed_api(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Deterministic Phase 4 gate: probe the submitted API base URL."""
    result = await validate_deployed_api(context.submitted_value)
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(DevopsRequiredFilesParams)
async def _check_devops_required_files(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Gate on the prescribed Phase 5 repository paths."""
    target = context.repository
    if target is None or not target.repo:
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=ValidationResult(
                is_valid=False,
                message="Requirement configuration error: missing required_repo",
                username_match=True,
                repo_exists=False,
            ),
        )
    result = await verify_required_devops_files(
        target.owner,
        target.repo,
        context.repo_files,
    )
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(PublicGhcrImageParams)
async def _check_public_ghcr_image(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Gate on the learner's public ``journal-api:latest`` GHCR manifest."""
    target = context.repository
    if target is None:
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=ValidationResult(
                is_valid=False,
                message="Requirement configuration error: missing required_repo",
                username_match=True,
                repo_exists=False,
            ),
        )
    result = await verify_public_ghcr_image(target.owner)
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(CodeQLStatusParams)
async def _check_codeql_status(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Deterministic Phase 6 gate: CodeQL green on the fork's current main HEAD."""
    target = context.repository
    if target is None or not target.repo:
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=ValidationResult(
                is_valid=False,
                message="Requirement configuration error: missing required_repo",
                username_match=True,
                repo_exists=False,
            ),
        )
    result = await verify_codeql_status(target.owner, target.repo)
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(SecurityScanningReviewParams)
async def _check_security_scanning_review(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Bundle the fork's security-scanning config files for rubric grading."""
    assert isinstance(params, SecurityScanningReviewParams)
    target = context.repository
    if target is None or not target.repo:
        return StepResult(passed=True, stop_on_fail=False)
    repo_files = context.repo_files or default_repo_files()
    bundle = await collect_security_scanning_evidence(
        target.owner,
        target.repo,
        params.task,
        repo_files=repo_files,
    )
    return StepResult(
        passed=True,
        stop_on_fail=False,
        evidence=[bundle],
        grading_task=params.task,
    )


@register_check(CareerReflectionGateParams)
async def _check_career_reflection_gate(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Deterministic Phase 7 gate: reject empty reflection submissions."""
    result = validate_career_reflection(context.submitted_value)
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(CareerReflectionReviewParams)
async def _check_career_reflection_review(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Bundle the learner's free-text reflection for text rubric grading."""
    assert isinstance(params, CareerReflectionReviewParams)
    bundle = collect_career_reflection_evidence(context.submitted_value, params.task)
    return StepResult(
        passed=True,
        stop_on_fail=False,
        evidence=[bundle],
        grading_task=params.task,
    )


@register_check(ProfileReadmeCheckParams)
async def _check_profile_readme(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Deterministic Phase 0 gate: the profile README repo resolves."""
    target = context.repository
    if target is None:
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=ValidationResult(
                is_valid=False,
                message=(
                    "Requirement configuration error: could not resolve GitHub target"
                ),
                username_match=True,
                repo_exists=False,
            ),
        )
    result = await validate_profile_readme(target)
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(RepoForkCheckParams)
async def _check_repo_fork(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Deterministic Phase 1/2 gate: the learner's repo forks the upstream."""
    target = context.repository
    if target is None:
        return StepResult(
            passed=False,
            stop_on_fail=True,
            validation_result=ValidationResult(
                is_valid=False,
                message=(
                    "Requirement configuration error: could not resolve GitHub target"
                ),
                username_match=True,
                repo_exists=False,
            ),
        )
    result = await validate_repo_fork(target)
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(CtfTokenCheckParams)
async def _check_ctf_token(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Deterministic Phase 1 gate: verify the submitted CTF token."""
    result = verify_ctf_token(
        context.submitted_value, context.job.github_username or ""
    )
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(NetworkingTokenCheckParams)
async def _check_networking_token(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Deterministic Phase 2 gate: verify the submitted networking token."""
    result = verify_networking_token(
        context.submitted_value, context.job.github_username or ""
    )
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(DeploymentArchitectureGateParams)
async def _check_deployment_architecture_gate(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Phase 4 gate: description meets min length and ``deploy.sh`` exists."""
    result = await validate_deployment_architecture(
        context.job.requirement,
        context.submitted_value,
        context.repository,
        context.repo_files,
    )
    return StepResult(
        passed=result.is_valid,
        stop_on_fail=True,
        validation_result=result,
    )


@register_check(DeploymentArchitectureReviewParams)
async def _check_deployment_architecture_review(
    context: StepContext,
    params: CheckParams,
) -> StepResult:
    """Bundle the fork's ``deploy.sh`` and the architecture description.

    Like ``llm_rubric_review`` but its evidence is a repo file plus the
    learner's free-text description, not a set of exact repository paths.
    """
    assert isinstance(params, DeploymentArchitectureReviewParams)
    target = context.repository
    if target is None or not target.repo:
        return StepResult(passed=True, stop_on_fail=False)
    deploy_script_path = getattr(
        context.job.requirement.type_config, "deploy_script_path", "deploy.sh"
    )
    bundle = await collect_deployment_architecture_evidence(
        target.owner,
        target.repo,
        context.submitted_value,
        params.task,
        deploy_script_path=deploy_script_path,
        repo_files=context.repo_files or default_repo_files(),
    )
    return StepResult(
        passed=True,
        stop_on_fail=False,
        evidence=[bundle],
        grading_task=params.task,
    )


# ---------------------------------------------------------------------------
# Profile registry: every submission type maps to a declared profile.
# ---------------------------------------------------------------------------


_PROFILE_REGISTRY: dict[SubmissionType, VerificationProfile] = {}


def register_profile(
    submission_type: SubmissionType, profile: VerificationProfile
) -> None:
    """Register a profile for a submission type (raises on dupes)."""
    if submission_type in _PROFILE_REGISTRY:
        raise ValueError(f"Profile already registered: {submission_type}")
    _PROFILE_REGISTRY[submission_type] = profile


def profile_for(submission_type: SubmissionType) -> VerificationProfile | None:
    """Return the profile for a submission type, if any."""
    return _PROFILE_REGISTRY.get(submission_type)


_JOURNAL_API_RUBRIC = JOURNAL_API_FINAL_RUBRIC_TASK.grader
assert isinstance(_JOURNAL_API_RUBRIC, LLMRubricGraderConfig)

_JOURNAL_API_PROFILE = VerificationProfile(
    requires_username=True,
    steps=(
        Step(
            params=CIStatusParams(),
            task_id="journal-api-implementation-ci",
        ),
        Step(
            params=LLMRubricReviewParams(
                task=JOURNAL_API_FINAL_RUBRIC_TASK,
                evidence_paths=JOURNAL_API_IMPORTANT_PATHS,
            ),
            task_id=JOURNAL_API_FINAL_RUBRIC_TASK.id,
        ),
    ),
    rubric=_JOURNAL_API_RUBRIC,
)

register_profile(SubmissionType.JOURNAL_API_VERIFIER, _JOURNAL_API_PROFILE)


_DEPLOYMENT_ARCHITECTURE_RUBRIC = DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK.grader
assert isinstance(_DEPLOYMENT_ARCHITECTURE_RUBRIC, LLMRubricGraderConfig)

_DEPLOYMENT_ARCHITECTURE_PROFILE = VerificationProfile(
    requires_username=True,
    steps=(
        Step(
            params=DeploymentArchitectureGateParams(),
            task_id="deployment-architecture-gate",
        ),
        Step(
            params=DeploymentArchitectureReviewParams(
                task=DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK,
            ),
            task_id=DEPLOYMENT_ARCHITECTURE_RUBRIC_TASK.id,
        ),
    ),
    rubric=_DEPLOYMENT_ARCHITECTURE_RUBRIC,
)

register_profile(
    SubmissionType.DEPLOYMENT_ARCHITECTURE, _DEPLOYMENT_ARCHITECTURE_PROFILE
)


_DEPLOYED_API_PROFILE = VerificationProfile(
    requires_username=False,
    steps=(
        Step(
            params=DeployedApiCheckParams(),
            task_id="deployed-api-check",
        ),
    ),
)

register_profile(SubmissionType.DEPLOYED_API, _DEPLOYED_API_PROFILE)


_DEVOPS_IMPLEMENTATION_RUBRIC = DEVOPS_IMPLEMENTATION_RUBRIC_TASK.grader
assert isinstance(_DEVOPS_IMPLEMENTATION_RUBRIC, LLMRubricGraderConfig)

_DEVOPS_ANALYSIS_PROFILE = VerificationProfile(
    requires_username=True,
    steps=(
        Step(
            params=DevopsRequiredFilesParams(),
            task_id="devops-required-files",
        ),
        Step(
            params=PublicGhcrImageParams(),
            task_id="public-ghcr-image",
        ),
        Step(
            params=LLMRubricReviewParams(
                task=DEVOPS_IMPLEMENTATION_RUBRIC_TASK,
                discover_paths=True,
            ),
            task_id=DEVOPS_IMPLEMENTATION_RUBRIC_TASK.id,
        ),
    ),
    rubric=_DEVOPS_IMPLEMENTATION_RUBRIC,
)

register_profile(SubmissionType.DEVOPS_ANALYSIS, _DEVOPS_ANALYSIS_PROFILE)


_SECURITY_SCANNING_RUBRIC = SECURITY_SCANNING_RUBRIC_TASK.grader
assert isinstance(_SECURITY_SCANNING_RUBRIC, LLMRubricGraderConfig)

_SECURITY_SCANNING_PROFILE = VerificationProfile(
    requires_username=True,
    steps=(
        Step(
            params=CodeQLStatusParams(),
            task_id="codeql-status-gate",
        ),
        Step(
            params=SecurityScanningReviewParams(task=SECURITY_SCANNING_RUBRIC_TASK),
            task_id=SECURITY_SCANNING_RUBRIC_TASK.id,
        ),
    ),
    rubric=_SECURITY_SCANNING_RUBRIC,
)

register_profile(SubmissionType.SECURITY_SCANNING, _SECURITY_SCANNING_PROFILE)


_CAREER_REFLECTION_RUBRIC = CAREER_REFLECTION_RUBRIC_TASK.grader
assert isinstance(_CAREER_REFLECTION_RUBRIC, LLMRubricGraderConfig)

_CAREER_REFLECTION_PROFILE = VerificationProfile(
    requires_username=False,
    steps=(
        Step(
            params=CareerReflectionGateParams(),
            task_id="career-reflection-gate",
        ),
        Step(
            params=CareerReflectionReviewParams(task=CAREER_REFLECTION_RUBRIC_TASK),
            task_id=CAREER_REFLECTION_RUBRIC_TASK.id,
        ),
    ),
    rubric=_CAREER_REFLECTION_RUBRIC,
)

register_profile(SubmissionType.CAREER_REFLECTION, _CAREER_REFLECTION_PROFILE)


_PROFILE_README_PROFILE = VerificationProfile(
    requires_username=True,
    steps=(
        Step(
            params=ProfileReadmeCheckParams(),
            task_id="profile-readme-check",
        ),
    ),
)

register_profile(SubmissionType.PROFILE_README, _PROFILE_README_PROFILE)


_REPO_FORK_PROFILE = VerificationProfile(
    requires_username=True,
    steps=(
        Step(
            params=RepoForkCheckParams(),
            task_id="repo-fork-check",
        ),
    ),
)

register_profile(SubmissionType.REPO_FORK, _REPO_FORK_PROFILE)


_CTF_TOKEN_PROFILE = VerificationProfile(
    requires_username=True,
    steps=(
        Step(
            params=CtfTokenCheckParams(),
            task_id="ctf-token-check",
        ),
    ),
)

register_profile(SubmissionType.CTF_TOKEN, _CTF_TOKEN_PROFILE)


_NETWORKING_TOKEN_PROFILE = VerificationProfile(
    requires_username=True,
    steps=(
        Step(
            params=NetworkingTokenCheckParams(),
            task_id="networking-token-check",
        ),
    ),
)

register_profile(SubmissionType.NETWORKING_TOKEN, _NETWORKING_TOKEN_PROFILE)


def _resolve_profile(job: PreparedVerificationAttempt) -> VerificationProfile | None:
    """Return the profile for this job's submission type, or None if unknown."""
    return profile_for(job.requirement.submission_type)


def _steps_for(profile: VerificationProfile) -> tuple[Step, ...]:
    """Return a profile's declared steps."""
    return profile.steps


def _aggregate(step_results: list[StepResult]) -> ValidationResult:
    """Fold step results into one ``ValidationResult``.

    One deterministic gate is returned unchanged. Multiple gates fold in
    declaration order: the last gate supplies the decisive message while all
    gate outcomes and task feedback contribute to the aggregate.
    """
    authoritative_results = [
        result.validation_result
        for result in step_results
        if result.validation_result is not None
    ]
    if len(authoritative_results) == 1:
        return authoritative_results[0]
    if authoritative_results:
        decisive_result = authoritative_results[-1]
        task_results = [
            task_result
            for validation_result in authoritative_results
            for task_result in (validation_result.task_results or [])
        ]

        def latest_value(field: str) -> bool | str | None:
            for validation_result in reversed(authoritative_results):
                value = getattr(validation_result, field)
                if value is not None:
                    return value
            return None

        return decisive_result.model_copy(
            update={
                "is_valid": all(result.is_valid for result in authoritative_results),
                "username_match": latest_value("username_match"),
                "repo_exists": latest_value("repo_exists"),
                "task_results": task_results or None,
                "verification_completed": all(
                    result.verification_completed for result in authoritative_results
                ),
                "cloud_provider": latest_value("cloud_provider"),
            }
        )

    task_results = [r.task_result for r in step_results if r.task_result is not None]
    passed = all(r.passed for r in step_results)
    message = (
        "Verification succeeded."
        if passed
        else "Verification failed. Review the task feedback and try again."
    )
    return ValidationResult(
        is_valid=passed,
        message=message,
        task_results=task_results or None,
        verification_completed=True,
    )


def _grading_requests_for(
    job: PreparedVerificationAttempt,
    deterministic_result: ValidationResult,
    step_results: list[StepResult],
) -> list[LLMGradingRequest]:
    """Turn steps that requested grading into recorded grading requests.

    Runs after aggregation so the prompt carries the final deterministic
    result. Empty when a gate failed before the rubric step ran, which is how
    a migrated profile signals "no grading needed" to the orchestrator.

    A task whose evidence source is ``submitted_text`` grades free text with no
    repository (Phase 7); every other task requires a repository target.
    """
    target = job.target
    requests: list[LLMGradingRequest] = []
    for result in step_results:
        task = result.grading_task
        if task is None:
            continue
        evidence = result.evidence[0].model_dump(mode="json") if result.evidence else {}
        if task.evidence.source == "submitted_text":
            message = build_text_rubric_message(
                requirement_slug=job.requirement.slug,
                requirement_name=job.requirement.name,
                deterministic_result=deterministic_result,
                task=task,
                evidence=evidence,
            )
        else:
            if target is None or not target.repo:
                raise ValueError(
                    f"Rubric task {task.id!r} requires a GitHub repository target"
                )
            message = build_repo_rubric_message(
                requirement_slug=job.requirement.slug,
                requirement_name=job.requirement.name,
                deterministic_result=deterministic_result,
                owner=target.owner,
                repo=target.repo,
                task=task,
                evidence=evidence,
            )
        requests.append(
            LLMGradingRequest(
                task=task,
                message=message,
                thread_id=f"{job.id}-{task.id}",
            )
        )
    return requests


def _grading_disposition_for(
    profile: VerificationProfile,
    step_results: list[StepResult],
    grading_requests: list[LLMGradingRequest],
) -> GradingDisposition:
    """Explain why this run will or will not enter LLM grading."""
    if profile.rubric is None:
        if grading_requests:
            raise ValueError("Non-rubric profile produced grading requests")
        return GradingDisposition.NOT_REQUIRED
    if grading_requests:
        return GradingDisposition.REQUESTED
    if any(not result.passed and result.stop_on_fail for result in step_results):
        return GradingDisposition.SKIPPED_GATE_FAILED
    raise ValueError("Rubric profile completed without a grading request")


async def run_profile(
    job: PreparedVerificationAttempt,
    *,
    repo_files: RepoFiles | None = None,
) -> VerificationRunResult:
    """Run a submission type's profile and return the aggregate result.

    Steps run in order; a failed gate with ``stop_on_fail`` short-circuits the
    rest. Evidence bundles accumulate across steps, are visible to later steps
    via ``evidence_so_far``, and are carried on the returned run result.

    Every result records both its LLM grading requests and a
    ``grading_disposition`` explaining why grading was requested or skipped.
    An unregistered type (which the exhaustiveness test forbids) returns a
    clean error result.
    """
    profile = _resolve_profile(job)
    if profile is None:
        return VerificationRunResult(
            attempt=job,
            validation_result=ValidationResult(
                is_valid=False,
                message=(f"Unknown submission type: {job.requirement.submission_type}"),
                username_match=False,
                repo_exists=False,
            ),
            evidence=None,
            grading_requests=[],
            grading_disposition=(GradingDisposition.SKIPPED_UNKNOWN_SUBMISSION_TYPE),
        )

    if profile.requires_username and not job.github_username:
        return VerificationRunResult(
            attempt=job,
            validation_result=ValidationResult(
                is_valid=False,
                message="GitHub username is required for this verification",
                username_match=False,
            ),
            evidence=None,
            grading_requests=[],
            grading_disposition=GradingDisposition.SKIPPED_MISSING_USERNAME,
        )

    steps = _steps_for(profile)
    context = StepContext(
        job=job,
        repository=job.target,
        submitted_value=job.submitted_value.as_text,
        repo_files=repo_files,
    )

    step_results: list[StepResult] = []
    bundles: list[EvidenceBundle] = []
    for step in steps:
        result = await check_for(step.params)(context, step.params)
        step_results.append(result)
        if result.evidence:
            bundles.extend(result.evidence)
            context = replace(
                context,
                evidence_so_far=(*context.evidence_so_far, *result.evidence),
            )
        if not result.passed and result.stop_on_fail:
            break

    deterministic_result = _aggregate(step_results)
    grading_requests = _grading_requests_for(job, deterministic_result, step_results)
    grading_disposition = _grading_disposition_for(
        profile, step_results, grading_requests
    )

    return VerificationRunResult(
        attempt=job,
        validation_result=deterministic_result,
        evidence=bundles or None,
        grading_requests=grading_requests,
        grading_disposition=grading_disposition,
    )
