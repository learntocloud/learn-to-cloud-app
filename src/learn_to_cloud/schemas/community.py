"""Public community page models."""

from datetime import datetime

from learn_to_cloud.schemas.base import FrozenModel


class CommunityMember(FrozenModel):
    """A learner shown publicly on the community page."""

    github_username: str
    avatar_url: str | None = None


class CommunityActivity(FrozenModel):
    """Recent verification activity across the current curriculum."""

    active_learners: int
    attempts: int
    projects_verified: int


class CommunityPhaseActivity(FrozenModel):
    """Recent verification activity for one curriculum phase."""

    phase_order: int
    label: str
    active_learners: int
    attempts: int
    projects_verified: int


class RepoUpdate(FrozenModel):
    """Latest commit for a curriculum repo (service-layer response model).

    ``available`` is False when the GitHub lookup failed (rate limit,
    network error); the page still renders the repo with a fallback.
    """

    name: str
    url: str
    available: bool = True
    commit_message: str | None = None
    commit_author: str | None = None
    commit_url: str | None = None
    committed_at: datetime | None = None


class CommunityPageData(FrozenModel):
    """Aggregate data shown on the public community page."""

    activity: CommunityActivity
    phase_activity: list[CommunityPhaseActivity]
    graduates: list[CommunityMember]
    repo_updates: list[RepoUpdate]
