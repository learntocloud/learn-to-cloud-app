"""Typed storage helpers for submitted verification values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

from learn_to_cloud_shared.models import SubmissionType, SubmissionValueKind
from learn_to_cloud_shared.schemas import HandsOnRequirement

_GITHUB_URL_TYPES = {
    SubmissionType.GITHUB_PROFILE.value,
    SubmissionType.PROFILE_README.value,
    SubmissionType.REPO_FORK.value,
    SubmissionType.JOURNAL_API_VERIFIER.value,
    SubmissionType.DEVOPS_ANALYSIS.value,
    SubmissionType.SECURITY_SCANNING.value,
    "ci_status",
}
_TOKEN_TYPES = {
    SubmissionType.CTF_TOKEN.value,
    SubmissionType.NETWORKING_TOKEN.value,
    "iac_token",
}
_DEPLOYED_URL_TYPES = {SubmissionType.DEPLOYED_API.value}


class SubmittedValueColumns(Protocol):
    submission_value_kind: str
    github_url: str | None
    token_value: str | None
    deployed_url: str | None
    text_value: str | None
    submitted_value: str


@dataclass(frozen=True, slots=True)
class SubmittedValue:
    """A submitted value normalized into its database storage shape."""

    kind: SubmissionValueKind
    github_url: str | None = None
    token_value: str | None = None
    deployed_url: str | None = None
    text_value: str | None = None

    @property
    def as_text(self) -> str:
        match self.kind:
            case SubmissionValueKind.GITHUB_URL:
                value = self.github_url
            case SubmissionValueKind.TOKEN:
                value = self.token_value
            case SubmissionValueKind.DEPLOYED_URL:
                value = self.deployed_url
            case SubmissionValueKind.TEXT:
                value = self.text_value
        if value is None:
            raise ValueError(f"Missing value for {self.kind.value}")
        return value

    def to_columns(self) -> dict[str, str | None]:
        return {
            "submitted_value": self.as_text,
            "submission_value_kind": self.kind.value,
            "github_url": self.github_url,
            "token_value": self.token_value,
            "deployed_url": self.deployed_url,
            "text_value": self.text_value,
        }

    def to_payload(self) -> dict[str, str | None]:
        return self.to_columns()

    @classmethod
    def from_payload(cls, payload: object) -> SubmittedValue:
        if not isinstance(payload, Mapping):
            raise TypeError("Expected submission_value payload object")
        payload_map: dict[str, object] = {}
        for key, value in payload.items():
            if not isinstance(key, str):
                raise TypeError("Expected string submission_value payload keys")
            payload_map[key] = value
        kind = payload_map.get("submission_value_kind")
        if not isinstance(kind, str):
            raise TypeError("Expected submission_value_kind payload field")
        return cls.from_columns(
            kind=kind,
            github_url=_optional_str(payload_map.get("github_url"), "github_url"),
            token_value=_optional_str(payload_map.get("token_value"), "token_value"),
            deployed_url=_optional_str(
                payload_map.get("deployed_url"),
                "deployed_url",
            ),
            text_value=_optional_str(payload_map.get("text_value"), "text_value"),
            legacy_value=_optional_str(
                payload_map.get("submitted_value"),
                "submitted_value",
            ),
        )

    @classmethod
    def from_raw(
        cls,
        requirement: HandsOnRequirement,
        raw_value: str,
    ) -> SubmittedValue:
        kind = value_kind_for_submission_type(requirement.submission_type)
        value = raw_value.strip()
        if not value:
            raise ValueError("Submitted value cannot be empty.")

        match kind:
            case SubmissionValueKind.GITHUB_URL:
                _validate_github_url(value)
                return cls(kind=kind, github_url=value)
            case SubmissionValueKind.TOKEN:
                return cls(kind=kind, token_value=value)
            case SubmissionValueKind.DEPLOYED_URL:
                _validate_http_url(value, field_name="deployed API URL")
                return cls(kind=kind, deployed_url=value)
            case SubmissionValueKind.TEXT:
                return cls(kind=kind, text_value=value)

    @classmethod
    def from_columns(
        cls,
        *,
        kind: str | SubmissionValueKind,
        github_url: str | None,
        token_value: str | None,
        deployed_url: str | None,
        text_value: str | None,
        legacy_value: str | None = None,
    ) -> SubmittedValue:
        normalized_kind = (
            kind if isinstance(kind, SubmissionValueKind) else SubmissionValueKind(kind)
        )
        value = _single_value_for_kind(
            normalized_kind,
            github_url=github_url,
            token_value=token_value,
            deployed_url=deployed_url,
            text_value=text_value,
        )
        if legacy_value is not None and legacy_value != value:
            raise ValueError("Legacy submitted_value does not match typed value")
        return cls(
            kind=normalized_kind,
            github_url=github_url,
            token_value=token_value,
            deployed_url=deployed_url,
            text_value=text_value,
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
    raise ValueError(f"Unknown submission_type for submitted value: {raw_type!r}")


def submission_value_from_columns(row: SubmittedValueColumns) -> SubmittedValue:
    return SubmittedValue.from_columns(
        kind=row.submission_value_kind,
        github_url=row.github_url,
        token_value=row.token_value,
        deployed_url=row.deployed_url,
        text_value=row.text_value,
        legacy_value=row.submitted_value,
    )


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"Expected string payload field: {field_name}")
    return value


def _single_value_for_kind(
    kind: SubmissionValueKind,
    *,
    github_url: str | None,
    token_value: str | None,
    deployed_url: str | None,
    text_value: str | None,
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
