"""Learning progress prepared for page and fragment templates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from learn_to_cloud_shared.schemas import Phase, PhaseProgress


def build_progress_dict(completed: int, total: int) -> dict[str, int]:
    """Return completed, total, and rounded percentage for a progress bar."""
    return {
        "completed": completed,
        "total": total,
        "percentage": round(completed / total * 100) if total > 0 else 0,
    }


def build_phase_topics(phase: Phase, detail: PhaseProgress) -> list[dict[str, Any]]:
    """Merge ordered topic metadata with its optional learning progress."""
    topics: list[dict[str, Any]] = []
    for t in phase.topics:
        tp = detail.topic_progress.get(t.uuid) if detail.topic_progress else None
        topics.append(
            {
                "name": t.name,
                "slug": t.slug,
                "progress": (
                    {"completed": tp.steps_completed, "total": tp.steps_total}
                    if tp
                    else None
                ),
            }
        )

    return topics
