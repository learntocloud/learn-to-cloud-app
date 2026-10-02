"""Tests for typed submitted-value storage helpers."""

import pytest

from learn_to_cloud.models import SubmissionValueKind
from learn_to_cloud.verification.submission_values import (
    TokenValue,
    submitted_value_from_raw,
)
from tests.support.requirement_factories import (
    ctf_token_requirement,
    deployed_api_requirement,
    profile_readme_requirement,
)


@pytest.mark.unit
def test_token_value_uses_token_column() -> None:
    value = submitted_value_from_raw(ctf_token_requirement(), " token-123 ")

    assert value.kind is SubmissionValueKind.TOKEN
    assert isinstance(value, TokenValue)
    assert value.token == "token-123"
    assert value.as_text == "token-123"


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
def test_variant_constructors_reject_noncanonical_values() -> None:
    with pytest.raises(ValueError, match="canonical text"):
        TokenValue(" token-123 ")
