"""The GitHub repository a hands-on requirement verifies against."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GitHubRepositoryTarget:
    """A repository and, when required, its expected upstream fork parent."""

    owner: str
    repo: str
    forked_from: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def url(self) -> str:
        """Canonical ``https://github.com/...`` URL for this target."""
        return f"https://github.com/{self.full_name}"
