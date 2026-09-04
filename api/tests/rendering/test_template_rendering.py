"""Rendered-HTML tests for phase and dashboard progress states."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from learn_to_cloud_shared.schemas import SubmissionData

from learn_to_cloud.core.templates import templates
from learn_to_cloud.rendering.context import (
    COMMUNITY_LINKS,
    HELP_LINKS,
    build_requirement_card_context,
    feedback_tasks_and_passed,
)

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


@pytest.mark.unit
class TestHomePage:
    def test_anonymous_learner_starts_at_first_available_phase(self):
        html = _render(
            "pages/home.html",
            user=None,
            phases=[SimpleNamespace(order=0), SimpleNamespace(order=1)],
        )
        main = html.split("<main", 1)[1].split("</main>", 1)[0]

        assert 'href="/phase/0"' in main
        assert "Start learning" in main
        assert 'href="/curriculum"' in main
        assert 'href="/phase/1"' not in main
        assert "Continue learning" not in main

    def test_returning_learner_continues_from_dashboard(self):
        html = _render("pages/home.html", phases=[SimpleNamespace(order=0)])
        main = html.split("<main", 1)[1].split("</main>", 1)[0]

        assert 'href="/dashboard"' in main
        assert "Continue learning" in main
        assert 'href="/curriculum"' in main
        assert 'href="/phase/0"' not in main

    @pytest.mark.parametrize("signed_in", [False, True])
    def test_missing_curriculum_keeps_recovery_and_dashboard_access(self, signed_in):
        ctx = {} if signed_in else {"user": None}
        html = _render("pages/home.html", phases=[], **ctx)
        main = html.split("<main", 1)[1].split("</main>", 1)[0]

        assert "The learning path is temporarily unavailable." in main
        assert 'href="/" hx-boost="false"' in main
        assert 'href="/faq"' in main
        assert 'href="/phase/' not in main
        assert ('href="/dashboard"' in main) is signed_in


def _requirement(slug: str, name: str, description: str = ""):
    from learn_to_cloud_shared.testing.requirement_factories import (
        ctf_token_requirement,
    )

    return ctf_token_requirement(
        slug=slug,
        name=name,
        description=description,
    )


def _submission(
    *,
    is_validated: bool,
    verification_completed: bool = False,
    validation_message: str | None = None,
    submitted_value: str = "",
    validated_at: datetime | None = None,
) -> SubmissionData:
    return SubmissionData(
        id=uuid4(),
        is_validated=is_validated,
        verification_completed=verification_completed,
        validation_message=validation_message,
        submitted_value=submitted_value,
        validated_at=validated_at,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _card_contexts(
    requirements: list[Any],
    submissions_by_req: dict[str, SubmissionData],
) -> dict[str, object]:
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
def test_phase5_holistic_feedback_renders_in_shared_panel():
    html = _render(
        "partials/verification_feedback.html",
        feedback_tasks=[
            {
                "name": "DevOps Implementation Review",
                "passed": False,
                "message": (
                    "Dockerfile and CI/CD are sound; Kubernetes references "
                    "a different image."
                ),
                "next_steps": "Align the workflow and Deployment image reference.",
            }
        ],
        feedback_passed=0,
        requirement_slug="devops-implementation",
    )

    assert "DevOps Implementation Review" in html
    assert "Kubernetes references" in html
    assert "Align the workflow" in html
    assert 'id="feedback-panel-devops-implementation"' in html


@pytest.mark.unit
def test_failing_feedback_panel_opens_by_default():
    """A failed grade shows its per-dimension rationale without a click (#699)."""
    html = _render(
        "partials/verification_feedback.html",
        feedback_tasks=[
            {
                "name": "Logging",
                "passed": False,
                "message": "No structured logging found.",
                "next_steps": "Add a logger to the create endpoint.",
            },
            {"name": "Validation", "passed": True, "message": "Looks good."},
        ],
        feedback_passed=1,
        requirement_slug="journal-api-implementation",
    )

    assert 'x-data="{ expanded: true }"' in html
    assert "1/2 automated checks passed — what to fix" in html
    assert "No structured logging found." in html
    assert "Add a logger to the create endpoint." in html


@pytest.mark.unit
def test_passing_feedback_panel_stays_collapsed():
    """A passing grade with no advice stays a bare summary."""
    html = _render(
        "partials/verification_feedback.html",
        feedback_tasks=[{"name": "Logging", "passed": True, "message": "Good."}],
        feedback_passed=1,
        requirement_slug="journal-api-implementation",
    )

    assert 'x-data="{ expanded: false }"' in html
    assert "Review summary" in html
    assert "suggestion" not in html


@pytest.mark.unit
def test_passing_feedback_panel_keeps_next_steps():
    """A verified requirement can't be resubmitted, so its advice must survive."""
    html = _render(
        "partials/verification_feedback.html",
        feedback_tasks=[
            {
                "name": "Error Handling",
                "passed": True,
                "message": "Endpoints return the right status codes.",
                "next_steps": "Consider parsing the LLM JSON more defensively.",
            },
            {"name": "Logging", "passed": True, "message": "Good."},
        ],
        feedback_passed=2,
        requirement_slug="journal-api-implementation",
    )

    assert "Review summary" in html
    assert "Consider parsing the LLM JSON more defensively." in html


@pytest.mark.unit
def test_passing_feedback_panel_pluralizes_suggestions():
    html = _render(
        "partials/verification_feedback.html",
        feedback_tasks=[
            {"name": "A", "passed": True, "message": "ok", "next_steps": "do x"},
            {"name": "B", "passed": True, "message": "ok", "next_steps": "do y"},
        ],
        feedback_passed=2,
        requirement_slug="journal-api-implementation",
    )

    assert "Review summary" in html
    assert "do x" in html
    assert "do y" in html


@pytest.mark.unit
def test_structured_feedback_uses_required_counts_and_groups_suggestions():
    html = _render(
        "partials/verification_feedback.html",
        feedback_tasks=[
            {
                "name": "Journal API review",
                "passed": True,
                "message": "The implementation meets the required rubric.",
                "criteria": [
                    {
                        "id": "logging",
                        "label": "Application logging",
                        "kind": "required",
                        "status": "met",
                        "explanation": "Logging is configured in api/main.py.",
                        "next_steps": "",
                        "evidence": [{"label": "api/main.py", "url": None}],
                    },
                    {
                        "id": "validation",
                        "label": "Request validation",
                        "kind": "required",
                        "status": "met",
                        "explanation": "Typed request models validate input.",
                        "next_steps": "",
                        "evidence": [],
                    },
                    {
                        "id": "clarity",
                        "label": "Pythonic clarity",
                        "kind": "quality",
                        "status": "not_met",
                        "explanation": "One dependency is implicit.",
                        "next_steps": "Inject the dependency explicitly.",
                        "evidence": [],
                    },
                ],
            }
        ],
        feedback_passed=1,
        requirement_slug="journal-api-implementation",
    )

    assert "2 of 2 required checks passed" in html
    assert "1 suggestion" in html
    assert "Required checks" in html
    assert "Suggestions" in html
    assert "Application logging" in html
    assert "Evidence reviewed" in html


@pytest.mark.unit
def test_verified_feedback_links_only_safe_repository_evidence():
    tasks, passed = feedback_tasks_and_passed(
        {
            "tasks": [
                {
                    "name": "Journal API review",
                    "passed": True,
                    "message": "The implementation passed.",
                    "criteria": [
                        {
                            "id": "logging",
                            "label": "Application logging",
                            "kind": "required",
                            "status": "met",
                            "explanation": "Logging is configured.",
                            "evidence_refs": ["api/main.py", "../secret", "CI status"],
                        }
                    ],
                }
            ],
            "passed": 1,
        }
    )
    card = build_requirement_card_context(
        requirement=_requirement("journal-api", "Journal API"),
        github_username="tester",
        submission=_submission(
            is_validated=True,
            verification_completed=True,
            submitted_value="https://github.com/tester/journal-starter",
        ),
        feedback_tasks=tasks,
        feedback_passed=passed,
    )

    html = _render("partials/verified_requirement_row.html", card=card)

    assert "tester/journal-starter" in html
    assert "Repository:" not in html
    assert "https://github.com/tester/journal-starter/blob/HEAD/api/main.py" in html
    assert "blob/HEAD/../secret" not in html
    assert "blob/HEAD/CI%20status" not in html


@pytest.mark.unit
class TestPhaseVerificationLocked:
    """The gated branch of pages/verification_phase.html."""

    def _render_phase(
        self,
        requirements: list[Any],
        submissions_by_req: dict[str, SubmissionData],
    ) -> str:
        return _render(
            "pages/verification_phase.html",
            phase=SimpleNamespace(name="Phase 6", description="", order=6),
            phase_progress=SimpleNamespace(
                verification=SimpleNamespace(
                    requirements_required=len(requirements),
                    requirements_verified=len(submissions_by_req),
                    percentage=0,
                    is_complete=False,
                )
            ),
            requirements=requirements,
            card_contexts_by_req=_card_contexts(requirements, submissions_by_req),
            verification_locked=True,
            prerequisite_phase_id=5,
            history=SimpleNamespace(
                items=[],
                page=1,
                has_previous=False,
                has_next=False,
            ),
        )

    def test_validated_requirement_renders_as_complete_when_locked(self):
        """A validated requirement shows the green verified row, not a padlock."""
        req = _requirement("security-scanning", "Enable Security Scanning")
        submission = _submission(is_validated=True, verification_completed=True)

        html = self._render_phase([req], {"security-scanning": submission})

        assert 'id="requirement-security-scanning"' in html
        assert "Enable Security Scanning" in html
        assert "text-green-900 dark:text-green-100" in html
        # The gating banner still appears for the phase overall.
        assert "Phase 5 verification required" in html

    def test_unvalidated_requirement_stays_locked_when_gated(self):
        """A not-yet-validated requirement keeps the padlock row."""
        req = _requirement("ci-status", "CI Status")

        html = self._render_phase([req], {})

        assert "Locked" in html
        assert "text-green-800 dark:text-green-200" not in html

    def test_mixed_shows_validated_complete_and_other_locked(self):
        """Validated and unvalidated requirements render differently."""
        done = _requirement("security-scanning", "Enable Security Scanning")
        todo = _requirement("ci-status", "CI Status")
        submission = _submission(is_validated=True, verification_completed=True)

        html = self._render_phase([done, todo], {"security-scanning": submission})

        assert 'id="requirement-security-scanning"' in html
        assert "text-green-900 dark:text-green-100" in html
        assert "Locked" in html


@pytest.mark.unit
class TestPhaseVerificationCardStates:
    """The unlocked branch's cards in pages/verification_phase.html."""

    def _render_phase(
        self,
        requirements: list[Any],
        submissions_by_req: dict[str, SubmissionData],
    ) -> str:
        return _render(
            "pages/verification_phase.html",
            phase=SimpleNamespace(name="Phase 1", description="", order=1),
            phase_progress=SimpleNamespace(
                verification=SimpleNamespace(
                    requirements_required=len(requirements),
                    requirements_verified=len(submissions_by_req),
                    percentage=0,
                    is_complete=False,
                )
            ),
            requirements=requirements,
            card_contexts_by_req=_card_contexts(requirements, submissions_by_req),
            verification_locked=False,
            prerequisite_phase_id=None,
            history=SimpleNamespace(
                items=[],
                page=1,
                has_previous=False,
                has_next=False,
            ),
        )

    def test_not_started_shows_form_no_pill(self):
        req = _requirement("ci-status", "CI Status")
        html = self._render_phase([req], {})
        assert "Needs work" not in html
        assert "Verified" not in html
        assert 'hx-post="/htmx/verifications/ci-status/submit/value"' in html
        assert 'name="requirement_slug"' not in html
        assert ':disabled="!valid"' in html
        assert 'href="/phase/1"' in html
        assert "Review Phase 1 learning" in html

    def test_token_form_uses_configured_length_limits(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            ctf_token_requirement,
        )

        req = ctf_token_requirement(
            slug="linux-token",
            name="Linux token",
            placeholder="Paste token",
            min_length=200,
            max_length=2048,
        )

        html = self._render_phase([req], {})

        assert 'minlength="200"' in html
        assert 'maxlength="2048"' in html
        assert 'autocomplete="off"' in html
        assert 'spellcheck="false"' in html

    def test_deployed_url_form_uses_url_constraints(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            deployed_api_requirement,
        )

        req = deployed_api_requirement(
            slug="deployed-api",
            min_length=8,
        )

        html = self._render_phase([req], {})

        assert 'type="url"' in html
        assert 'minlength="8"' in html
        assert 'maxlength="2048"' in html
        assert 'autocomplete="url"' in html

    def test_reflection_form_constrains_every_answer(self):
        from learn_to_cloud_shared.testing.requirement_factories import (
            career_reflection_requirement,
        )

        req = career_reflection_requirement(
            slug="career-reflection",
            min_answer_length=200,
            question_count=3,
        )

        html = self._render_phase([req], {})

        assert html.count('name="answers"') == 3
        assert html.count('minlength="200"') == 3
        assert html.count('maxlength="6000"') == 3

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
        assert "a problem on our side, not something you did" in html
        assert "You can try again" in html
        assert "report the issue" in html
        assert "not counted against your rate limit" not in html

    def test_passed_shows_verified_pill(self):
        req = _requirement("ci-status", "CI Status")
        submission = _submission(is_validated=True, verification_completed=True)
        html = self._render_phase([req], {"ci-status": submission})
        # A passed requirement renders via the verified row, not the
        # full interactive card -- see partials/verified_requirement_row.html.
        assert 'id="requirement-ci-status"' in html
        assert "text-green-900 dark:text-green-100" in html
        assert "Verified" in html

    def test_passed_keeps_requirement_context_visible(self):
        """A verified requirement keeps its evidence on screen (#701)."""
        req = _requirement(
            "ci-status",
            "CI Status",
            description="Submit your Journal API fork URL",
        )
        submission = _submission(
            is_validated=True,
            verification_completed=True,
            submitted_value="https://github.com/tester/journal-api",
            validated_at=datetime(2026, 7, 29, 12, 0),
        )
        html = self._render_phase([req], {"ci-status": submission})

        assert "Submit your Journal API fork URL" not in html
        assert "https://github.com/tester/journal-api" in html
        assert "Verified Jul 29, 2026" in html
        assert "Report a problem" in html

    def test_passed_does_not_echo_non_url_submissions(self):
        """Tokens and long free text are not dumped back into the summary."""
        req = _requirement("career-reflection", "Career Reflection")
        submission = _submission(
            is_validated=True,
            verification_completed=True,
            submitted_value="a very long written reflection " * 50,
            validated_at=datetime(2026, 7, 29, 12, 0),
        )
        html = self._render_phase([req], {"career-reflection": submission})

        assert "Graded:" not in html
        assert "a very long written reflection" not in html
        assert "Verified Jul 29, 2026" in html

    def test_readonly_derived_url_is_explained(self):
        """The auto-derived, read-only field says why it can't be edited (#701)."""
        from learn_to_cloud_shared.testing.requirement_factories import (
            journal_api_verifier_requirement,
        )

        req = journal_api_verifier_requirement(
            slug="journal-api",
            name="Journal API",
            required_repo="learntocloud/journal-api",
        )
        html = self._render_phase([req], {})

        assert "readonly" in html
        assert 'hx-post="/htmx/verifications/journal-api/submit/derived"' in html
        assert 'name="submitted_value"' not in html
        assert "Why can't I edit this URL?" in html
        assert "organization" in html

    def test_active_card_uses_concise_requirement_description(self):
        req = _requirement(
            "linux-token",
            "Linux token",
            description="Paste the completion token.",
        )

        html = self._render_phase([req], {})

        assert "Paste the completion token." in html

    def test_failed_feedback_precedes_resubmission_form(self):
        req = _requirement("journal-api", "Journal API")
        submission = _submission(
            is_validated=False,
            verification_completed=True,
            validation_message="The implementation needs work.",
        )
        feedback_tasks, feedback_passed = feedback_tasks_and_passed(
            {
                "tasks": [
                    {
                        "name": "Logging",
                        "passed": False,
                        "message": "Structured logging is missing.",
                    }
                ],
                "passed": 0,
            }
        )
        card = build_requirement_card_context(
            requirement=req,
            github_username="tester",
            submission=submission,
            feedback_tasks=feedback_tasks,
            feedback_passed=feedback_passed,
        )

        html = _render("partials/requirement_card.html", card=card)

        assert html.index("Structured logging is missing.") < html.index("<form")


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
        has_verification=False,
    )

    assert "Verification progress — 1/2 requirements" in html
    assert "Learning progress — 2/5 steps" in html
    assert "Verification is what counts" not in html


