"""Unit tests for rendering.steps module.

Tests cover:
- render_md markdown to HTML conversion
- _process_admonitions blockquote callout conversion
- _provider_sort_key cloud provider ordering
- build_step_data LearningStep to template dict
"""

import pytest
from learn_to_cloud_shared.schemas import LearningStep, ProviderOption

from learn_to_cloud.rendering.steps import (
    _process_admonitions,
    _provider_sort_key,
    build_step_data,
    render_md,
)

# ---------------------------------------------------------------------------
# render_md
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderMd:
    def test_basic_paragraph(self):
        result = render_md("hello world")
        assert "<p>" in result
        assert "hello world" in result

    def test_empty_string(self):
        assert render_md("") == ""

    def test_none(self):
        assert render_md(None) == ""

    def test_fenced_code(self):
        result = render_md("```python\nprint('hi')\n```")
        assert "<code" in result

    @pytest.mark.parametrize(
        "admonition,css_class",
        [
            ("TIP", "callout-tip"),
            ("WARNING", "callout-warning"),
            ("NOTE", "callout-note"),
            ("IMPORTANT", "callout-important"),
        ],
    )
    def test_admonition_types(self, admonition, css_class):
        result = render_md(f"> [!{admonition}] Test content.")
        assert css_class in result

    def test_regular_blockquote_unchanged(self):
        result = render_md("> Just a normal quote.")
        assert "<blockquote>" in result


# ---------------------------------------------------------------------------
# _process_admonitions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcessAdmonitions:
    def test_no_blockquote_unchanged(self):
        html = "<p>hello</p>"
        assert _process_admonitions(html) == html

    def test_blockquote_without_admonition_unchanged(self):
        html = "<blockquote><p>normal quote</p></blockquote>"
        assert _process_admonitions(html) == html

    def test_single_admonition_unwraps_blockquote(self):
        html = "<blockquote>\n<p>[!TIP]\nUse this.</p>\n</blockquote>"
        result = _process_admonitions(html)
        assert "<blockquote>" not in result
        assert "callout-tip" in result
        assert "Use this." in result

    def test_mixed_content_keeps_blockquote(self):
        html = "<blockquote><p>[!TIP]\nUse this.</p><p>Normal text.</p></blockquote>"
        result = _process_admonitions(html)
        assert "<blockquote>" in result
        assert "callout-tip" in result


# ---------------------------------------------------------------------------
# _provider_sort_key
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProviderSortKey:
    @pytest.mark.parametrize(
        "provider,expected_rank",
        [("azure", 0), ("aws", 1), ("gcp", 2), ("other", 3)],
    )
    def test_provider_ordering(self, provider, expected_rank):
        assert _provider_sort_key(provider)[0] == expected_rank

    def test_case_insensitive(self):
        assert _provider_sort_key("Azure") == (0, "azure")

    def test_empty_string(self):
        assert _provider_sort_key("") == (3, "")


# ---------------------------------------------------------------------------
# build_step_data
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildStepData:
    def test_basic_step(self):
        step = LearningStep(
            id="step-1",
            order=0,
            title="Install",
            description="Do stuff",
        )
        data = build_step_data(step)
        assert data["id"] == "step-1"
        assert data["title"] == "Install"
        assert "<p>" in data["description_html"]

    def test_empty_optional_fields(self):
        step = LearningStep(id="step-1", order=0)
        data = build_step_data(step)
        assert data["action"] == ""
        assert data["title"] == ""
        assert data["url"] == ""
        assert data["code"] == ""

    def test_options_sorted_by_provider(self):
        step = LearningStep(
            id="step-1",
            order=0,
            options=[
                ProviderOption(
                    provider="gcp",
                    title="GCP Guide",
                    url="https://gcp.dev",
                    description="",
                ),
                ProviderOption(
                    provider="azure",
                    title="Azure Guide",
                    url="https://azure.dev",
                    description="",
                ),
                ProviderOption(
                    provider="aws",
                    title="AWS Guide",
                    url="https://aws.dev",
                    description="",
                ),
            ],
        )
        data = build_step_data(step)
        providers = [o["provider"] for o in data["options"]]
        assert providers == ["azure", "aws", "gcp"]

    def test_custom_md_renderer(self):
        step = LearningStep(id="step-1", order=0, description="hello")
        data = build_step_data(step, md_renderer=lambda s: f"CUSTOM:{s}")
        assert data["description_html"] == "CUSTOM:hello"
