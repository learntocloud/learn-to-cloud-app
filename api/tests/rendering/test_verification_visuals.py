"""Disclosure behavior for mixed verification results."""

from html.parser import HTMLParser

import pytest

from learn_to_cloud.core.templates import templates


class _FeedbackParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.text_contexts: dict[str, tuple[str, ...]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.tags.pop() == tag

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.text_contexts[text] = tuple(self.tags)


@pytest.mark.unit
@pytest.mark.parametrize("structured", [False, True])
def test_mixed_feedback_discloses_passed_checks_but_keeps_fixes_visible(
    structured: bool,
) -> None:
    if structured:
        tasks = [
            {
                "name": "Repository review",
                "passed": False,
                "criteria": [
                    {
                        "id": "readme",
                        "label": "Readme",
                        "kind": "required",
                        "status": "met",
                        "explanation": "Readme is present.",
                        "evidence": [
                            {
                                "label": "README.md",
                                "url": "https://github.com/tester/repo/blob/main/README.md",
                            }
                        ],
                    },
                    {
                        "id": "health",
                        "label": "Health endpoint",
                        "kind": "required",
                        "status": "unmet",
                        "explanation": "Health endpoint is missing.",
                        "next_steps": "Add a health endpoint.",
                    },
                ],
            }
        ]
        passed = 0
    else:
        tasks = [
            {
                "name": "Readme",
                "passed": True,
                "message": "Readme is present.",
            },
            {
                "name": "Health endpoint",
                "passed": False,
                "message": "Health endpoint is missing.",
                "next_steps": "Add a health endpoint.",
            },
        ]
        passed = 1

    html = templates.env.get_template("partials/verification_feedback.html").render(
        feedback_tasks=tasks,
        feedback_passed=passed,
        requirement_slug="journal-api",
    )
    parser = _FeedbackParser()
    parser.feed(html)
    parser.close()

    assert not parser.tags
    assert 'x-data="{ expanded: true }"' in html
    assert 'aria-controls="feedback-panel-journal-api"' in html
    assert 'id="feedback-panel-journal-api" x-show="expanded" x-collapse' in html
    assert "summary" in parser.text_contexts["Passed: Readme"]
    assert "details" in parser.text_contexts["Readme is present."]
    assert "details" not in parser.text_contexts["Health endpoint is missing."]
    assert "details" not in parser.text_contexts["Next step: Add a health endpoint."]
    if structured:
        assert parser.text_contexts["README.md"].count("details") == 2
