"""Unit tests for schema-derived constants."""

from __future__ import annotations

from learn_to_cloud_shared.schemas import KNOWN_HANDS_ON_SUBMISSION_TYPES


def test_known_submission_types_matches_union() -> None:
    """The derived constant must list exactly the union's submission types."""
    assert KNOWN_HANDS_ON_SUBMISSION_TYPES == {
        "profile_readme",
        "repo_fork",
        "ctf_token",
        "networking_token",
        "journal_api_verifier",
        "deployed_api",
        "devops_analysis",
        "security_scanning",
        "career_reflection",
        "deployment_architecture",
    }
    # A type the DB CHECK allows but the union doesn't know must be absent,
    # so the content loader treats it as unknown (issue #603).
    assert "ci_status" not in KNOWN_HANDS_ON_SUBMISSION_TYPES
