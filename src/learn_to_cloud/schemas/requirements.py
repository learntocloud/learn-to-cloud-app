"""Hands-on requirement models and their per-type configuration."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator

from learn_to_cloud.models import SubmissionType
from learn_to_cloud.schemas.base import StrictFrozenModel

# ---------------------------------------------------------------------------
# Hands-on requirement type_config models (issue #470)
#
# Every requirement has the same top-level keys
# (uuid, id, submission_type, name, description, type_config).
# Variation between submission types lives inside ``type_config``.
# Pydantic validates per-type config via a discriminated union, so YAML
# authors get parse errors for mismatched fields (e.g., placeholder on a
# profile_readme requirement).
# ---------------------------------------------------------------------------


class EmptyConfig(StrictFrozenModel):
    """No type-specific config (used by profile_readme)."""


class RepoConfig(StrictFrozenModel):
    """Config shared by all GitHub-repo-backed verification types."""

    required_repo: str = Field(
        description="Upstream repo (owner/name) the learner forks from.",
    )


class PlaceholderConfig(StrictFrozenModel):
    """Config shared by free-form input verification types (tokens, URLs)."""

    placeholder: str | None = Field(
        default=None,
        description="Input hint shown in the form field.",
    )
    min_length: int = Field(
        default=1,
        ge=1,
        le=2048,
        description="Minimum characters required before submission.",
    )
    max_length: int = Field(
        default=2048,
        ge=1,
        le=2048,
        description="Maximum accepted input length.",
    )

    @model_validator(mode="after")
    def validate_length_range(self) -> Self:
        if self.min_length > self.max_length:
            raise ValueError("min_length cannot exceed max_length")
        return self


# Per-type config classes inherit from the shared shape. Even when
# behavior is identical, having per-type names keeps JSON Schema clear
# and lets one type evolve fields independently in the future.


class RepoForkConfig(RepoConfig):
    """Config for repo_fork requirements."""


class JournalApiVerifierConfig(RepoConfig):
    """Config for journal_api_verifier requirements."""


class DevopsVerificationConfig(RepoConfig):
    """Config for devops_verification requirements."""


class SecurityScanningConfig(RepoConfig):
    """Config for security_scanning requirements."""


class CtfTokenConfig(PlaceholderConfig):
    """Config for ctf_token requirements."""


class NetworkingTokenConfig(PlaceholderConfig):
    """Config for networking_token requirements."""


class DeployedApiConfig(PlaceholderConfig):
    """Config for deployed_api requirements."""


class CareerReflectionQuestion(StrictFrozenModel):
    """One reflection prompt the learner answers in the app."""

    id: str = Field(description="Stable id for this question.")
    prompt: str = Field(description="The reflection prompt shown to the learner.")


class CareerReflectionConfig(StrictFrozenModel):
    """Config for career_reflection requirements."""

    questions: list[CareerReflectionQuestion] = Field(
        description="Reflection prompts the learner answers in the app.",
        min_length=1,
    )
    min_answer_length: int = Field(
        default=200,
        ge=1,
        description="Minimum characters required for each answer.",
    )


# ---------------------------------------------------------------------------
# Hands-on requirement subclasses, one per active SubmissionType
# (issue #470)
# ---------------------------------------------------------------------------


class _RequirementBase(StrictFrozenModel):
    """Shared top-level fields for every hands-on requirement.

    Subclasses add a ``submission_type`` discriminator field and a typed
    ``type_config``.
    """

    uuid: UUID
    slug: str
    name: str
    description: str


class ProfileReadmeRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.PROFILE_README]
    type_config: EmptyConfig = Field(default_factory=EmptyConfig)


class RepoForkRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.REPO_FORK]
    type_config: RepoForkConfig


class CtfTokenRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.CTF_TOKEN]
    type_config: CtfTokenConfig = Field(default_factory=CtfTokenConfig)


class NetworkingTokenRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.NETWORKING_TOKEN]
    type_config: NetworkingTokenConfig = Field(default_factory=NetworkingTokenConfig)


class JournalApiVerifierRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.JOURNAL_API_VERIFIER]
    type_config: JournalApiVerifierConfig


class DeployedApiRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.DEPLOYED_API]
    type_config: DeployedApiConfig = Field(default_factory=DeployedApiConfig)


class DevopsVerificationRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.DEVOPS_VERIFICATION]
    type_config: DevopsVerificationConfig


class SecurityScanningRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.SECURITY_SCANNING]
    type_config: SecurityScanningConfig


class CareerReflectionRequirement(_RequirementBase):
    submission_type: Literal[SubmissionType.CAREER_REFLECTION]
    type_config: CareerReflectionConfig


HandsOnRequirement = Annotated[
    ProfileReadmeRequirement
    | RepoForkRequirement
    | CtfTokenRequirement
    | NetworkingTokenRequirement
    | JournalApiVerifierRequirement
    | DeployedApiRequirement
    | DevopsVerificationRequirement
    | SecurityScanningRequirement
    | CareerReflectionRequirement,
    Field(discriminator="submission_type"),
]

# Annotated unions don't expose ``model_validate``; use this adapter for
# loading requirements from saved attempt snapshots.
HandsOnRequirementAdapter = TypeAdapter(HandsOnRequirement)
