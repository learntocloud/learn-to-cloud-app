"""Cross-suite helpers preserve factory freshness and settings isolation."""

import pytest
from learn_to_cloud_shared_test_support.requirement_factories import make_requirement
from learn_to_cloud_shared_test_support.settings import clear_settings_cache

from learn_to_cloud_shared.core.config import (
    get_migration_settings,
    get_web_settings,
    get_worker_settings,
)
from learn_to_cloud_shared.models import SubmissionType


@pytest.mark.parametrize("submission_type", list(SubmissionType))
def test_requirement_factory_produces_fresh_matching_requirements(submission_type):
    first = make_requirement(submission_type)
    second = make_requirement(submission_type)

    assert first.uuid != second.uuid
    assert first.submission_type == second.submission_type == submission_type
    assert first.model_dump(exclude={"uuid"}) == second.model_dump(exclude={"uuid"})


def test_settings_helper_clears_every_cached_settings_instance():
    getters = (get_migration_settings, get_worker_settings, get_web_settings)
    clear_settings_cache()
    try:
        for getter in getters:
            assert getter() is getter()
            assert getter.cache_info().currsize == 1

        clear_settings_cache()

        assert all(getter.cache_info().currsize == 0 for getter in getters)
    finally:
        clear_settings_cache()
