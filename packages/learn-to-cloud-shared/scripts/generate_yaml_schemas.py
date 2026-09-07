"""Generate JSON Schema files from Pydantic curriculum models.

These JSON Schemas drive editor support (autocomplete, validation) for
the curriculum YAML files. They are generated from the same Pydantic
models that the loader uses at runtime, so they stay in lock-step.

Run from the package root::

    cd packages/learn-to-cloud-shared && uv run python scripts/generate_yaml_schemas.py

Output:
    src/learn_to_cloud_shared/content/schemas/phase.schema.json
    src/learn_to_cloud_shared/content/schemas/topic.schema.json
    src/learn_to_cloud_shared/content/schemas/requirement.schema.json

A CI check regenerates these and fails if the committed files differ
(see .github/workflows/deploy.yml).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from learn_to_cloud_shared.schemas import (
    HandsOnRequirementAdapter,
    Phase,
    StepAction,
    Topic,
)

SCHEMAS_DIR = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "learn_to_cloud_shared"
    / "content"
    / "schemas"
)


def _write_schema(path: Path, schema: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")


def _topic_authoring_schema() -> dict:
    """Adapt the runtime Topic schema to the authored YAML format."""
    schema = Topic.model_json_schema()

    schema["properties"].pop("order")
    schema["required"].remove("order")
    schema["additionalProperties"] = False

    action_schema = schema["$defs"]["StepAction"]
    action_schema["enum"] = [
        *(action.value for action in StepAction),
        *(f"{action.label}:" for action in StepAction),
    ]
    return schema


def main() -> int:
    phase_schema = Phase.model_json_schema()
    topic_schema = _topic_authoring_schema()
    requirement_schema = HandsOnRequirementAdapter.json_schema()

    phase_path = SCHEMAS_DIR / "phase.schema.json"
    topic_path = SCHEMAS_DIR / "topic.schema.json"
    requirement_path = SCHEMAS_DIR / "requirement.schema.json"

    _write_schema(phase_path, phase_schema)
    _write_schema(topic_path, topic_schema)
    _write_schema(requirement_path, requirement_schema)

    print(f"Wrote {phase_path.relative_to(Path.cwd())}")
    print(f"Wrote {topic_path.relative_to(Path.cwd())}")
    print(f"Wrote {requirement_path.relative_to(Path.cwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