@pytest.mark.unit
def test_phase_page_links_to_verification_workspace_without_rendering_form():
    phase_progress = SimpleNamespace(
        status="learning_complete",
        verification=SimpleNamespace(
            requirements_required=2,
            requirements_verified=1,
            percentage=50.0,
            is_complete=False,
        ),
        learning=SimpleNamespace(
            steps_required=5,
            steps_completed=5,
            percentage=100.0,
            is_complete=True,
        ),
    )

    html = _render(
        "pages/phase.html",
        phase=SimpleNamespace(name="Phase 4", description="", order=4),
        topics=[],
        phase_progress=phase_progress,
        has_verification=True,
    )

    assert 'href="/verifications/phase/4"' in html
    assert "Continue verification" in html
    assert 'hx-post="/htmx/github/submit"' not in html


@pytest.mark.unit
def test_phase_verification_renders_paginated_safe_attempt_history():
    requirement = _requirement("journal-api", "Journal API")
    history_item = SimpleNamespace(
        id="history-id",
        requirement=requirement,
        outcome="failed",
        status_label="Needs work",
        status_variant="error",
        validation_message="The required endpoint is missing.",
        feedback_tasks=[
            {
                "name": "API shape",
                "passed": False,
                "message": "No health endpoint was found.",
                "next_steps": "Add GET /health.",
            }
        ],
        feedback_passed=0,
        completed_at=datetime(2026, 8, 28, 18, 0),
    )
    phase_progress = SimpleNamespace(
        verification=SimpleNamespace(
            requirements_required=1,
            requirements_verified=0,
            percentage=0,
            is_complete=False,
        )
    )

    html = _render(
        "pages/verification_phase.html",
        phase=SimpleNamespace(name="Phase 3", description="", order=3),
        phase_progress=phase_progress,
        requirements=[],
        card_contexts_by_req={},
        verification_locked=False,
        prerequisite_phase_id=None,
        history=SimpleNamespace(
            items=[history_item],
            page=2,
            has_previous=True,
            has_next=True,
        ),
    )

    assert "Attempt history" in html
    assert "The required endpoint is missing." in html
    assert "No health endpoint was found." in html
    assert "Add GET /health." in html
    assert "submitted-token-value" not in html
    assert 'href="/verifications/phase/3?history_page=1"' in html
    assert 'href="/verifications/phase/3?history_page=3"' in html


