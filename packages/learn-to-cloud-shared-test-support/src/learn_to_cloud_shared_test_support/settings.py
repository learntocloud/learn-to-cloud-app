"""Settings isolation for tests across workspace members."""

from learn_to_cloud_shared.core.config import (
    get_migration_settings,
    get_web_settings,
    get_worker_settings,
)


def clear_settings_cache() -> None:
    """Clear all cached settings between tests."""
    get_migration_settings.cache_clear()
    get_worker_settings.cache_clear()
    get_web_settings.cache_clear()
