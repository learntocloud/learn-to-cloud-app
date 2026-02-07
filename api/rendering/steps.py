"""Step rendering utilities shared across page and HTMX routes.

Centralises the step content-object → template-dict conversion so the
same logic isn't duplicated in every route that renders step partials.
"""

from collections.abc import Callable

import markdown

_md = markdown.Markdown(extensions=["fenced_code", "tables"])


def render_md(text: str | None) -> str:
    """Render markdown text to HTML. Returns empty string if falsy input."""
    if not text:
        return ""
    _md.reset()
    return _md.convert(text)


def build_step_data(
    step,
    *,
    md_renderer: Callable[[str | None], str] = render_md,
) -> dict:
    """Convert a content LearningStep object to a template-ready dict.

    Args:
        step: A LearningStep content object.
        md_renderer: Markdown-to-HTML callable (default: module-level render_md).
    """
    data: dict = {
        "order": step.order,
        "text": getattr(step, "text", ""),
        "action": getattr(step, "action", ""),
        "title": getattr(step, "title", ""),
        "url": getattr(step, "url", ""),
        "description": getattr(step, "description", ""),
        "description_html": md_renderer(getattr(step, "description", "")),
        "code": getattr(step, "code", ""),
        "options": [],
    }
    for opt in getattr(step, "options", []):
        data["options"].append(
            {
                "provider": getattr(opt, "provider", ""),
                "label": getattr(opt, "label", getattr(opt, "provider", "")),
                "title": getattr(opt, "title", ""),
                "url": getattr(opt, "url", ""),
                "description_html": md_renderer(getattr(opt, "description", "")),
            }
        )
    return data