@pytest.mark.unit
def test_step_checkbox_keeps_keyboard_events_from_toggling_accordion():
    loader = _ENV.loader
    assert loader is not None
    source, _, _ = loader.get_source(_ENV, "partials/topic_step.html")
    assert "@keydown.space.stop" in source
    assert "@keydown.enter.stop" in source
    assert 'role="button"' not in source
    assert 'aria-label="Mark {{ step_label }} complete"' in source
    assert "x-collapse x-cloak" in source


@pytest.mark.unit
def test_community_page_renders_activity_and_canonical_footer_link():
    community = SimpleNamespace(
        activity=SimpleNamespace(
            active_learners=42,
            attempts=75,
            projects_verified=20,
        ),
        phase_activity=[
            SimpleNamespace(
                label="Starting from Zero",
                active_learners=30,
                attempts=50,
                projects_verified=12,
            )
        ],
        graduates=[],
        repo_updates=[],
    )

    html = _render(
        "pages/community.html",
        community=community,
        community_links=COMMUNITY_LINKS,
        user=None,
    )

    assert "Learn to Cloud community" in html
    assert "42" in html
    assert "This week in the community" in html
    assert "Starting from Zero" in html
    assert 'href="/community"' in html
    assert 'href="/stats"' not in html


@pytest.mark.unit
def test_community_page_renders_safe_external_resource_links():
    community = SimpleNamespace(
        activity=SimpleNamespace(
            active_learners=0,
            attempts=0,
            projects_verified=0,
        ),
        phase_activity=[],
        graduates=[],
        repo_updates=[],
    )

    html = _render(
        "pages/community.html",
        community=community,
        community_links=COMMUNITY_LINKS,
        user=None,
    )

    expected_links = {
        "https://discord.gg/st7g2Hp77r",
        "https://github.com/learntocloud/learn-to-cloud-app/discussions",
        "https://youtube.com/made-by-gps",
        "https://github.com/learntocloud/learn-to-cloud-app",
        "https://x.com/madebygps",
        "https://x.com/learntocloud",
    }
    for url in expected_links:
        assert f'href="{url}"' in html
    assert html.count('rel="noopener noreferrer"') >= len(expected_links)
    assert "No verification activity has been recorded in the past 7 days." in html
    assert "Curriculum updates are temporarily unavailable." in html
    assert "Discord" in html
    assert "GitHub Discussions" in html
    assert "Follow @madebygps" in html
    assert "Follow @learntocloud" in html


