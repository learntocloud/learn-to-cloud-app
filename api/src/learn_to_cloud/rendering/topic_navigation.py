"""Previous and next links for topic pages."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from learn_to_cloud_shared.schemas import Topic


def build_topic_nav(
    topics: list[Topic],
    current_slug: str,
    phase_id: int,
    phase_name: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return previous/next topic links, using the phase page at either end."""
    current_idx = next((i for i, t in enumerate(topics) if t.slug == current_slug), -1)
    if current_idx == -1:
        return None, None

    phase_link = {
        "slug": None,
        "name": phase_name,
        "url": f"/phase/{phase_id}",
    }

    if current_idx == 0:
        prev_topic = phase_link
    else:
        prev_t = topics[current_idx - 1]
        prev_topic = {
            "slug": prev_t.slug,
            "name": prev_t.name,
            "url": f"/phase/{phase_id}/{prev_t.slug}",
        }

    if current_idx == len(topics) - 1:
        next_topic = phase_link
    else:
        next_t = topics[current_idx + 1]
        next_topic = {
            "slug": next_t.slug,
            "name": next_t.name,
            "url": f"/phase/{phase_id}/{next_t.slug}",
        }

    return prev_topic, next_topic
