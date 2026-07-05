"""Tests for typed submitted-value storage helpers."""

import pytest

from learn_to_cloud_shared.models import SubmissionType, SubmissionValueKind
from learn_to_cloud_shared.submission_values import (
    SubmittedValue,
    value_kind_for_submission_type,
)
from learn_to_cloud_shared.testing.requirement_factories import (
    career_reflection_requirement,
    ctf_token_requirement,
    deployed_api_requirement,
    github_profile_requirement,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("submission_type", "expected"),
    [
        (SubmissionType.GITHUB_PROFILE, SubmissionValueKind.GITHUB_URL),
        (SubmissionType.JOURNAL_API_VERIFIER, SubmissionValueKind.GITHUB_URL),
        (SubmissionType.CTF_TOKEN, SubmissionValueKind.TOKEN),
        (SubmissionType.DEPLOYED_API, SubmissionValueKind.DEPLOYED_URL),
        (SubmissionType.CAREER_REFLECTION, SubmissionValueKind.TEXT),
        (SubmissionType.DEPLOYMENT_ARCHITECTURE, SubmissionValueKind.TEXT),
        ("ci_status", SubmissionValueKind.GITHUB_URL),
        ("iac_token", SubmissionValueKind.TOKEN),
    ],
)
def test_value_kind_for_submission_type(
    submission_type: SubmissionType | str,
    expected: SubmissionValueKind,
) -> None:
    assert value_kind_for_submission_type(submission_type) is expected


@pytest.mark.unit
def test_github_url_value_uses_github_column() -> None:
    value = SubmittedValue.from_raw(
        github_profile_requirement(),
        " https://github.com/user ",
    )

    assert value.kind is SubmissionValueKind.GITHUB_URL
    assert value.github_url == "https://github.com/user"
    assert value.to_columns() == {
        "submitted_value": "https://github.com/user",
        "submission_value_kind": "github_url",
        "github_url": "https://github.com/user",
        "token_value": None,
        "deployed_url": None,
        "text_value": None,
    }


@pytest.mark.unit
def test_text_value_uses_text_column() -> None:
    value = SubmittedValue.from_raw(
        career_reflection_requirement(),
        "  ## Question 0?\n\nA thoughtful answer.  ",
    )

    assert value.kind is SubmissionValueKind.TEXT
    assert value.text_value == "## Question 0?\n\nA thoughtful answer."
    assert value.as_text == "## Question 0?\n\nA thoughtful answer."
    assert value.to_columns() == {
        "submitted_value": "## Question 0?\n\nA thoughtful answer.",
        "submission_value_kind": "text",
        "github_url": None,
        "token_value": None,
        "deployed_url": None,
        "text_value": "## Question 0?\n\nA thoughtful answer.",
    }


@pytest.mark.unit
def test_text_value_round_trips_through_columns() -> None:
    original = SubmittedValue.from_raw(
        career_reflection_requirement(),
        "Reflection body text.",
    )

    restored = SubmittedValue.from_columns(
        kind=original.kind.value,
        github_url=None,
        token_value=None,
        deployed_url=None,
        text_value=original.text_value,
        legacy_value=original.as_text,
    )

    assert restored.kind is SubmissionValueKind.TEXT
    assert restored.text_value == "Reflection body text."


@pytest.mark.unit
def test_token_value_uses_token_column() -> None:
    value = SubmittedValue.from_raw(ctf_token_requirement(), " token-123 ")

    assert value.kind is SubmissionValueKind.TOKEN
    assert value.token_value == "token-123"
    assert value.as_text == "token-123"


@pytest.mark.unit
def test_deployed_url_value_uses_deployed_url_column() -> None:
    value = SubmittedValue.from_raw(
        deployed_api_requirement(),
        " https://api.example.com ",
    )

    assert value.kind is SubmissionValueKind.DEPLOYED_URL
    assert value.deployed_url == "https://api.example.com"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw_value",
    ["not-a-url", "https://example.com/user", "https://github.com/user name"],
)
def test_github_url_requires_github_url(raw_value: str) -> None:
    with pytest.raises(ValueError, match="GitHub URL"):
        SubmittedValue.from_raw(github_profile_requirement(), raw_value)


@pytest.mark.unit
def test_deployed_url_rejects_whitespace() -> None:
    with pytest.raises(ValueError, match="deployed API URL"):
        SubmittedValue.from_raw(
            deployed_api_requirement(),
            "https://api.example.com/bad path",
        )


@pytest.mark.unit
def test_payload_round_trip_rejects_legacy_mismatch() -> None:
    payload = {
        "submission_value_kind": "github_url",
        "github_url": "https://github.com/user",
        "token_value": None,
        "deployed_url": None,
        "submitted_value": "https://github.com/other",
    }

    with pytest.raises(ValueError, match="Legacy submitted_value"):
        SubmittedValue.from_payload(payload)
