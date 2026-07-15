"""Rendered-HTML tests for phase and dashboard templates.

These guard issue #593: a hands-on requirement that was validated before its
phase became gated must still render as complete (not blanket-locked), and the
dashboard tile must not label a hands-on-only phase as "0/N steps".
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from learn_to_cloud.core.templates import templates

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
    return SimpleNamespace(uuid=f"uuid-{slug}", slug=slug, name=name)


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
            progress=None,
            requirements=requirements,
            submissions_by_req=submissions_by_req,
            feedback_by_req={},
            active_jobs_by_req={},
            verification_status_tokens_by_req={},
            derived_urls_by_req={},
            verification_locked=True,
            prerequisite_phase_id=5,
        )

    def test_validated_requirement_renders_as_complete_when_locked(self):
        """A validated requirement shows the green verified row, not a padlock."""
        req = _requirement("security-scanning", "Enable Security Scanning")
        submission = SimpleNamespace(is_validated=True, validation_message=None)

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
        submission = SimpleNamespace(is_validated=True, validation_message=None)

        html = self._render_phase([done, todo], {"security-scanning": submission})

        assert 'id="requirement-security-scanning"' in html
        assert "text-green-800 dark:text-green-200" in html  # the validated one
        assert "opacity-50" in html  # the locked one


@pytest.mark.unit
class TestDashboardTileLabel:
    """The in-progress tile label in pages/dashboard.html."""

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
        return _render("pages/dashboard.html", dashboard=dashboard)

    def test_hands_on_only_phase_shows_hands_on_label(self):
        """Zero steps + validated hands-on shows a hands-on label, not steps."""
        progress = SimpleNamespace(
            status="in_progress",
            learning=SimpleNamespace(
                steps_completed=0, steps_required=28, percentage=0.0
            ),
            verification=SimpleNamespace(
                requirements_verified=1, requirements_required=1, percentage=100.0
            ),
        )

        html = self._render_dashboard(progress)

        assert "1/1 hands-on" in html
        assert "0/28 steps" not in html

    def test_step_progress_phase_shows_steps_label(self):
        """Nonzero step progress keeps the steps label."""
        progress = SimpleNamespace(
            status="in_progress",
            learning=SimpleNamespace(
                steps_completed=5, steps_required=28, percentage=17.9
            ),
            verification=SimpleNamespace(
                requirements_verified=0, requirements_required=1, percentage=0.0
            ),
        )

        html = self._render_dashboard(progress)

        assert "5/28 steps" in html
        assert "hands-on" not in html
