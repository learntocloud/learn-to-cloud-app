"""Learner progress and dashboard models."""

from uuid import UUID

from pydantic import Field, computed_field

from learn_to_cloud.schemas.base import FrozenModel


class TopicProgressData(FrozenModel):
    """Progress status for a topic (service-layer response model)."""

    steps_completed: int
    steps_total: int
    percentage: float
    status: str  # "not_started", "in_progress", "completed"


class LearningProgress(FrozenModel):
    """A learner's checked-step progress, scoped to current catalog steps.

    ``steps_completed`` intersects stored ``learner_step_completions`` UUIDs
    with the catalog's current active step UUIDs, so a retired step never
    inflates progress.
    """

    steps_completed: int
    steps_required: int

    @computed_field
    @property
    def is_complete(self) -> bool:
        """A zero-step phase is learning-complete by definition."""
        return self.steps_completed >= self.steps_required

    @computed_field
    @property
    def percentage(self) -> float:
        if self.steps_required == 0:
            return 100.0
        return round(min(100.0, (self.steps_completed / self.steps_required) * 100), 1)


class VerificationProgress(FrozenModel):
    """A learner's succeeded-attempt progress, scoped to current requirements.

    ``requirements_verified`` intersects distinct requirement UUIDs with a
    ``succeeded`` ``verification_attempts`` outcome against the catalog's
    current active requirement UUIDs -- a ``failed``/``server_error``/
    ``cancelled`` outcome never counts, and a retired requirement UUID never
    inflates progress.
    """

    requirements_verified: int
    requirements_required: int

    @computed_field
    @property
    def is_complete(self) -> bool:
        """A zero-requirement phase is verification-complete by definition."""
        return self.requirements_verified >= self.requirements_required

    @computed_field
    @property
    def percentage(self) -> float:
        if self.requirements_required == 0:
            return 100.0
        return round(
            min(100.0, (self.requirements_verified / self.requirements_required) * 100),
            1,
        )


class PhaseProgressData(FrozenModel):
    """Progress status for a phase (service-layer response model)."""

    learning: LearningProgress
    verification: VerificationProgress
    status: str  # "not_started", "in_progress", "completed"


class PhaseSummaryData(FrozenModel):
    """Phase summary data for the dashboard (service-layer response model).

    Trimmed to exactly what ``dashboard.html`` renders: order, name,
    and progress. Full phase content (description, objectives,
    capstone, requirements) belongs to the phase detail view, not the
    dashboard list.
    """

    order: int
    name: str
    required_for_graduation: bool = True
    progress: PhaseProgressData | None = None


class ContinuePhaseData(FrozenModel):
    """Where the dashboard's "Continue" action should take the learner.

    ``destination_url`` already resolves to the specific place that matters
    -- the first unchecked learning step's topic, or the dedicated phase
    verification workspace once every step is checked -- so templates never
    need to re-derive a phase link from separate id/order/slug fields.
    """

    destination_url: str
    label: str


class DashboardData(FrozenModel):
    """Complete dashboard payload (service-layer response model).

    Exposes two item-weighted totals across all phases' *current* steps and
    requirements, rather than one blended percentage -- see
    ``UserProgress.overall_learning_percentage`` /
    ``overall_verification_percentage``.
    """

    phases: list[PhaseSummaryData]
    learning_percentage: float
    verification_percentage: float
    phases_completed: int
    total_phases: int
    is_program_complete: bool
    continue_phase: ContinuePhaseData | None = None
    optional_phases: list[PhaseSummaryData] = Field(default_factory=list)


class PhaseProgress(FrozenModel):
    """User's progress for a single phase.

    Unified model used by both dashboard and phase detail views. Holds
    learning and verification as two separate, typed measures rather than
    one blended percentage -- a phase is complete only when *both* are
    complete (see ``is_complete``). When ``topic_progress`` is populated,
    provides per-topic breakdown.
    """

    learning: LearningProgress
    verification: VerificationProgress
    topic_progress: dict[UUID, TopicProgressData] | None = None

    @computed_field
    @property
    def is_complete(self) -> bool:
        """Phase is complete only when learning AND verification are both complete."""
        return self.learning.is_complete and self.verification.is_complete

    @computed_field
    @property
    def status(self) -> str:
        """Phase status, naming which of the two measures still needs work.

        ``learning_complete`` and ``verification_complete`` name the
        *finished* measure -- a learner reads "learning complete" as
        "verification is what's left", not as a description of what they
        just did. ``verification_complete`` covers the (rarer, sequential
        gating is verification-only) case where a learner verifies before
        checking off every step.

        Only distinguished when the phase has real work on *both* axes --
        a phase with zero steps or zero requirements is trivially complete
        on that axis (see ``LearningProgress``/``VerificationProgress``),
        and labelling that trivial truth as "complete" would misrepresent a
        phase the learner hasn't touched at all.
        """
        has_any_work = (
            self.learning.steps_required > 0
            or self.verification.requirements_required > 0
        )
        if not has_any_work:
            return "not_started"
        if self.is_complete:
            return "completed"
        has_both_axes = (
            self.learning.steps_required > 0
            and self.verification.requirements_required > 0
        )
        if has_both_axes:
            if self.learning.is_complete:
                return "learning_complete"
            if self.verification.is_complete:
                return "verification_complete"
        if (
            self.learning.steps_completed > 0
            or self.verification.requirements_verified > 0
        ):
            return "in_progress"
        return "not_started"


class UserProgress(FrozenModel):
    """Complete progress summary for a user."""

    phases: dict[int, PhaseProgress]
    total_phases: int
    required_phase_orders: frozenset[int] = frozenset()

    @property
    def graduation_phase_orders(self) -> frozenset[int]:
        """Phase orders that count toward curriculum graduation."""
        return self.required_phase_orders or frozenset(self.phases)

    @computed_field
    @property
    def phases_completed(self) -> int:
        """Count completed phases that are required for graduation."""
        return sum(
            1
            for order, progress in self.phases.items()
            if order in self.graduation_phase_orders and progress.is_complete
        )

    @computed_field
    @property
    def current_phase(self) -> int:
        """First incomplete required phase, or the last required phase."""
        required_orders = sorted(self.graduation_phase_orders)
        for phase_id in required_orders:
            if not self.phases[phase_id].is_complete:
                return phase_id
        return required_orders[-1] if required_orders else 0

    @computed_field
    @property
    def is_program_complete(self) -> bool:
        """True if all graduation-required phases are completed."""
        return self.phases_completed >= self.total_phases

    @computed_field
    @property
    def overall_learning_percentage(self) -> float:
        """Item-weighted learning percentage across graduation phases."""
        required_progress = [
            progress
            for order, progress in self.phases.items()
            if order in self.graduation_phase_orders
        ]
        total_required = sum(p.learning.steps_required for p in required_progress)
        if total_required == 0:
            return 100.0
        completed = sum(
            min(p.learning.steps_completed, p.learning.steps_required)
            for p in required_progress
        )
        return round((completed / total_required) * 100, 1)

    @computed_field
    @property
    def overall_verification_percentage(self) -> float:
        """Item-weighted verification percentage across graduation phases."""
        required_progress = [
            progress
            for order, progress in self.phases.items()
            if order in self.graduation_phase_orders
        ]
        total_required = sum(
            p.verification.requirements_required for p in required_progress
        )
        if total_required == 0:
            return 100.0
        completed = sum(
            min(
                p.verification.requirements_verified,
                p.verification.requirements_required,
            )
            for p in required_progress
        )
        return round((completed / total_required) * 100, 1)
