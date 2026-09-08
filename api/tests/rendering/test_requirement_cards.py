"""Requirement-card state derivation and form integration."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.schemas import HandsOnRequirement

from learn_to_cloud.rendering.requirement_cards import (
    CheckingCardContext,
    FailedCardContext,
    NotStartedCardContext,
    PassedCardContext,
    UnavailableCardContext,
    build_checking_requirement_card_context,
    build_input_error_requirement_card_context,
    build_requirement_card_context,
    build_unavailable_requirement_card_context,
)
from learn_to_cloud.rendering.verification_forms import (
    DerivedFormContext,
    TokenFormContext,
)


def _make_requirement(
    submission_type: SubmissionType,
    required_repo: str | None = None,
) -> HandsOnRequirement:
    from learn_to_cloud_shared_test_support.requirement_factories import (
        make_requirement,
    )

    return make_requirement(
        submission_type,
        slug="req-1",
        name="Test",
        description="Test",
        required_repo=required_repo,
    )


@pytest.mark.unit
class TestBuildRequirementCardContext:
    def test_derivable_profile_readme_builds_required_form_url(self):
        req = _make_requirement(SubmissionType.PROFILE_README)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
        )
        assert isinstance(ctx, NotStartedCardContext)
        form = ctx.verification_form
        assert isinstance(form, DerivedFormContext)
        assert form.url == "https://github.com/alice/alice"
        assert form.action == "/htmx/verifications/req-1/submit/derived"

    def test_derivable_journal_api_verifier_uses_required_repo(self):
        req = _make_requirement(
            SubmissionType.JOURNAL_API_VERIFIER,
            required_repo="learntocloud/journal-starter",
        )
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="bob",
        )
        assert isinstance(ctx, NotStartedCardContext)
        form = ctx.verification_form
        assert isinstance(form, DerivedFormContext)
        assert form.url == "https://github.com/bob/journal-starter"

    def test_token_type_builds_only_token_form_fields(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
        )
        assert isinstance(ctx, NotStartedCardContext)
        form = ctx.verification_form
        assert isinstance(form, TokenFormContext)
        assert form.action == "/htmx/verifications/req-1/submit/value"
        assert form.min_length == 1
        assert not hasattr(form, "url")

    def test_misconfigured_derived_requirement_fails_context_build(self):
        req = _make_requirement(SubmissionType.JOURNAL_API_VERIFIER)
        with (
            patch(
                "learn_to_cloud.rendering.verification_forms.derive_submission_value",
                side_effect=ValueError("missing required_repo"),
            ),
            pytest.raises(ValueError, match="missing required_repo"),
        ):
            build_requirement_card_context(requirement=req, github_username="alice")

    def test_graded_url_exposes_the_url_that_was_verified(self):
        """The verified card shows which value was graded (#701)."""
        req = _make_requirement(SubmissionType.JOURNAL_API_VERIFIER)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
            submission=_make_submission(is_validated=True, verification_completed=True),
        )
        assert isinstance(ctx, PassedCardContext)
        assert ctx.graded_url == "https://github.com/alice/repo"

    def test_graded_url_omits_non_url_submissions(self):
        """Tokens and free text are not echoed back into the verified card."""
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_requirement_card_context(
            requirement=req,
            github_username="alice",
            submission=_make_submission(
                is_validated=True,
                verification_completed=True,
                submitted_value="ctf-token-abc123",
            ),
        )
        assert isinstance(ctx, PassedCardContext)
        assert ctx.graded_url is None

    def test_graded_url_is_none_without_a_submission(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_requirement_card_context(requirement=req, github_username="alice")
        assert isinstance(ctx, NotStartedCardContext)
        assert not hasattr(ctx, "graded_url")


def _make_submission(
    *,
    is_validated: bool,
    verification_completed: bool = False,
    validation_message: str | None = None,
    error_code: str | None = None,
    submitted_value: str = "https://github.com/alice/repo",
):
    from datetime import UTC, datetime

    from learn_to_cloud_shared.schemas import SubmissionData

    return SubmissionData(
        id=uuid4(),
        submitted_value=submitted_value,
        is_validated=is_validated,
        verification_completed=verification_completed,
        validation_message=validation_message,
        error_code=error_code,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


@pytest.mark.unit
class TestBuildRequirementCardContextCardState:
    def test_required_evidence_absence_is_actionable_learner_failure(self):
        ctx = build_requirement_card_context(
            requirement=_make_requirement(SubmissionType.CTF_TOKEN),
            github_username="alice",
            submission=_make_submission(
                is_validated=False,
                verification_completed=True,
                error_code="evidence.required_missing",
                validation_message="Add the required pyproject.toml.",
            ),
        )

        assert isinstance(ctx, FailedCardContext)
        assert ctx.error_code == "evidence.required_missing"
        assert ctx.error_message == "Add the required pyproject.toml."

    def test_evidence_failure_exposes_code_without_partial_feedback(self):
        from learn_to_cloud.rendering.feedback import FeedbackTaskContext

        ctx = build_requirement_card_context(
            requirement=_make_requirement(SubmissionType.CTF_TOKEN),
            github_username="alice",
            submission=_make_submission(
                is_validated=False,
                error_code="evidence.total_limit",
                validation_message="The evidence could not be collected.",
            ),
            feedback_tasks=[
                FeedbackTaskContext(
                    name="Partial review",
                    passed=False,
                    message="Incomplete feedback must not appear",
                    next_steps="",
                    criteria=(),
                )
            ],
            feedback_passed=1,
        )

        assert isinstance(ctx, UnavailableCardContext)
        assert ctx.error_code == "evidence.total_limit"
        assert "Retrying unchanged work may not help." in ctx.message
        assert ctx.feedback_tasks == []
        assert ctx.feedback_passed == 0

    def test_validated_submission_does_not_prepare_a_resubmission_form(self):
        with patch(
            "learn_to_cloud.rendering.verification_forms.derive_submission_value",
            side_effect=ValueError("Form preparation must not run"),
        ):
            ctx = build_requirement_card_context(
                requirement=_make_requirement(SubmissionType.PROFILE_README),
                github_username="alice",
                submission=_make_submission(is_validated=True),
            )

        assert isinstance(ctx, PassedCardContext)

    def test_input_error_keeps_form_and_message(self):
        ctx = build_input_error_requirement_card_context(
            requirement=_make_requirement(SubmissionType.CTF_TOKEN),
            github_username="alice",
            message="Please enter a token.",
        )

        assert isinstance(ctx, NotStartedCardContext)
        assert isinstance(ctx.verification_form, TokenFormContext)
        assert ctx.error_message == "Please enter a token."
        assert ctx.feedback_tasks == []
        assert ctx.feedback_passed == 0

    def test_failed_submission_without_message_uses_default(self):
        ctx = build_requirement_card_context(
            requirement=_make_requirement(SubmissionType.CTF_TOKEN),
            github_username="alice",
            submission=_make_submission(
                is_validated=False, verification_completed=True
            ),
        )

        assert isinstance(ctx, FailedCardContext)
        assert ctx.error_message == "Verification did not pass."

    def test_processing_is_checking_regardless_of_submission(self):
        from learn_to_cloud.core.templates import templates

        req = _make_requirement(SubmissionType.CTF_TOKEN)
        attempt_id = uuid4()
        ctx = build_checking_requirement_card_context(
            requirement=req,
            verification_attempt_id=attempt_id,
            verification_status_delay_seconds=2,
        )
        assert isinstance(ctx, CheckingCardContext)
        assert ctx.kind == "checking"
        html = templates.get_template("partials/requirement_card.html").render(card=ctx)
        assert (
            f'hx-get="/htmx/verification/attempts/status?attempt_id={attempt_id}"'
            in html
        )
        assert "token=" not in html
        assert "queued or being verified" in html
        assert "Analyzing your code" not in html
        assert 'hx-trigger="load delay:2s"' in html

    def test_no_submission_is_not_started(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_requirement_card_context(requirement=req, github_username="alice")
        assert isinstance(ctx, NotStartedCardContext)
        assert ctx.kind == "not_started"
        assert ctx.error_message is None

    def test_validated_submission_is_passed(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        submission = _make_submission(is_validated=True, verification_completed=True)
        ctx = build_requirement_card_context(
            requirement=req, github_username="alice", submission=submission
        )
        assert isinstance(ctx, PassedCardContext)
        assert ctx.kind == "passed"

    def test_learner_failure_is_failed_with_validation_message(self):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        submission = _make_submission(
            is_validated=False,
            verification_completed=True,
            validation_message="Token did not match.",
        )
        ctx = build_requirement_card_context(
            requirement=req, github_username="alice", submission=submission
        )
        assert isinstance(ctx, FailedCardContext)
        assert ctx.kind == "failed"
        assert ctx.error_message == "Token did not match."

    def test_persisted_system_fault_is_unavailable_not_failed(self):
        """A persisted incomplete result is not a failed learner attempt."""
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        submission = _make_submission(is_validated=False, verification_completed=False)
        ctx = build_requirement_card_context(
            requirement=req, github_username="alice", submission=submission
        )
        assert isinstance(ctx, UnavailableCardContext)
        assert ctx.kind == "unavailable"
        assert "Verification stopped before it could finish." in ctx.message
        assert "Your work was not judged to have failed." in ctx.message
        assert "You can try again" in ctx.message
        assert "report the issue" in ctx.message

    def test_explicit_server_error_overrides_missing_submission(self):
        """The live submit/poll flow can force 'unavailable' with no row yet."""
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        ctx = build_unavailable_requirement_card_context(
            requirement=req,
            github_username="alice",
            message="Verification could not be started.",
        )
        assert ctx.kind == "unavailable"
        assert "Verification could not be started." in ctx.message
        assert "Your work was not judged to have failed." in ctx.message

    @pytest.mark.parametrize(
        "cause",
        [
            "GitHub API error (503). Try again later.",
            "Network error connecting to GitHub. Try again later.",
            "GitHub API error (401). Try again later.",
            "Verification failed before recording a result.",
        ],
    )
    def test_unavailable_preserves_saved_cause_without_guessing(self, cause):
        req = _make_requirement(SubmissionType.CTF_TOKEN)
        submission = _make_submission(is_validated=False, validation_message=cause)

        ctx = build_requirement_card_context(
            requirement=req, github_username="alice", submission=submission
        )

        assert isinstance(ctx, UnavailableCardContext)
        assert cause in ctx.message
        assert "Your work was not judged to have failed." in ctx.message
        assert "report the issue" in ctx.message
        assert "You do not need to change your work" in ctx.message
