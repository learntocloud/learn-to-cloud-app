"""Public community page models."""

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


class CommunityPageData(FrozenModel):
    """Aggregate data shown on the public community page."""

    activity: CommunityActivity
    phase_activity: list[CommunityPhaseActivity]
    graduates: list[CommunityMember]
