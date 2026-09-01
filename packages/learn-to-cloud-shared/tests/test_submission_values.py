"""Tests for typed submitted-value storage helpers."""

import pytest

from learn_to_cloud_shared.models import SubmissionType, SubmissionValueKind
from learn_to_cloud_shared.submission_values import (
    DeployedUrlValue,
    GitHubUrlValue,
    TextValue,
    TokenValue,
    submitted_value_from_payload,
    submitted_value_from_raw,
    value_kind_for_submission_type,
)
from learn_to_cloud_shared.testing.requirement_factories import (
    career_reflection_requirement,
    ctf_token_requirement,
    deployed_api_requirement,
    profile_readme_requirement,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("submission_type", "expected"),
    [
        (SubmissionType.PROFILE_README, SubmissionValueKind.GITHUB_URL),
        (SubmissionType.JOURNAL_API_VERIFIER, SubmissionValueKind.GITHUB_URL),
        (SubmissionType.CTF_TOKEN, SubmissionValueKind.TOKEN),
        (SubmissionType.DEPLOYED_API, SubmissionValueKind.DEPLOYED_URL),
        (SubmissionType.CAREER_REFLECTION, SubmissionValueKind.TEXT),
        (SubmissionType.DEPLOYMENT_ARCHITECTURE, SubmissionValueKind.TEXT),
    ],
)
def test_value_kind_for_submission_type(
    submission_type: SubmissionType | str,
    expected: SubmissionValueKind,
) -> None:
    assert value_kind_for_submission_type(submission_type) is expected


@pytest.mark.unit
def test_github_url_value_uses_typed_payload() -> None:
    value = submitted_value_from_raw(
        profile_readme_requirement(),
        " https://github.com/user ",
    )

    assert value.kind is SubmissionValueKind.GITHUB_URL
    assert isinstance(value, GitHubUrlValue)
    assert value.github_url == "https://github.com/user"
    assert value.to_payload() == {
        "submission_value_kind": "github_url",
        "value": "https://github.com/user",
    }


@pytest.mark.unit
def test_text_value_uses_typed_payload() -> None:
    value = submitted_value_from_raw(
        career_reflection_requirement(),
        "  ## Question 0?\n\nA thoughtful answer.  ",
    )

    assert value.kind is SubmissionValueKind.TEXT
    assert isinstance(value, TextValue)
    assert value.text == "## Question 0?\n\nA thoughtful answer."
    assert value.as_text == "## Question 0?\n\nA thoughtful answer."
    assert value.to_payload() == {
        "submission_value_kind": "text",
        "value": "## Question 0?\n\nA thoughtful answer.",
    }


@pytest.mark.unit
def test_text_value_round_trips_through_payload() -> None:
    original = submitted_value_from_raw(
        career_reflection_requirement(),
        "Reflection body text.",
    )

    restored = submitted_value_from_payload(original.to_payload())

    assert restored.kind is SubmissionValueKind.TEXT
    assert isinstance(restored, TextValue)
    assert restored.text == "Reflection body text."


@pytest.mark.unit
def test_token_value_uses_token_column() -> None:
    value = submitted_value_from_raw(ctf_token_requirement(), " token-123 ")

    assert value.kind is SubmissionValueKind.TOKEN
    assert isinstance(value, TokenValue)
    assert value.token == "token-123"
    assert value.as_text == "token-123"


@pytest.mark.unit
def test_deployed_url_value_uses_deployed_url_column() -> None:
    value = submitted_value_from_raw(
        deployed_api_requirement(),
        " https://api.example.com ",
    )

    assert value.kind is SubmissionValueKind.DEPLOYED_URL
    assert isinstance(value, DeployedUrlValue)
    assert value.url == "https://api.example.com"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw_value",
    ["not-a-url", "https://example.com/user", "https://github.com/user name"],
)
def test_github_url_requires_github_url(raw_value: str) -> None:
    with pytest.raises(ValueError, match="GitHub URL"):
        submitted_value_from_raw(profile_readme_requirement(), raw_value)


@pytest.mark.unit
def test_deployed_url_rejects_whitespace() -> None:
    with pytest.raises(ValueError, match="deployed API URL"):
        submitted_value_from_raw(
            deployed_api_requirement(),
            "https://api.example.com/bad path",
        )


@pytest.mark.unit
def test_payload_rejects_legacy_typed_value_fields() -> None:
    payload = {
        "submission_value_kind": "github_url",
        "github_url": "https://github.com/user",
        "token_value": "unexpected-token",
        "deployed_url": None,
        "text_value": None,
    }

    with pytest.raises(ValueError, match="Invalid submission value payload fields"):
        submitted_value_from_payload(payload)


@pytest.mark.unit
def test_current_payload_rejects_extra_variant_fields() -> None:
    payload = {
        "submission_value_kind": "token",
        "value": "token-123",
        "github_url": "https://github.com/unexpected",
    }

    with pytest.raises(ValueError, match="Invalid submission value payload fields"):
        submitted_value_from_payload(payload)


@pytest.mark.unit
def test_variant_constructors_reject_noncanonical_values() -> None:
    with pytest.raises(ValueError, match="canonical text"):
        TokenValue(" token-123 ")
