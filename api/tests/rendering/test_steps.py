"""Unit tests for rendering.steps module.

Tests cover:
- render_md markdown to HTML conversion
- _process_admonitions blockquote callout conversion
- _provider_sort_key cloud provider ordering
- build_step_data LearningStep to template dict
"""

import pytest

from rendering.steps import (
    _process_admonitions,
    _provider_sort_key,
    build_step_data,
    render_md,
)
from schemas import LearningStep, ProviderOption

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

    def test_admonition_tip(self):
        result = render_md("> [!TIP] Use this.")
        assert "callout-tip" in result
        assert "Use this." in result

    def test_admonition_warning(self):
        result = render_md("> [!WARNING] Be careful.")
        assert "callout-warning" in result

    def test_admonition_note(self):
        result = render_md("> [!NOTE] Take note.")
        assert "callout-note" in result

    def test_admonition_important(self):
        result = render_md("> [!IMPORTANT] Do this.")
        assert "callout-important" in result

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
    def test_azure_first(self):
        assert _provider_sort_key("azure") == (0, "azure")

    def test_aws_second(self):
        assert _provider_sort_key("aws") == (1, "aws")

    def test_gcp_third(self):
        assert _provider_sort_key("gcp") == (2, "gcp")

    def test_unknown_last(self):
        assert _provider_sort_key("other") == (3, "other")

    def test_case_insensitive(self):
        assert _provider_sort_key("Azure") == (0, "azure")

    def test_empty_string(self):
        assert _provider_sort_key("") == (3, "")

    def test_ordering(self):
        assert _provider_sort_key("azure") < _provider_sort_key("aws")
        assert _provider_sort_key("aws") < _provider_sort_key("gcp")
        assert _provider_sort_key("gcp") < _provider_sort_key("other")


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
