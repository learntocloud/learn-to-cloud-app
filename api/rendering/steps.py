"""Step rendering utilities shared across page and HTMX routes.

Centralises the step content-object → template-dict conversion so the
same logic isn't duplicated in every route that renders step partials.
"""

from collections.abc import Callable

import markdown

_md = markdown.Markdown(extensions=["fenced_code", "tables"])


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
        "id": getattr(step, "id"),
        "order": step.order,
        "action": getattr(step, "action", ""),
        "title": getattr(step, "title", ""),
        "url": getattr(step, "url", ""),
        "description": getattr(step, "description", ""),
        "description_html": md_renderer(getattr(step, "description", "")),
        "code": getattr(step, "code", ""),
        "options": [],
    }
    sorted_options = sorted(
        getattr(step, "options", []),
        key=lambda option: _provider_sort_key(getattr(option, "provider", "")),
    )

    for opt in sorted_options:
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
