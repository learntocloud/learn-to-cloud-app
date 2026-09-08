"""Feedback normalization and repository evidence contracts."""

import pytest

from learn_to_cloud.rendering.feedback import (
    FeedbackCriterionContext,
    FeedbackEvidenceContext,
    FeedbackTaskContext,
    feedback_tasks_and_passed,
    incomplete_verification_message,
    prepare_card_feedback,
)
from learn_to_cloud.services.submissions_service import feedback_context_from_json

pytestmark = pytest.mark.unit


def test_capstone_feedback_preserves_run_and_commit_without_rubric_criteria():
    sha = "a" * 40
    run_url = "https://github.com/learner/journal-starter/actions/runs/789"
    context = feedback_context_from_json(
        [
            {
                "task_name": "Verify capstone",
                "passed": True,
                "feedback": f"Full capstone verification passed for {sha}. {run_url}",
                "next_steps": "",
                "criterion_results": [],
            }
        ]
    )
    tasks, passed = feedback_tasks_and_passed(context)
    tasks, passed = prepare_card_feedback(
        tasks, passed, "https://github.com/learner/journal-starter"
    )
    assert passed == 1
    assert len(tasks) == 1
    assert tasks[0].name == "Verify capstone"
    assert sha in tasks[0].message
    assert run_url in tasks[0].message
    assert tasks[0].criteria == ()


@pytest.mark.parametrize(
    "error_code",
    [
        "evidence.file_limit",
        "evidence.item_limit",
        "evidence.total_limit",
        "evidence.selection",
        "evidence.configuration",
    ],
)
def test_evidence_service_failure_needs_service_attention(error_code):
    message = incomplete_verification_message("Saved safe cause.", error_code)

    assert "Your work was not judged" in message
    assert "Saved safe cause." in message
    assert "Retrying unchanged work may not help." in message
    assert "Please report the issue" in message
    assert "You do not need to shrink or split your work." in message
    assert "You can try again." not in message


def test_changed_evidence_recommends_stable_repository_retry():
    message = incomplete_verification_message(None, "evidence.changed")

    assert "Your work was not judged" in message
    assert "after the repository stops changing" in message
    assert "report the issue" in message


@pytest.mark.parametrize(
    "error_code",
    [
        "authentication",
        "authorization",
        "client_error",
        "network",
        "provider_unavailable",
        "rate_limit",
    ],
)
def test_retrieval_failure_recommends_retry_later(error_code):
    message = incomplete_verification_message(
        "GitHub API error (401). Try again later.", error_code
    )

    assert message == (
        "Verification is temporarily unavailable because the service could not "
        "retrieve the required evidence. Your work was not evaluated. "
        "Try again in a few minutes. If the problem continues, report the issue."
    )
    assert "401" not in message


@pytest.mark.parametrize("error_code", [None, "historical.unknown"])
def test_unknown_codes_keep_generic_recovery_without_parsing_cause(error_code):
    message = incomplete_verification_message("evidence.total_limit", error_code)

    assert "You can try again." in message
    assert "Retrying unchanged" not in message


@pytest.mark.parametrize("feedback", [None, {}, {"tasks": None}, {"tasks": "invalid"}])
def test_missing_or_invalid_tasks_produce_empty_feedback(feedback):
    assert feedback_tasks_and_passed(feedback) == ([], 0)


def test_feedback_preserves_order_defaults_and_skips_invalid_entries():
    tasks, passed = feedback_tasks_and_passed(
        {
            "tasks": [
                None,
                {"name": "Skip", "criteria": None},
                {
                    "name": "First",
                    "passed": True,
                    "criteria": [
                        None,
                        {
                            "id": "criterion",
                            "kind": "unknown",
                            "status": "unknown",
                            "evidence_refs": ["api/main.py", 7],
                        },
                    ],
                },
                {"name": "Second"},
            ],
            "passed": "1",
        }
    )

    assert passed == 0
    assert [task.name for task in tasks] == ["First", "Second"]
    assert tasks[0].passed is True
    assert tasks[0].message == tasks[0].next_steps == ""
    assert tasks[0].criteria == (
        FeedbackCriterionContext(
            id="criterion",
            label="",
            kind="required",
            status="not_met",
            explanation="",
            next_steps="",
            evidence=(
                FeedbackEvidenceContext(label="api/main.py"),
                FeedbackEvidenceContext(label="7"),
            ),
        ),
    )
    assert tasks[1] == FeedbackTaskContext(
        name="Second", passed=False, message="", next_steps="", criteria=()
    )


def test_feedback_preserves_valid_criteria_and_ignores_non_list_references():
    tasks, passed = feedback_tasks_and_passed(
        {
            "tasks": [
                {
                    "criteria": [
                        {
                            "kind": kind,
                            "status": status,
                            "evidence_refs": "not-a-list",
                        }
                        for kind, status in (
                            ("required", "met"),
                            ("quality", "not_met"),
                            ("bonus", "not_applicable"),
                        )
                    ]
                }
            ],
            "passed": 2,
        }
    )

    assert passed == 2
    assert [(criterion.kind, criterion.status) for criterion in tasks[0].criteria] == [
        ("required", "met"),
        ("quality", "not_met"),
        ("bonus", "not_applicable"),
    ]
    assert all(not criterion.evidence for criterion in tasks[0].criteria)


@pytest.mark.parametrize(
    ("repository_url", "reference", "expected_url"),
    [
        (
            "https://github.com/owner/repo",
            "api/main.py",
            "https://github.com/owner/repo/blob/HEAD/api/main.py",
        ),
        (
            "https://github.com/owner/repo/",
            "api/file#1.py",
            "https://github.com/owner/repo/blob/HEAD/api/file%231.py",
        ),
        ("https://github.com/owner/repo", "", None),
        ("https://github.com/owner/repo", "/etc/passwd", None),
        ("https://github.com/owner/repo", "../secret", None),
        ("https://github.com/owner/repo", "api/../secret", None),
        ("https://github.com/owner/repo", "CI status", None),
        ("https://github.com/owner/repo", "api/\nmain.py", None),
        ("http://github.com/owner/repo", "api/main.py", None),
        ("https://example.com/owner/repo", "api/main.py", None),
        ("https://github.com.evil.test/owner/repo", "api/main.py", None),
        ("https://github.com/owner", "api/main.py", None),
        ("https://github.com/owner/repo/tree/main", "api/main.py", None),
    ],
)
def test_evidence_linking_preserves_labels_and_does_not_mutate_feedback(
    repository_url, reference, expected_url
):
    tasks, passed = feedback_tasks_and_passed(
        {
            "tasks": [
                {
                    "name": "Review",
                    "passed": True,
                    "criteria": [{"evidence_refs": [reference]}],
                }
            ],
            "passed": 1,
        }
    )
    linked_tasks, linked_passed = prepare_card_feedback(tasks, passed, repository_url)

    assert linked_passed == 1
    assert linked_tasks[0].criteria[0].evidence == (
        FeedbackEvidenceContext(label=reference, url=expected_url),
    )
    assert tasks[0].criteria[0].evidence == (FeedbackEvidenceContext(label=reference),)