@pytest.mark.unit
def test_dashboard_help_section_links_to_discord():
    dashboard = SimpleNamespace(
        phases=[],
        learning_percentage=0,
        verification_percentage=0,
        phases_completed=0,
        total_phases=0,
        is_program_complete=False,
        continue_phase=None,
    )

    html = _render("pages/dashboard.html", dashboard=dashboard, help_links=HELP_LINKS)

    assert 'href="https://discord.gg/st7g2Hp77r"' in html
    assert "Ask the Community" not in html


@pytest.mark.unit
class TestDashboardPrimaryState:
    @staticmethod
    def _dashboard(
        *,
        phases: list[object],
        continue_phase: object | None = None,
        is_program_complete: bool = False,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            phases=phases,
            learning_percentage=0,
            verification_percentage=0,
            phases_completed=0,
            total_phases=len(phases),
            is_program_complete=is_program_complete,
            continue_phase=continue_phase,
        )

    def test_fresh_learner_sees_start_state(self):
        phase = SimpleNamespace(order=0, name="Prerequisites", progress=None)
        html = _render(
            "pages/dashboard.html",
            dashboard=self._dashboard(phases=[phase]),
            help_links=[],
        )

        assert "Start the curriculum" in html
        assert "Resume" not in html
        assert "Full curriculum" not in html

    def test_returning_learner_sees_resume_state(self):
        phase = SimpleNamespace(order=0, name="Prerequisites", progress=None)
        continue_phase = SimpleNamespace(
            destination_url="/phase/0/linux",
            label="Phase 0: Prerequisites",
        )
        html = _render(
            "pages/dashboard.html",
            dashboard=self._dashboard(phases=[phase], continue_phase=continue_phase),
            help_links=[],
        )

        assert "Continue your path" in html
        assert 'href="/phase/0/linux"' in html

    def test_completed_learner_sees_completion_state(self):
        progress = SimpleNamespace(
            status="completed",
            verification=SimpleNamespace(
                requirements_required=1,
                requirements_verified=1,
            ),
            learning=SimpleNamespace(steps_required=1, steps_completed=1),
        )
        phase = SimpleNamespace(order=0, name="Prerequisites", progress=progress)
        html = _render(
            "pages/dashboard.html",
            dashboard=self._dashboard(phases=[phase], is_program_complete=True),
            help_links=[],
        )

        assert "You completed the program." in html

    def test_missing_curriculum_sees_recovery_state(self):
        html = _render(
            "pages/dashboard.html",
            dashboard=self._dashboard(phases=[]),
            help_links=[],
        )

        assert "Progress is temporarily unavailable." in html
        assert "Try again" in html


@pytest.mark.unit
def test_primary_links_are_in_navbar_and_footer_is_minimal():
    navbar = _render("partials/navbar.html")
    footer = _render("partials/footer.html")

    for path in ("/verifications", "/community", "/faq"):
        assert f'href="{path}"' in navbar
        assert f'href="{path}"' not in footer

    assert 'href="/curriculum"' not in navbar
    assert 'href="/curriculum"' in footer
    assert "Program overview" in footer
    assert 'href="/privacy"' in footer
    assert 'href="/terms"' in footer
    assert "Discord" not in footer
    assert "GitHub" not in footer
    assert "YouTube" not in footer
    assert "Sponsor" not in footer


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
        assert "Complete" in html
        assert "28/28 steps checked" in html
        assert "1/1 requirements verified" in html
        assert 'text-3xl font-bold text-white">' not in html
