"""Unit tests for services.verification.url_derivation.

Covers derive_submission_value for all submission types, _parse_pr_number
edge cases, and the is_derivable / fork_name_from_required_repo helpers.
"""

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import HandsOnRequirement
from learn_to_cloud_shared.verification.url_derivation import (
    _parse_pr_number,
    derive_submission_value,
    fork_name_from_required_repo,
    is_derivable,
)


def _req(
    submission_type: SubmissionType,
    required_repo: str | None = None,
) -> HandsOnRequirement:
    return HandsOnRequirement(
        id="req-1",
        submission_type=submission_type,
        name="Test",
        description="Test",
        required_repo=required_repo,
    )


@pytest.mark.unit
class TestIsDerivable:
    @pytest.mark.parametrize(
        "sub_type",
        [
            SubmissionType.GITHUB_PROFILE,
            SubmissionType.PROFILE_README,
            SubmissionType.REPO_FORK,
            SubmissionType.CI_STATUS,
            SubmissionType.DEVOPS_ANALYSIS,
            SubmissionType.SECURITY_SCANNING,
        ],
    )
    def test_derivable_types(self, sub_type: SubmissionType):
        assert is_derivable(sub_type) is True

    @pytest.mark.parametrize(
        "sub_type",
        [
            SubmissionType.CTF_TOKEN,
            SubmissionType.NETWORKING_TOKEN,
            SubmissionType.DEPLOYED_API,
            SubmissionType.PR_REVIEW,
        ],
    )
    def test_non_derivable_types(self, sub_type: SubmissionType):
        assert is_derivable(sub_type) is False


@pytest.mark.unit
class TestForkNameFromRequiredRepo:
    def test_valid(self):
        assert fork_name_from_required_repo("learntocloud/journal-starter") == (
            "journal-starter"
        )

    def test_nested_path(self):
        # rsplit takes the last segment
        assert fork_name_from_required_repo("owner/group/repo") == "repo"

    def test_missing_slash_raises(self):
        with pytest.raises(ValueError, match="owner/name"):
            fork_name_from_required_repo("journal-starter")


@pytest.mark.unit
class TestDeriveSubmissionValue:
    def test_github_profile(self):
        req = _req(SubmissionType.GITHUB_PROFILE)
        assert derive_submission_value(req, "octocat") == "https://github.com/octocat"

    def test_profile_readme(self):
        req = _req(SubmissionType.PROFILE_README)
        assert (
            derive_submission_value(req, "octocat")
            == "https://github.com/octocat/octocat"
        )

    def test_repo_fork(self):
        req = _req(SubmissionType.REPO_FORK, required_repo="learntocloud/linux-ctfs")
        assert (
            derive_submission_value(req, "alice")
            == "https://github.com/alice/linux-ctfs"
        )

    def test_ci_status(self):
        req = _req(
            SubmissionType.CI_STATUS,
            required_repo="learntocloud/journal-starter",
        )
        assert (
            derive_submission_value(req, "bob")
            == "https://github.com/bob/journal-starter"
        )

    def test_devops_analysis(self):
        req = _req(
            SubmissionType.DEVOPS_ANALYSIS,
            required_repo="learntocloud/journal-starter",
        )
        assert (
            derive_submission_value(req, "carol")
            == "https://github.com/carol/journal-starter"
        )

    def test_security_scanning(self):
        req = _req(
            SubmissionType.SECURITY_SCANNING,
            required_repo="learntocloud/journal-starter",
        )
        assert (
            derive_submission_value(req, "dave")
            == "https://github.com/dave/journal-starter"
        )

    def test_repo_fork_missing_required_repo_raises(self):
        req = _req(SubmissionType.REPO_FORK)
        with pytest.raises(ValueError, match="required_repo"):
            derive_submission_value(req, "alice")

    def test_pr_review_valid(self):
        req = _req(
            SubmissionType.PR_REVIEW, required_repo="learntocloud/journal-starter"
        )
        assert (
            derive_submission_value(req, "alice", user_input="42")
            == "https://github.com/alice/journal-starter/pull/42"
        )

    def test_pr_review_with_hash_prefix(self):
        req = _req(
            SubmissionType.PR_REVIEW, required_repo="learntocloud/journal-starter"
        )
        assert (
            derive_submission_value(req, "alice", user_input=" #17 ")
            == "https://github.com/alice/journal-starter/pull/17"
        )

    def test_pr_review_missing_required_repo_raises(self):
        req = _req(SubmissionType.PR_REVIEW)
        with pytest.raises(ValueError, match="required_repo"):
            derive_submission_value(req, "alice", user_input="42")

    def test_pr_review_missing_pr_number_raises(self):
        req = _req(
            SubmissionType.PR_REVIEW, required_repo="learntocloud/journal-starter"
        )
        with pytest.raises(ValueError, match="PR number is required"):
            derive_submission_value(req, "alice", user_input=None)

    def test_pr_review_non_numeric_raises(self):
        req = _req(
            SubmissionType.PR_REVIEW, required_repo="learntocloud/journal-starter"
        )
        with pytest.raises(ValueError, match="positive integer"):
            derive_submission_value(req, "alice", user_input="abc")

    def test_ctf_token_passes_through(self):
        req = _req(SubmissionType.CTF_TOKEN)
        assert derive_submission_value(req, "alice", user_input="ctf-xyz") == "ctf-xyz"

    def test_networking_token_passes_through(self):
        req = _req(SubmissionType.NETWORKING_TOKEN)
        assert derive_submission_value(req, "alice", user_input="net-abc") == "net-abc"

    def test_deployed_api_passes_through(self):
        req = _req(SubmissionType.DEPLOYED_API)
        assert (
            derive_submission_value(req, "alice", user_input="https://api.example.com")
            == "https://api.example.com"
        )

    def test_derivable_ignores_user_input(self):
        """Tampered submitted_value for derivable types is silently ignored.

        This is the key regression guard for issue #234: even if a learner
        tries to post a crafted URL, the server ignores it and rebuilds the
        canonical URL from their github_username.
        """
        req = _req(SubmissionType.GITHUB_PROFILE)
        assert (
            derive_submission_value(
                req, "alice", user_input="https://evil.example.com/pwn"
            )
            == "https://github.com/alice"
        )


@pytest.mark.unit
class TestParsePrNumber:
    def test_valid(self):
        assert _parse_pr_number("42") == 42

    def test_whitespace(self):
        assert _parse_pr_number("  7  ") == 7

    def test_hash_prefix(self):
        assert _parse_pr_number("#17") == 17

    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="out of range"):
            _parse_pr_number("0")

    def test_negative_rejected(self):
        # Leading '-' fails isdigit.
        with pytest.raises(ValueError, match="positive integer"):
            _parse_pr_number("-5")

    def test_over_max_rejected(self):
        with pytest.raises(ValueError, match="out of range"):
            _parse_pr_number("1000000")

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="required"):
            _parse_pr_number("")

    def test_none_rejected(self):
        with pytest.raises(ValueError, match="required"):
            _parse_pr_number(None)

    def test_non_numeric_rejected(self):
        with pytest.raises(ValueError, match="positive integer"):
            _parse_pr_number("abc")
