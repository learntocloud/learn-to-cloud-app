"""Step rendering utilities shared across page and HTMX routes.

Centralises the step content-object → template-dict conversion so the
same logic isn't duplicated in every route that renders step partials.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import markdown

from schemas import LearningStep

_md = markdown.Markdown(extensions=["fenced_code", "tables"])

# GitHub-style admonition types → (CSS class suffix, icon, label)
_ADMONITION_TYPES: dict[str, tuple[str, str, str]] = {
    "TIP": ("tip", "\U0001f4a1", "Tip"),
    "HINT": ("tip", "\U0001f4a1", "Hint"),
    "WARNING": ("warning", "\u26a0\ufe0f", "Warning"),
    "IMPORTANT": ("important", "\u2757", "Important"),
    "NOTE": ("note", "\u2139\ufe0f", "Note"),
}

_ADMONITION_TYPES_PATTERN = "|".join(_ADMONITION_TYPES)

# Matches <p>[!TYPE] content</p> inside a blockquote
_ADMONITION_P_RE = re.compile(
    r"<p>\[!(" + _ADMONITION_TYPES_PATTERN + r")\]\s*\n?(.*?)</p>",
    re.DOTALL | re.IGNORECASE,
)


def _p_to_callout(match: re.Match) -> str:
    """Convert a single <p>[!TYPE] ...</p> into a callout div."""
    admonition_type = match.group(1).upper()
    body = match.group(2).strip()
    css_class, icon, label = _ADMONITION_TYPES[admonition_type]
    return (
        f'<div class="callout callout-{css_class}">'
        f'<span class="callout-icon">{icon}</span>'
        f'<div class="callout-content">'
        f"<strong>{label}:</strong> {body}"
        f"</div></div>"
    )


def _process_admonitions(html: str) -> str:
    """Convert GitHub-style blockquote admonitions to styled callout divs.

    Handles both single-admonition blockquotes and merged blockquotes
    where Markdown combines consecutive ``>`` lines into one
    ``<blockquote>`` with multiple ``<p>`` tags.
    """

    def _replace_blockquote(bq_match: re.Match) -> str:
        inner = bq_match.group(1)
        # If this blockquote has no admonition markers, leave it alone
        if "[!" not in inner:
            return bq_match.group(0)
        # Replace each <p>[!TYPE]...</p> with a callout div
        result = _ADMONITION_P_RE.sub(_p_to_callout, inner)
        # If everything was converted (no leftover <p> tags), unwrap the blockquote
        if "<p>" not in result:
            return result
        # Mixed content: keep non-admonition parts in the blockquote
        return f"<blockquote>{result}</blockquote>"

    return re.sub(
        r"<blockquote>\s*(.*?)\s*</blockquote>",
        _replace_blockquote,
        html,
        flags=re.DOTALL,
    )


def _provider_sort_key(provider: str) -> tuple[int, str]:
    provider_key = (provider or "").strip().lower()
    if provider_key == "azure":
        return (0, provider_key)
    if provider_key == "aws":
        return (1, provider_key)
    if provider_key == "gcp":
        return (2, provider_key)
    return (3, provider_key)


def render_md(text: str | None) -> str:
    """Render markdown text to HTML with GitHub-style admonition support.

    Supports callout syntax in blockquotes:
    ``> [!TIP] Your tip text``
    ``> [!WARNING] Warning text``
    ``> [!IMPORTANT] Important text``
    ``> [!NOTE] Note text``
    ``> [!HINT] Hint text``

    Returns empty string if falsy input.
    """
    if not text:
        return ""
    _md.reset()
    html = _md.convert(text)
    html = _process_admonitions(html)
    return html


def build_step_data(
    step: LearningStep,
    *,
    md_renderer: Callable[[str | None], str] = render_md,
) -> dict[str, Any]:
    """Convert a content LearningStep object to a template-ready dict.

    Args:
        step: A LearningStep content object.
        md_renderer: Markdown-to-HTML callable (default: module-level render_md).
    """
    data: dict[str, Any] = {
        "id": step.id,
        "order": step.order,
        "action": step.action or "",
        "title": step.title or "",
        "url": step.url or "",
        "description": step.description or "",
        "description_html": md_renderer(step.description),
        "code": step.code or "",
        "options": [],
    }
    sorted_options = sorted(
        step.options,
        key=lambda option: _provider_sort_key(option.provider),
    )

    for opt in sorted_options:
        data["options"].append(
            {
                "provider": opt.provider,
                "label": opt.provider,
                "title": opt.title,
                "url": opt.url,
                "description_html": md_renderer(opt.description),
            }
        )
    return data
