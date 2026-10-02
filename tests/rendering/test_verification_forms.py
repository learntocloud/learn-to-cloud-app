"""Verification form preparation contracts."""

import pytest

from learn_to_cloud.models import SubmissionType
from learn_to_cloud.rendering.templates import templates
from learn_to_cloud.rendering.verification_forms import (
    DeployedUrlFormContext,
    ReflectionFormContext,
    TokenFormContext,
    build_verification_form_context,
)
from learn_to_cloud.schemas.verification import SubmissionData
from learn_to_cloud.verification.forms import (
    MAX_REFLECTION_ANSWER_LENGTH,
    verification_submit_action,
)
from tests.support.requirement_factories import (
    career_reflection_requirement,
    ctf_token_requirement,
    deployed_api_requirement,
    make_requirement,
    networking_token_requirement,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "factory", [ctf_token_requirement, networking_token_requirement]
)
@pytest.mark.parametrize("placeholder", [None, "Paste the lab token"])
def test_token_form_uses_configured_limits_and_shared_action(factory, placeholder):
    requirement = factory(placeholder=placeholder, min_length=100, max_length=500)
    form = build_verification_form_context(requirement, "learner", None)

    assert isinstance(form, TokenFormContext)
    assert form.placeholder == (placeholder or "Paste your completion token here")
    assert (form.min_length, form.max_length) == (100, 500)
    assert form.action == verification_submit_action(
        requirement.slug, requirement.submission_type
    )


@pytest.mark.parametrize("submitted_value", [None, "https://learner.example.com/api"])
def test_deployed_form_preserves_the_submitted_url(submitted_value):
    requirement = deployed_api_requirement(min_length=8, max_length=512)
    submission = (
        SubmissionData(
            submitted_value=submitted_value,
            is_validated=False,
            verification_completed=True,
        )
        if submitted_value is not None
        else None
    )

    form = build_verification_form_context(requirement, "learner", submission)

    assert isinstance(form, DeployedUrlFormContext)
    assert form.value == (submitted_value or "")
    assert form.placeholder == "https://your-api.example.com"
    assert (form.min_length, form.max_length) == (8, 512)
    assert form.action == verification_submit_action(
        requirement.slug, requirement.submission_type
    )


def test_reflection_form_shares_answer_limits_and_preserves_question_order():
    requirement = career_reflection_requirement(min_answer_length=123, question_count=2)

    form = build_verification_form_context(requirement, "learner", None)

    assert isinstance(form, ReflectionFormContext)
    assert form.questions == tuple(requirement.type_config.questions)
    assert form.min_answer_length == 123
    assert form.max_answer_length == MAX_REFLECTION_ANSWER_LENGTH
    assert form.action == verification_submit_action(
        requirement.slug, requirement.submission_type
    )


@pytest.mark.parametrize("submission_type", list(SubmissionType))
def test_every_submission_type_has_a_renderable_form(submission_type):
    requirement = make_requirement(submission_type)
    form = build_verification_form_context(requirement, "learner", None)

    assert form.action == verification_submit_action(requirement.slug, submission_type)
    html = templates.get_template(form.template).render(
        requirement=requirement,
        verification_form=form,
    )
    assert "<input" in html or "<textarea" in html
