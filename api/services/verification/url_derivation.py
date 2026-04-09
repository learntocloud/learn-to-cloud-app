"""Server-side derivation of canonical submission values.

Hands-on verification URLs for GitHub-backed requirements are derived from
the authenticated user's ``github_username`` plus the requirement's
``required_repo``.  Keeping this logic on the server closes an injection
vector (learners can no longer craft arbitrary URLs) and removes a fragile
copy/paste step from the UI.

The resulting string is what gets persisted in ``Submission.submitted_value``
and passed to the validators.  Token-based types and the Phase 4 deployed
API type keep their existing free-form input and pass through unchanged.
"""

from __future__ import annotations

from models import SubmissionType
from schemas import HandsOnRequirement

# Derivable types: the server constructs the URL from username + required_repo.
# The template renders these as read-only fields so the learner cannot edit
# them before submitting.
_DERIVABLE_TYPES: frozenset[SubmissionType] = frozenset(
    {
        SubmissionType.GITHUB_PROFILE,
        SubmissionType.PROFILE_README,
        SubmissionType.REPO_FORK,
        SubmissionType.CODE_ANALYSIS,
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
        SubmissionType.JOURNAL_API_RESPONSE,
    }
)

# Maximum PR number we accept.  GitHub has no hard upper bound but a 6-digit
# cap is comfortably above any real learner fork and stops obvious abuse.
_MAX_PR_NUMBER = 999_999


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
            value.  Ignored for derivable URL types.  For ``pr_review`` this
            is the numeric PR number as a string.

    Returns:
        The canonical value that should be persisted in
        ``Submission.submitted_value`` and passed to the validator.

    Raises:
        ValueError: If the requirement is misconfigured (e.g. missing
            ``required_repo``) or the user input is malformed (e.g. a
            non-numeric PR number).
    """
    sub_type = requirement.submission_type

    if sub_type == SubmissionType.GITHUB_PROFILE:
        return f"https://github.com/{github_username}"

    if sub_type == SubmissionType.PROFILE_README:
        return f"https://github.com/{github_username}/{github_username}"

    if sub_type in (
        SubmissionType.REPO_FORK,
        SubmissionType.CODE_ANALYSIS,
        SubmissionType.DEVOPS_ANALYSIS,
        SubmissionType.SECURITY_SCANNING,
    ):
        if not requirement.required_repo:
            raise ValueError(f"Requirement {requirement.id!r} is missing required_repo")
        fork = fork_name_from_required_repo(requirement.required_repo)
        return f"https://github.com/{github_username}/{fork}"

    if sub_type == SubmissionType.PR_REVIEW:
        if not requirement.required_repo:
            raise ValueError(f"Requirement {requirement.id!r} is missing required_repo")
        pr_number = _parse_pr_number(user_input)
        fork = fork_name_from_required_repo(requirement.required_repo)
        return f"https://github.com/{github_username}/{fork}/pull/{pr_number}"

    if sub_type in _PASS_THROUGH_TYPES:
        return user_input or ""

    raise ValueError(
        f"Unhandled submission type {sub_type!r}. Add it to "
        "_DERIVABLE_TYPES or _PASS_THROUGH_TYPES in url_derivation.py."
    )


def _parse_pr_number(raw: str | None) -> int:
    """Parse and validate a PR number from a form field.

    Accepts leading/trailing whitespace and a leading ``#``.  Rejects
    anything that isn't a positive integer within the allowed range.
    """
    if raw is None:
        raise ValueError("PR number is required.")
    cleaned = raw.strip().lstrip("#")
    if not cleaned:
        raise ValueError("PR number is required.")
    if not cleaned.isdigit():
        raise ValueError("PR number must be a positive integer.")
    value = int(cleaned)
    if value < 1 or value > _MAX_PR_NUMBER:
        raise ValueError("PR number is out of range.")
    return value
