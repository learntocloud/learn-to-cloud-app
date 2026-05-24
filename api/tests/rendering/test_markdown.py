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


@pytest.mark.unit
class TestProcessAdmonitions:
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
        html = render_md(f"> [!{admon_type}] Body here")
        processed = _process_admonitions(html)
        assert expected_class in processed
        assert expected_label in processed

    def test_blockquote_without_admonition_is_preserved(self):
        html = render_md("> Plain quote")
        processed = _process_admonitions(html)
        assert "<blockquote>" in processed
        assert "callout-" not in processed
