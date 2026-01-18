"""Unit tests for services/submissions.py.

Tests submission helper functions used by progress and badge services.

Total test cases: 6
- TestGetValidatedIdsByPhase: 6 tests
"""

from models import Submission, SubmissionType
from services.submissions_service import get_validated_ids_by_phase


class TestGetValidatedIdsByPhase:
    """Test get_validated_ids_by_phase function.

    This function groups validated submission requirement IDs by phase,
    used for determining phase completion status.
    """

    def test_empty_list_returns_empty_dict(self):
        """Empty submission list returns empty dict."""
        result = get_validated_ids_by_phase([])
        assert result == {}

    def test_single_validated_submission(self):
        """Single validated submission is grouped correctly."""
        submissions = [
            Submission(
                id=1,
                user_id="user123",
                requirement_id="phase0-github-profile",
                submission_type=SubmissionType.GITHUB_PROFILE,
                phase_id=0,
                submitted_value="https://github.com/testuser",
                extracted_username="testuser",
                is_validated=True,
            )
        ]

        result = get_validated_ids_by_phase(submissions)

        assert result == {0: {"phase0-github-profile"}}

    def test_unvalidated_submissions_excluded(self):
        """Unvalidated submissions are not included."""
        submissions = [
            Submission(
                id=1,
                user_id="user123",
                requirement_id="phase0-github-profile",
                submission_type=SubmissionType.GITHUB_PROFILE,
                phase_id=0,
                submitted_value="https://github.com/testuser",
                extracted_username="testuser",
                is_validated=False,
            )
        ]

        result = get_validated_ids_by_phase(submissions)
        assert result == {}

    def test_multiple_requirements_same_phase(self):
        """Multiple validated requirements in same phase grouped together."""
        submissions = [
            Submission(
                id=1,
                user_id="user123",
                requirement_id="phase1-profile-readme",
                submission_type=SubmissionType.PROFILE_README,
                phase_id=1,
                submitted_value="https://github.com/testuser/testuser",
                extracted_username="testuser",
                is_validated=True,
            ),
            Submission(
                id=2,
                user_id="user123",
                requirement_id="phase1-linux-ctfs-fork",
                submission_type=SubmissionType.REPO_FORK,
                phase_id=1,
                submitted_value="https://github.com/testuser/linux-ctfs",
                extracted_username="testuser",
                is_validated=True,
            ),
            Submission(
                id=3,
                user_id="user123",
                requirement_id="phase1-linux-ctf-token",
                submission_type=SubmissionType.CTF_TOKEN,
                phase_id=1,
                submitted_value="token123",
                extracted_username="testuser",
                is_validated=True,
            ),
        ]

        result = get_validated_ids_by_phase(submissions)

        assert result == {
            1: {
                "phase1-profile-readme",
                "phase1-linux-ctfs-fork",
                "phase1-linux-ctf-token",
            }
        }

    def test_multiple_phases(self):
        """Validated submissions from multiple phases grouped correctly."""
        submissions = [
            Submission(
                id=1,
                user_id="user123",
                requirement_id="phase0-github-profile",
                submission_type=SubmissionType.GITHUB_PROFILE,
                phase_id=0,
                submitted_value="https://github.com/testuser",
                extracted_username="testuser",
                is_validated=True,
            ),
            Submission(
                id=2,
                user_id="user123",
                requirement_id="phase1-profile-readme",
                submission_type=SubmissionType.PROFILE_README,
                phase_id=1,
                submitted_value="https://github.com/testuser/testuser",
                extracted_username="testuser",
                is_validated=True,
            ),
            Submission(
                id=3,
                user_id="user123",
                requirement_id="phase2-journal-starter-fork",
                submission_type=SubmissionType.REPO_FORK,
                phase_id=2,
                submitted_value="https://github.com/testuser/journal-starter",
                extracted_username="testuser",
                is_validated=True,
            ),
        ]

        result = get_validated_ids_by_phase(submissions)

        assert result == {
            0: {"phase0-github-profile"},
            1: {"phase1-profile-readme"},
            2: {"phase2-journal-starter-fork"},
        }

    def test_mixed_validated_and_unvalidated(self):
        """Only validated submissions included when mixed."""
        submissions = [
            Submission(
                id=1,
                user_id="user123",
                requirement_id="phase0-github-profile",
                submission_type=SubmissionType.GITHUB_PROFILE,
                phase_id=0,
                submitted_value="https://github.com/testuser",
                extracted_username="testuser",
                is_validated=True,
            ),
            Submission(
                id=2,
                user_id="user123",
                requirement_id="phase1-profile-readme",
                submission_type=SubmissionType.PROFILE_README,
                phase_id=1,
                submitted_value="https://github.com/invalid",
                extracted_username="invalid",
                is_validated=False,
            ),
            Submission(
                id=3,
                user_id="user123",
                requirement_id="phase1-linux-ctfs-fork",
                submission_type=SubmissionType.REPO_FORK,
                phase_id=1,
                submitted_value="https://github.com/testuser/linux-ctfs",
                extracted_username="testuser",
                is_validated=True,
            ),
        ]

        result = get_validated_ids_by_phase(submissions)

        assert result == {
            0: {"phase0-github-profile"},
            1: {"phase1-linux-ctfs-fork"},
        }
