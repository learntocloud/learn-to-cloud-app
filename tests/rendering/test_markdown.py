"""Unit tests for the markdown renderer.

Covers:
- ``render_md`` markdown to HTML conversion
- ``_process_admonitions`` blockquote callout conversion
- ``render_md`` is memoized so repeated calls hit the cache
"""

import pytest

from learn_to_cloud.rendering.markdown import _process_admonitions, render_md


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
        result = render_md("```\ncode\n```")
        assert "<pre>" in result and "<code>" in result

    def test_table(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |"
        result = render_md(md)
        assert "<table>" in result

    def test_is_cached(self):
        # Sentinel: two calls with the same input return the *exact same*
        # string instance, proving the lru_cache is wired.
        a = render_md("# Hello")
        b = render_md("# Hello")
        assert a is b

    @pytest.mark.parametrize(
        "admon_type,expected_class,expected_label",
        [
            ("TIP", "callout-tip", "<strong>Tip:</strong>"),
            ("WARNING", "callout-warning", "<strong>Warning:</strong>"),
            ("IMPORTANT", "callout-important", "<strong>Important:</strong>"),
            ("NOTE", "callout-note", "<strong>Note:</strong>"),
            ("HINT", "callout-tip", "<strong>Hint:</strong>"),
        ],
    )
    def test_admonition_types(self, admon_type, expected_class, expected_label):
        result = render_md(f"> [!{admon_type}] Body here")
        assert expected_class in result
        assert expected_label in result

    def test_reference_definitions_do_not_leak_between_documents(self):
        first = render_md(
            "[first-document-only]: https://example.com/first-document\n\n"
            "[reference][first-document-only]"
        )
        second = render_md("[reference][first-document-only]")

        assert '<a href="https://example.com/first-document">' in first
        assert "[reference][first-document-only]" in second
        assert "<a " not in second


@pytest.mark.unit
class TestProcessAdmonitions:
    def test_admonition_markup_is_converted(self):
        result = _process_admonitions(
            "<blockquote><p>[!NOTE] Keep this body.</p></blockquote>"
        )
        assert 'class="callout callout-note"' in result
        assert "<strong>Note:</strong> Keep this body." in result
        assert "<blockquote>" not in result

    def test_blockquote_without_admonition_is_preserved(self):
        html = "<blockquote><p>Plain quote</p></blockquote>"
        assert _process_admonitions(html) == html
