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
    *,
    has_verification: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return topic links, continuing to verification after the final topic."""
    current_idx = next((i for i, t in enumerate(topics) if t.slug == current_slug), -1)
    if current_idx == -1:
        return None, None

    phase_link = {
        "name": phase_name,
        "url": f"/phase/{phase_id}",
    }

    if current_idx == 0:
        prev_topic = phase_link
    else:
        prev_t = topics[current_idx - 1]
        prev_topic = {
            "name": prev_t.name,
            "url": f"/phase/{phase_id}/{prev_t.slug}",
        }

    if current_idx == len(topics) - 1:
        next_topic = (
            {
                "label": "Next step",
                "name": f"Continue to Phase {phase_id} verification",
                "url": f"/verifications/phase/{phase_id}",
            }
            if has_verification
            else phase_link
        )
    else:
        next_t = topics[current_idx + 1]
        next_topic = {
            "name": next_t.name,
            "url": f"/phase/{phase_id}/{next_t.slug}",
        }

    return prev_topic, next_topic
