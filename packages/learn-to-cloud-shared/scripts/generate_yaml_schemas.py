"""Generate JSON Schema files from Pydantic curriculum models.

These JSON Schemas drive editor support (autocomplete, validation) for
the curriculum YAML files. They are generated from the same Pydantic
models that the loader uses at runtime, so they stay in lock-step.

Run from the package root::

    cd packages/learn-to-cloud-shared && uv run python scripts/generate_yaml_schemas.py

Output:
    src/learn_to_cloud_shared/content/schemas/phase.schema.json
    src/learn_to_cloud_shared/content/schemas/topic.schema.json

A CI check regenerates these and fails if the committed files differ
(see .github/workflows/deploy.yml).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from learn_to_cloud_shared.schemas import Phase, Topic

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


def main() -> int:
    phase_schema = Phase.model_json_schema()
    topic_schema = Topic.model_json_schema()

    phase_path = SCHEMAS_DIR / "phase.schema.json"
    topic_path = SCHEMAS_DIR / "topic.schema.json"

    _write_schema(phase_path, phase_schema)
    _write_schema(topic_path, topic_schema)

    print(f"Wrote {phase_path.relative_to(Path.cwd())}")
    print(f"Wrote {topic_path.relative_to(Path.cwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
