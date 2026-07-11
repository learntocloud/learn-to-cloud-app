"""The GitHub identity a hands-on requirement verifies against.

Every repo- or profile-based verification points at a deterministic GitHub
location built from two atoms: the learner's ``github_username`` and the
requirement's upstream ``required_repo``. ``GitHubTarget`` captures that
location as a pure value object so the pipeline constructs it once (see
``submission_derivation.build_target``) and reads it everywhere instead of
parsing it back out of a URL.

A target is either profile-level (``repo is None``) or a repository. Repo
targets that must be a fork carry ``forked_from``, the upstream ``owner/name``
their parent is checked against.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GitHubTarget:
    """A GitHub profile or repository a verification runs against."""

    owner: str
    repo: str | None = None
    forked_from: str | None = None

    @property
    def is_repo(self) -> bool:
        """True when this target names a repository rather than a profile."""
        return self.repo is not None

    @property
    def full_name(self) -> str | None:
        """``owner/repo`` for a repository target, else ``None``."""
        return f"{self.owner}/{self.repo}" if self.repo is not None else None

    @property
    def url(self) -> str:
        """Canonical ``https://github.com/...`` URL for this target."""
        if self.repo is not None:
            return f"https://github.com/{self.owner}/{self.repo}"
        return f"https://github.com/{self.owner}"
