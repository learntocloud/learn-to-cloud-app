"""Unit tests for the catalog-backed curriculum read API.

These are pure in-memory lookups over the process-level
``CurriculumCatalog`` singleton (the real packaged artifact), so no DB
or mocking is needed -- every function here is synchronous.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from learn_to_cloud.curriculum.reads import (
    get_phase_by_slug,
    get_topic_containing_step,
)

pytestmark = pytest.mark.unit


class TestGetPhaseBySlug:
    def test_unknown_slug_returns_none(self):
        assert get_phase_by_slug("not-a-real-phase") is None


class TestGetTopicContainingStep:
    def test_unknown_step_uuid_returns_none(self):
        assert get_topic_containing_step(uuid4()) is None
