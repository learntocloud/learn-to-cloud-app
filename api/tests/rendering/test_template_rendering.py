"""Rendered-HTML tests for phase and dashboard progress states."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from learn_to_cloud.core.templates import templates
from learn_to_cloud.rendering.context import build_requirement_card_context

_ENV = templates.env


def _base_ctx(**overrides: object) -> dict[str, object]:
    ctx: dict[str, object] = dict(
        request=SimpleNamespace(url=SimpleNamespace(path="/")),
        static_url=lambda p: f"/static/{p}",
        frontend_telemetry=None,
        now=datetime(2026, 1, 1),
        user=SimpleNamespace(
            github_username="tester", first_name="Tester", avatar_url=None
        ),
    )
    ctx.update(overrides)
    return ctx


def _render(template_name: str, **ctx: object) -> str:
    return _ENV.get_template(template_name).render(**_base_ctx(**ctx))


def _requirement(slug: str, name: str) -> SimpleNamespace:
    from learn_to_cloud_shared.models import SubmissionType

    return SimpleNamespace(
        uuid=f"uuid-{slug}",
        slug=slug,
        name=name,
        description="",
        submission_type=SubmissionType.CTF_TOKEN,
    )


def _submission(
    *,
    is_validated: bool,
    verification_completed: bool = False,
    validation_message: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        is_validated=is_validated,
        verification_completed=verification_completed,
        validation_message=validation_message,
        submitted_value="",
    )


def _card_contexts(
    requirements: list[SimpleNamespace],
    submissions_by_req: dict[str, object],
) -> dict[str, dict]:
    """Build the same card_contexts_by_req shape pages_routes.py builds."""
    return {
        req.slug: build_requirement_card_context(
            requirement=req,
            github_username="tester",
            submission=submissions_by_req.get(req.slug),
        )
        for req in requirements
    }


@pytest.mark.unit
class TestPhaseVerificationLocked:
    """The gated (`verification_locked`) branch of pages/phase.html."""

    def _render_phase(
        self,
        requirements: list[SimpleNamespace],
        submissions_by_req: dict[str, object],
    ) -> str:
        return _render(
            "pages/phase.html",
            phase=SimpleNamespace(name="Phase 6", description="", order=6),
            topics=[],
            phase_progress=None,
            requirements=requirements,
            card_contexts_by_req=_card_contexts(requirements, submissions_by_req),
            verification_locked=True,
            prerequisite_phase_id=5,
        )

    def test_validated_requirement_renders_as_complete_when_locked(self):
        """A validated requirement shows the green verified row, not a padlock."""
        req = _requirement("security-scanning", "Enable Security Scanning")
        submission = _submission(is_validated=True, verification_completed=True)

        html = self._render_phase([req], {"security-scanning": submission})

        assert 'id="requirement-security-scanning"' in html
        assert "Enable Security Scanning" in html
        assert "text-green-800 dark:text-green-200" in html
        # The gating banner still appears for the phase overall.
        assert "Phase 5 verification required" in html

    def test_unvalidated_requirement_stays_locked_when_gated(self):
        """A not-yet-validated requirement keeps the padlock row."""
        req = _requirement("ci-status", "CI Status")

        html = self._render_phase([req], {})

        assert "🔒" in html
        assert "opacity-50" in html
        assert "text-green-800 dark:text-green-200" not in html

    def test_mixed_shows_validated_complete_and_other_locked(self):
        """Validated and unvalidated requirements render differently."""
        done = _requirement("security-scanning", "Enable Security Scanning")
        todo = _requirement("ci-status", "CI Status")
        submission = _submission(is_validated=True, verification_completed=True)

        html = self._render_phase([done, todo], {"security-scanning": submission})

        assert 'id="requirement-security-scanning"' in html
        assert "text-green-800 dark:text-green-200" in html  # the validated one
        assert "opacity-50" in html  # the locked one


@pytest.mark.unit
class TestPhaseVerificationCardStates:
    """The unlocked branch's verification-card states in pages/phase.html."""

    def _render_phase(
        self,
        requirements: list[SimpleNamespace],
        submissions_by_req: dict[str, object],
    ) -> str:
        return _render(
            "pages/phase.html",
            phase=SimpleNamespace(name="Phase 1", description="", order=1),
            topics=[],
            phase_progress=None,
            requirements=requirements,
            card_contexts_by_req=_card_contexts(requirements, submissions_by_req),
            verification_locked=False,
            prerequisite_phase_id=None,
        )

    def test_not_started_shows_form_no_pill(self):
        req = _requirement("ci-status", "CI Status")
        html = self._render_phase([req], {})
        assert "Needs work" not in html
        assert "Verified" not in html
        assert 'hx-post="/htmx/github/submit"' in html

    def test_failed_shows_needs_work_pill_and_learner_message(self):
        req = _requirement("ci-status", "CI Status")
        submission = _submission(
            is_validated=False,
            verification_completed=True,
            validation_message="CI is not green yet.",
        )
        html = self._render_phase([req], {"ci-status": submission})
        assert "Needs work" in html
        assert "CI is not green yet." in html
        assert "Service unavailable" not in html

    def test_unavailable_shows_service_banner_not_learner_failure(self):
        """Regression: a persisted server_error/cancelled outcome must not
        render identically to a real learner failure (previously the phase
        page hardcoded server_error=False for every card)."""
        req = _requirement("ci-status", "CI Status")
        submission = _submission(is_validated=False, verification_completed=False)
        html = self._render_phase([req], {"ci-status": submission})
        assert "Service unavailable" in html
        assert "Needs work" not in html
        assert "not counted against your rate limit" in html
        assert html.count("not counted against your rate limit") == 1

    def test_passed_shows_verified_pill(self):
        req = _requirement("ci-status", "CI Status")
        submission = _submission(is_validated=True, verification_completed=True)
        html = self._render_phase([req], {"ci-status": submission})
        # A passed requirement renders via the compact verified row, not the
        # full interactive card -- see partials/verified_requirement_row.html.
        assert 'id="requirement-ci-status"' in html
        assert "text-green-800 dark:text-green-200" in html
        assert "Verified" in html


