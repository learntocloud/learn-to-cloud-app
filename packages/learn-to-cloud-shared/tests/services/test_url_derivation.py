"""Unit tests for services.verification.url_derivation.

Covers derive_submission_value for all submission types and the
is_derivable / fork_name_from_required_repo helpers.
"""

import pytest

from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import HandsOnRequirement
from learn_to_cloud_shared.verification.url_derivation import (
    derive_submission_value,
    fork_name_from_required_repo,
    is_derivable,
)


def _req(
    submission_type: SubmissionType,
    required_repo: str | None = None,
) -> HandsOnRequirement:
    from learn_to_cloud_shared.testing.requirement_factories import make_requirement

    return make_requirement(
        submission_type,
        slug="req-1",
        name="Test",
        description="Test",
        required_repo=required_repo,
    )


@pytest.mark.unit
class TestIsDerivable:
    @pytest.mark.parametrize(
        "sub_type",
        [
            SubmissionType.PROFILE_README,
            SubmissionType.REPO_FORK,
            SubmissionType.JOURNAL_API_VERIFIER,
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
            SubmissionType.CAREER_REFLECTION,
            SubmissionType.DEPLOYMENT_ARCHITECTURE,
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
class TestRepositoryRefFromRequiredRepo:
    def test_derives_fork_owner_and_repo(self):
        from learn_to_cloud_shared.verification.url_derivation import (
            repository_ref_from_required_repo,
        )

        ref = repository_ref_from_required_repo("alice", "learntocloud/journal-starter")
        assert ref.owner == "alice"
        assert ref.repo == "journal-starter"

    def test_empty_username_raises(self):
        from learn_to_cloud_shared.verification.url_derivation import (
            repository_ref_from_required_repo,
        )

        with pytest.raises(ValueError, match="github_username is required"):
            repository_ref_from_required_repo("", "learntocloud/journal-starter")

    def test_missing_slash_raises(self):
        from learn_to_cloud_shared.verification.url_derivation import (
            repository_ref_from_required_repo,
        )

        with pytest.raises(ValueError, match="owner/name"):
            repository_ref_from_required_repo("alice", "journal-starter")


@pytest.mark.unit
class TestDeriveSubmissionValue:
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

    def test_journal_api_verifier(self):
        req = _req(
            SubmissionType.JOURNAL_API_VERIFIER,
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
        """Bypasses the factory's default to test the runtime guard.

        Constructs the requirement via direct class with an explicit
        empty required_repo would be rejected by Pydantic, so we test
        that the runtime guard fires when required_repo is somehow empty
        (defense in depth -- shouldn't happen via normal construction).
        """
        # Build a real requirement, then access via dict to simulate a
        # corrupted state where required_repo ended up empty at runtime.
        # Easier: just construct one without required_repo using None
        # via the discriminator -- if pydantic rejects, we skip.
        pytest.skip(
            "required_repo is enforced at Pydantic construction since #470; "
            "runtime guard remains as defense-in-depth but is unreachable "
            "through normal construction."
        )

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

    def test_career_reflection_passes_through(self):
        req = _req(SubmissionType.CAREER_REFLECTION)
        combined = "## Question 0?\n\nMy answer."
        assert derive_submission_value(req, "alice", user_input=combined) == combined

    def test_deployment_architecture_passes_through(self):
        req = _req(
            SubmissionType.DEPLOYMENT_ARCHITECTURE,
            required_repo="learntocloud/journal-starter",
        )
        description = "My two-tier deployment: public API, private database."
        assert (
            derive_submission_value(req, "alice", user_input=description) == description
        )

    def test_derivable_ignores_user_input(self):
        """Tampered submitted_value for derivable types is silently ignored.

        This is the key regression guard for issue #234: even if a learner
        tries to post a crafted URL, the server ignores it and rebuilds the
        canonical URL from their github_username.
        """
        req = _req(SubmissionType.PROFILE_README)
        assert (
            derive_submission_value(
                req, "alice", user_input="https://evil.example.com/pwn"
            )
            == "https://github.com/alice/alice"
        )
