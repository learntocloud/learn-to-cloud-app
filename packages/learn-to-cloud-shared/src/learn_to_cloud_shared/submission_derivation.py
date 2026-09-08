"""Server-side construction of GitHub repository targets and submission values.

``build_target`` constructs a repository target from the authenticated learner's
``github_username`` and the requirement, including profile README repositories.
The pipeline reads it instead of parsing a URL back into a repository.

``derive_submission_value`` constructs only server-derived GitHub URL values.
Learner-controlled values are validated separately at their HTTP boundary.
"""

from __future__ import annotations

from learn_to_cloud_shared.github_repository_target import GitHubRepositoryTarget
from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import HandsOnRequirement
from learn_to_cloud_shared.submission_values import GitHubUrlValue

# Derivable types: the server constructs the URL from username + required_repo.
# The template renders these as read-only fields so the learner cannot edit
# them before submitting.
_DERIVABLE_TYPES: frozenset[SubmissionType] = frozenset(
    {
        SubmissionType.PROFILE_README,
        SubmissionType.REPO_FORK,
        SubmissionType.JOURNAL_API_VERIFIER,
        SubmissionType.DEVOPS_ANALYSIS,
        SubmissionType.SECURITY_SCANNING,
    }
)

# Repo-target types: the verified GitHub location is the learner's fork of the
# requirement's ``required_repo``, living at ``<username>/<fork-name>``.
_REPO_TARGET_TYPES: frozenset[SubmissionType] = frozenset(
    {
        SubmissionType.REPO_FORK,
        SubmissionType.JOURNAL_API_VERIFIER,
        SubmissionType.DEVOPS_ANALYSIS,
        SubmissionType.SECURITY_SCANNING,
    }
)


def is_derivable(submission_type: SubmissionType) -> bool:
    """Return True if the URL for this submission type is derived server-side.

    Derivable types render as a read-only field with a single Verify button;
    the browser posts no user-editable value for them.
    """
    return submission_type in _DERIVABLE_TYPES


def fork_name_from_required_repo(required_repo: str) -> str:
    """Return the repo name component of an ``owner/name`` pair.

    Raises ``ValueError`` if the input does not contain a ``/``.
    """
    if "/" not in required_repo:
        raise ValueError(
            f"required_repo must be in 'owner/name' format, got: {required_repo!r}"
        )
    return required_repo.rsplit("/", 1)[-1]


def _required_repo(requirement: HandsOnRequirement) -> str | None:
    """Read the upstream ``required_repo`` from a requirement's typed config.

    Only repo-target configs carry it; profile and free-form configs do not,
    so this returns ``None`` for them.
    """
    cfg = getattr(requirement, "type_config", None)
    return getattr(cfg, "required_repo", None) if cfg is not None else None


def build_target(
    requirement: HandsOnRequirement,
    github_username: str | None,
) -> GitHubRepositoryTarget | None:
    """Construct the GitHub repository a requirement verifies against.

    Returns ``None`` for free-form types (tokens, deployed API, career
    reflection) that reference no GitHub location, and when ``github_username``
    is missing so no target can be built. Profile README requirements target
    ``username/username``; fork requirements target ``required_repo``'s name
    under the learner's account.

    Raises ``ValueError`` if a repo-target requirement is missing a valid
    ``required_repo``.
    """
    if not github_username:
        return None

    sub_type = requirement.submission_type

    if sub_type == SubmissionType.PROFILE_README:
        return GitHubRepositoryTarget(owner=github_username, repo=github_username)

    if sub_type in _REPO_TARGET_TYPES:
        required_repo = _required_repo(requirement)
        if not required_repo:
            raise ValueError(
                f"Requirement {requirement.slug!r} is missing required_repo"
            )
        fork = fork_name_from_required_repo(required_repo)
        return GitHubRepositoryTarget(
            owner=github_username, repo=fork, forked_from=required_repo
        )

    return None


def derive_submission_value(
    requirement: HandsOnRequirement,
    github_username: str,
) -> GitHubUrlValue:
    """Build the typed GitHub URL for a server-derived requirement."""
    sub_type = requirement.submission_type

    if sub_type == SubmissionType.PROFILE_README:
        return GitHubUrlValue(f"https://github.com/{github_username}/{github_username}")

    if sub_type in (
        SubmissionType.REPO_FORK,
        SubmissionType.JOURNAL_API_VERIFIER,
        SubmissionType.DEVOPS_ANALYSIS,
        SubmissionType.SECURITY_SCANNING,
    ):
        required_repo = _required_repo(requirement)
        if not required_repo:
            raise ValueError(
                f"Requirement {requirement.slug!r} is missing required_repo"
            )
        fork = fork_name_from_required_repo(required_repo)
        return GitHubUrlValue(f"https://github.com/{github_username}/{fork}")

    raise ValueError(f"Submission type {sub_type.value!r} is not server-derived.")