@pytest.mark.unit
class TestProgressBarAccessibility:
    """Progress bars expose visible text plus ARIA value attributes."""

    def test_topic_progress_bar_has_progressbar_role(self):
        html = _render(
            "partials/topic_progress.html",
            progress={"completed": 2, "total": 5, "percentage": 40},
        )
        assert 'role="progressbar"' in html
        assert 'aria-valuenow="40"' in html
        assert 'aria-valuemin="0"' in html
        assert 'aria-valuemax="100"' in html
        assert "2/5 steps checked" in html


@pytest.mark.unit
def test_phase_progress_uses_distinct_labels_without_explanatory_copy():
    phase_progress = SimpleNamespace(
        status="in_progress",
        verification=SimpleNamespace(
            requirements_required=2,
            requirements_verified=1,
            percentage=50.0,
            is_complete=False,
        ),
        learning=SimpleNamespace(
            steps_required=5,
            steps_completed=2,
            percentage=40.0,
            is_complete=False,
        ),
    )
    html = _render(
        "pages/phase.html",
        phase=SimpleNamespace(name="Phase 1", description="", order=1),
        topics=[],
        phase_progress=phase_progress,
        requirements=[],
    )

    assert "Verification progress — 1/2 requirements" in html
    assert "Learning progress — 2/5 steps" in html
    assert "Verification is what counts" not in html


@pytest.mark.unit
def test_step_checkbox_keeps_keyboard_events_from_toggling_accordion():
    loader = _ENV.loader
    assert loader is not None
    source, _, _ = loader.get_source(_ENV, "partials/topic_step.html")
    assert "@keydown.space.stop" in source
    assert "@keydown.enter.stop" in source


@pytest.mark.unit
class TestDashboardPhaseRow:
    """The phase-row state/labels in pages/dashboard.html."""

    def _render_dashboard(self, progress: object) -> str:
        phase = SimpleNamespace(order=6, name="Phase 6", progress=progress)
        dashboard = SimpleNamespace(
            phases=[phase],
            learning_percentage=3.0,
            verification_percentage=3.0,
            phases_completed=0,
            total_phases=8,
            is_program_complete=False,
            continue_phase=None,
        )
        return _render("pages/dashboard.html", dashboard=dashboard, help_links=[])

    def _progress(
        self,
        *,
        status: str,
        steps_completed: int,
        steps_required: int,
        requirements_verified: int,
        requirements_required: int,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            status=status,
            learning=SimpleNamespace(
                steps_completed=steps_completed,
                steps_required=steps_required,
                percentage=0.0,
            ),
            verification=SimpleNamespace(
                requirements_verified=requirements_verified,
                requirements_required=requirements_required,
                percentage=0.0,
            ),
        )

    def test_hands_on_only_phase_shows_both_counts(self):
        """A hands-on-only phase (zero steps) shows the requirements count."""
        progress = self._progress(
            status="in_progress",
            steps_completed=0,
            steps_required=0,
            requirements_verified=1,
            requirements_required=2,
        )
        html = self._render_dashboard(progress)
        assert "1/2 requirements verified" in html
        assert "0/0 steps checked" not in html

    def test_hero_uses_clear_progress_labels(self):
        progress = self._progress(
            status="in_progress",
            steps_completed=2,
            steps_required=5,
            requirements_verified=1,
            requirements_required=2,
        )
        html = self._render_dashboard(progress)
        assert "Complete each phase's verification to progress." in html
        assert "Verification progress — 3% of requirements" in html
        assert "Learning progress — 3% of learning steps" in html
        assert "Verification is the measure that counts" not in html

    def test_step_progress_phase_shows_both_counts(self):
        progress = self._progress(
            status="in_progress",
            steps_completed=5,
            steps_required=28,
            requirements_verified=0,
            requirements_required=1,
        )
        html = self._render_dashboard(progress)
        assert "5/28 steps checked" in html
        assert "0/1 requirements verified" in html

    def test_learning_complete_state_shows_ready_for_verification(self):
        progress = self._progress(
            status="learning_complete",
            steps_completed=28,
            steps_required=28,
            requirements_verified=0,
            requirements_required=1,
        )
        html = self._render_dashboard(progress)
        assert "Ready for verification" in html

    def test_completed_state_has_no_duplicate_percentage_span(self):
        """The old top-right duplicate percentage span is gone entirely --
        the hero shows each measure's percentage exactly once, in its own
        labelled bar, and the phase row shows counts, not a percentage."""
        progress = self._progress(
            status="completed",
            steps_completed=28,
            steps_required=28,
            requirements_verified=1,
            requirements_required=1,
        )
        html = self._render_dashboard(progress)
        assert "Complete ✓" in html
        assert "28/28 steps checked" in html
        assert "1/1 requirements verified" in html
        assert 'text-3xl font-bold text-white">' not in html
