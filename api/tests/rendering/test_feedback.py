"""Feedback normalization and repository evidence contracts."""

import pytest

from learn_to_cloud.rendering.feedback import (
    FeedbackCriterionContext,
    FeedbackEvidenceContext,
    FeedbackTaskContext,
    feedback_tasks_and_passed,
    prepare_card_feedback,
)

pytestmark = pytest.mark.unit


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
