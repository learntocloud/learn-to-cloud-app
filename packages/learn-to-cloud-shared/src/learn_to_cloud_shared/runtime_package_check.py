"""Validate the installed curriculum and verification runtime contracts."""

from importlib import import_module
from importlib.resources import files
from importlib.util import find_spec
from inspect import iscoroutinefunction, signature
from pathlib import Path

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.models import SubmissionType
from learn_to_cloud_shared.verification.workflows import workflow_for


def main() -> None:
    """Check runtime data and catalog imports without contacting services."""
    catalog = get_curriculum_catalog()
    if not catalog.phases:
        raise RuntimeError("Runtime package did not load the curriculum artifact.")

    phases_path = Path(
        str(files("learn_to_cloud_shared").joinpath("content", "phases"))
    )
    if phases_path.exists():
        raise RuntimeError(f"Runtime package contains authored YAML at {phases_path}.")

    package = files("learn_to_cloud_shared")
    for directory in ("testing", "tests"):
        if package.joinpath(directory).is_dir():
            raise RuntimeError(f"Runtime package contains test support: {directory}.")
    if find_spec("learn_to_cloud_shared_test_support") is not None:
        raise RuntimeError(
            "Runtime environment contains development-only test support."
        )

    import_module("learn_to_cloud_shared.verification.engine")
    for submission_type in SubmissionType:
        workflow = workflow_for(submission_type)
        if workflow is None:
            raise RuntimeError(
                f"Runtime package has no workflow for {submission_type}."
            )
        for step in workflow.steps:
            if not iscoroutinefunction(step.check):
                raise RuntimeError(f"Workflow step {step.name} has no async check.")
            signature(step.check).bind(object())


if __name__ == "__main__":
    main()
