"""Typed storage helpers for submitted verification values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse

from learn_to_cloud_shared.models import SubmissionType, SubmissionValueKind
from learn_to_cloud_shared.schemas import HandsOnRequirement

_GITHUB_URL_TYPES = {
    SubmissionType.PROFILE_README.value,
    SubmissionType.REPO_FORK.value,
    SubmissionType.JOURNAL_API_VERIFIER.value,
    SubmissionType.DEVOPS_ANALYSIS.value,
    SubmissionType.SECURITY_SCANNING.value,
}
_TOKEN_TYPES = {
    SubmissionType.CTF_TOKEN.value,
    SubmissionType.NETWORKING_TOKEN.value,
}
_DEPLOYED_URL_TYPES = {SubmissionType.DEPLOYED_API.value}
_TEXT_TYPES = {
    SubmissionType.CAREER_REFLECTION.value,
    SubmissionType.DEPLOYMENT_ARCHITECTURE.value,
}

# Upper bound on stored free-text answers, guarding against abuse. The
# three reflection answers are combined into one blob before storage.
MAX_TEXT_LENGTH = 20_000


@dataclass(frozen=True, slots=True)
class GitHubUrlValue:
    """A validated GitHub URL submission."""

    github_url: str
    kind: Literal[SubmissionValueKind.GITHUB_URL] = field(
        init=False,
        default=SubmissionValueKind.GITHUB_URL,
    )

    def __post_init__(self) -> None:
        _validate_canonical_value(self.github_url)
        _validate_github_url(self.github_url)

    @property
    def as_text(self) -> str:
        return self.github_url

    def to_payload(self) -> dict[str, str]:
        return {"submission_value_kind": self.kind.value, "value": self.github_url}


@dataclass(frozen=True, slots=True)
class TokenValue:
    """A completion-token submission."""

    token: str
    kind: Literal[SubmissionValueKind.TOKEN] = field(
        init=False,
        default=SubmissionValueKind.TOKEN,
    )

    def __post_init__(self) -> None:
        _validate_canonical_value(self.token)

    @property
    def as_text(self) -> str:
        return self.token

    def to_payload(self) -> dict[str, str]:
        return {"submission_value_kind": self.kind.value, "value": self.token}


@dataclass(frozen=True, slots=True)
class DeployedUrlValue:
    """A deployed HTTP endpoint submission."""

    url: str
    kind: Literal[SubmissionValueKind.DEPLOYED_URL] = field(
        init=False,
        default=SubmissionValueKind.DEPLOYED_URL,
    )

    def __post_init__(self) -> None:
        _validate_canonical_value(self.url)
        _validate_http_url(self.url, field_name="deployed API URL")

    @property
    def as_text(self) -> str:
        return self.url

    def to_payload(self) -> dict[str, str]:
        return {"submission_value_kind": self.kind.value, "value": self.url}


@dataclass(frozen=True, slots=True)
class TextValue:
    """A free-text verification submission."""

    text: str
    kind: Literal[SubmissionValueKind.TEXT] = field(
        init=False,
        default=SubmissionValueKind.TEXT,
    )

    def __post_init__(self) -> None:
        _validate_canonical_value(self.text)
        _validate_text(self.text)

    @property
    def as_text(self) -> str:
        return self.text

    def to_payload(self) -> dict[str, str]:
        return {"submission_value_kind": self.kind.value, "value": self.text}


type SubmittedValue = GitHubUrlValue | TokenValue | DeployedUrlValue | TextValue


def submitted_value_from_raw(
    requirement: HandsOnRequirement,
    raw_value: str,
) -> SubmittedValue:
    """Validate learner input into the requirement's exact value variant."""
    kind = value_kind_for_submission_type(requirement.submission_type)
    value = raw_value.strip()
    if not value:
        raise ValueError("Submitted value cannot be empty.")

    match kind:
        case SubmissionValueKind.GITHUB_URL:
            _validate_github_url(value)
            return GitHubUrlValue(value)
        case SubmissionValueKind.TOKEN:
            return TokenValue(value)
        case SubmissionValueKind.DEPLOYED_URL:
            _validate_http_url(value, field_name="deployed API URL")
            return DeployedUrlValue(value)
        case SubmissionValueKind.TEXT:
            _validate_text(value)
            return TextValue(value)


def submitted_value_from_kind_and_value(
    kind: str | SubmissionValueKind,
    value: str,
) -> SubmittedValue:
    """Restore a typed value from the database's canonical pair."""
    normalized_kind = (
        kind if isinstance(kind, SubmissionValueKind) else SubmissionValueKind(kind)
    )
    match normalized_kind:
        case SubmissionValueKind.GITHUB_URL:
            return GitHubUrlValue(value)
        case SubmissionValueKind.TOKEN:
            return TokenValue(value)
        case SubmissionValueKind.DEPLOYED_URL:
            return DeployedUrlValue(value)
        case SubmissionValueKind.TEXT:
            return TextValue(value)


