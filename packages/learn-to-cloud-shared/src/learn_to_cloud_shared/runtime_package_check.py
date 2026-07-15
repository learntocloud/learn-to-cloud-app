"""Validate the installed shared package's runtime curriculum contract."""

from importlib.resources import files
from pathlib import Path

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog


def main() -> None:
    """Verify the compiled curriculum exists and authored YAML does not."""
    catalog = get_curriculum_catalog()
    if not catalog.phases:
        raise RuntimeError("Runtime package did not load the curriculum artifact.")

    phases_path = Path(
        str(files("learn_to_cloud_shared").joinpath("content", "phases"))
    )
    if phases_path.exists():
        raise RuntimeError(f"Runtime package contains authored YAML at {phases_path}.")


if __name__ == "__main__":
    main()
