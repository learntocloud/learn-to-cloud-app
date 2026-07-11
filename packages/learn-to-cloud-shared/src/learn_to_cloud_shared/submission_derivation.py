"""Server-side construction of GitHub identity and submission values.

Every repo- or profile-based verification is a pure function of two atoms:
the authenticated learner's ``github_username`` and the requirement's
``required_repo``. ``build_target`` constructs the ``GitHubTarget`` those
atoms describe; the pipeline reads it everywhere instead of parsing a URL
back into an identity.

``derive_submission_value`` builds the display/persist string shown in the
UI and stored in ``Submission.submitted_value``. Token-based types, the
deployed API type, and the journal API response type accept free-form input
and pass through unchanged.
"""

from __future__ import annotations

from learn_to_cloud_shared.github_target import GitHubTarget
from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import HandsOnRequirement

# Derivable types: the server constructs the URL from username + required_repo.
# The template renders these as read-only fields so the learner cannot edit
# them before submitting.
_DERIVABLE_TYPES: frozenset[SubmissionType] = frozenset(
    {
        SubmissionType.GITHUB_PROFILE,
        SubmissionType.PROFILE_README,
        SubmissionType.REPO_FORK,
        SubmissionType.JOURNAL_API_VERIFIER,
        SubmissionType.DEVOPS_ANALYSIS,
        SubmissionType.SECURITY_SCANNING,
    }
)

# Free-form types: the server passes the learner's raw input through to the
# validator unchanged.
_PASS_THROUGH_TYPES: frozenset[SubmissionType] = frozenset(
    {
        SubmissionType.CTF_TOKEN,
        SubmissionType.NETWORKING_TOKEN,
        SubmissionType.DEPLOYED_API,
        SubmissionType.CAREER_REFLECTION,
        SubmissionType.DEPLOYMENT_ARCHITECTURE,
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
        SubmissionType.DEPLOYMENT_ARCHITECTURE,
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
) -> GitHubTarget | None:
    """Construct the GitHub identity a requirement verifies against.

    Returns ``None`` for free-form types (tokens, deployed API, career
    reflection) that reference no GitHub location, and when ``github_username``
    is missing so no identity can be built. Profile types yield a profile
    target; repo types yield the learner's fork of ``required_repo``.

    Raises ``ValueError`` if a repo-target requirement is missing a valid
    ``required_repo``.
    """
    if not github_username:
        return None

    sub_type = requirement.submission_type

    if sub_type == SubmissionType.GITHUB_PROFILE:
        return GitHubTarget(owner=github_username)

    if sub_type == SubmissionType.PROFILE_README:
        return GitHubTarget(owner=github_username, repo=github_username)

    if sub_type in _REPO_TARGET_TYPES:
        required_repo = _required_repo(requirement)
        if not required_repo:
            raise ValueError(
                f"Requirement {requirement.slug!r} is missing required_repo"
            )
        fork = fork_name_from_required_repo(required_repo)
        return GitHubTarget(owner=github_username, repo=fork, forked_from=required_repo)

    return None


def derive_submission_value(
    requirement: HandsOnRequirement,
    github_username: str,
    user_input: str | None = None,
) -> str:
    """Build the canonical submission value for a requirement.

    Args:
        requirement: The requirement being submitted.
        github_username: The authenticated learner's GitHub username.
        user_input: For types that still accept user input, the raw form
            value.  Ignored for derivable URL types.

    Returns:
        The canonical value that should be persisted in
        ``Submission.submitted_value`` and passed to the validator.

    Raises:
        ValueError: If the requirement is misconfigured (e.g. missing
            ``required_repo``).
    """
    sub_type = requirement.submission_type

    if sub_type == SubmissionType.GITHUB_PROFILE:
        return f"https://github.com/{github_username}"

    if sub_type == SubmissionType.PROFILE_README:
        return f"https://github.com/{github_username}/{github_username}"

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
        return f"https://github.com/{github_username}/{fork}"

    if sub_type in _PASS_THROUGH_TYPES:
        return user_input or ""

    raise ValueError(
        f"Unhandled submission type {sub_type!r}. Add it to "
        "_DERIVABLE_TYPES or _PASS_THROUGH_TYPES in submission_derivation.py."
    )