def submitted_value_from_payload(payload: object) -> SubmittedValue:
    """Deserialize current and legacy Durable workflow value payloads."""
    payload_map = _payload_mapping(payload)
    kind = payload_map.get("submission_value_kind")
    if not isinstance(kind, str):
        raise TypeError("Expected submission_value_kind payload field")
    normalized_kind = SubmissionValueKind(kind)

    if "value" in payload_map:
        _require_payload_keys(payload_map, {"submission_value_kind", "value"})
        value = payload_map["value"]
        if not isinstance(value, str):
            raise TypeError("Expected string payload field: value")
        return submitted_value_from_kind_and_value(normalized_kind, value)

    _require_payload_keys(
        payload_map,
        {
            "submission_value_kind",
            "github_url",
            "token_value",
            "deployed_url",
            "text_value",
        },
    )
    github_url = _optional_str(payload_map.get("github_url"), "github_url")
    token_value = _optional_str(payload_map.get("token_value"), "token_value")
    deployed_url = _optional_str(payload_map.get("deployed_url"), "deployed_url")
    text_value = _optional_str(payload_map.get("text_value"), "text_value")
    value = _single_value_for_kind(
        normalized_kind,
        github_url=github_url,
        token_value=token_value,
        deployed_url=deployed_url,
        text_value=text_value,
    )
    return submitted_value_from_kind_and_value(normalized_kind, value)


def submitted_value_matches_requirement(
    requirement: HandsOnRequirement,
    submitted_value: SubmittedValue,
) -> bool:
    """Return whether a value variant belongs to the requirement type."""
    return submitted_value.kind is value_kind_for_submission_type(
        requirement.submission_type
    )


def value_kind_for_submission_type(
    submission_type: SubmissionType | str,
) -> SubmissionValueKind:
    raw_type = (
        submission_type.value
        if isinstance(submission_type, SubmissionType)
        else submission_type
    )
    if raw_type in _GITHUB_URL_TYPES:
        return SubmissionValueKind.GITHUB_URL
    if raw_type in _TOKEN_TYPES:
        return SubmissionValueKind.TOKEN
    if raw_type in _DEPLOYED_URL_TYPES:
        return SubmissionValueKind.DEPLOYED_URL
    if raw_type in _TEXT_TYPES:
        return SubmissionValueKind.TEXT
    raise ValueError(f"Unknown submission_type for submitted value: {raw_type!r}")


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"Expected string payload field: {field_name}")
    return value


def _payload_mapping(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise TypeError("Expected submission_value payload object")
    payload_map: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("Expected string submission_value payload keys")
        payload_map[key] = value
    return payload_map


def _require_payload_keys(
    payload: Mapping[str, object],
    expected: set[str],
) -> None:
    actual = set(payload)
    if actual != expected:
        raise ValueError(
            f"Invalid submission value payload fields: {sorted(actual - expected)}"
        )


def _single_value_for_kind(
    kind: SubmissionValueKind,
    *,
    github_url: str | None,
    token_value: str | None,
    deployed_url: str | None,
    text_value: str | None = None,
) -> str:
    values = {
        SubmissionValueKind.GITHUB_URL: github_url,
        SubmissionValueKind.TOKEN: token_value,
        SubmissionValueKind.DEPLOYED_URL: deployed_url,
        SubmissionValueKind.TEXT: text_value,
    }
    value = values[kind]
    other_values = [item for item_kind, item in values.items() if item_kind != kind]
    if value is None or any(item is not None for item in other_values):
        raise ValueError(f"Invalid typed value columns for {kind.value}")
    return value


def _validate_text(value: str) -> None:
    if len(value) > MAX_TEXT_LENGTH:
        raise ValueError(
            f"Submitted text must be at most {MAX_TEXT_LENGTH} characters.",
        )


def _validate_canonical_value(value: str) -> None:
    if not value or value != value.strip():
        raise ValueError("Submitted value must be non-empty canonical text.")


def _validate_github_url(value: str) -> None:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or not parsed.path.strip("/")
        or _has_whitespace(value)
    ):
        raise ValueError("Submitted value must be a GitHub URL.")


def _validate_http_url(value: str, *, field_name: str) -> None:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or _has_whitespace(value)
    ):
        raise ValueError(f"Submitted value must be a valid {field_name}.")


def _has_whitespace(value: str) -> bool:
    return any(character.isspace() for character in value)
