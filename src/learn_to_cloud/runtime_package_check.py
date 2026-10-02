"""Validate the installed package carries everything the runtime images need."""

from importlib import import_module
from importlib.metadata import entry_points
from importlib.resources import files
from pathlib import Path

from alembic.script import ScriptDirectory

from learn_to_cloud.curriculum.catalog import get_curriculum_catalog
from learn_to_cloud.migrations import alembic_config


def main() -> None:
    """Check runtime data and catalog imports without contacting services."""
    catalog = get_curriculum_catalog()
    if not catalog.phases:
        raise RuntimeError("Runtime package did not load the curriculum artifact.")

    phases_path = Path(str(files("learn_to_cloud").joinpath("content", "phases")))
    if phases_path.exists():
        raise RuntimeError(f"Runtime package contains authored YAML at {phases_path}.")

    package = files("learn_to_cloud")
    for directory in ("testing", "tests"):
        if package.joinpath(directory).is_dir():
            raise RuntimeError(f"Runtime package contains test support: {directory}.")

    if ScriptDirectory.from_config(alembic_config()).get_current_head() is None:
        raise RuntimeError("Runtime package did not include migration scripts.")

    if not package.joinpath("static", "css", "styles.css").is_file():
        raise RuntimeError("Runtime package did not include compiled CSS.")

    if not entry_points(group="console_scripts", name="learn-to-cloud-migrate"):
        raise RuntimeError("Runtime package did not install learn-to-cloud-migrate.")

    import_module("learn_to_cloud.verification.engine")


if __name__ == "__main__":
    main()
