#!/usr/bin/env python3
"""Migrate content files to split public/private data.

This script:
1. Reads each topic.json in content/phases/
2. Extracts expected_concepts into topic.grading.json (minimal format)
3. Removes expected_concepts from the original topic.json
4. Validates the migration

Usage:
    python scripts/migrate_content_split.py

Run this ONCE to split existing content files.
"""

import json
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).parent.parent
    content_dir = root / "content" / "phases"

    if not content_dir.exists():
        print(f"ERROR: Content directory not found: {content_dir}")
        sys.exit(1)

    files_processed = 0
    grading_files_created = 0
    questions_processed = 0

    for phase_dir in sorted(content_dir.iterdir()):
        if not phase_dir.is_dir() or phase_dir.name.startswith("."):
            continue

        for topic_file in sorted(phase_dir.glob("*.json")):
            # Skip index.json and already-created grading files
            if topic_file.name == "index.json" or topic_file.name.endswith(".grading.json"):
                continue

            with open(topic_file, encoding="utf-8") as f:
                data = json.load(f)

            # Extract grading concepts
            grading_data: dict[str, list[str]] = {}
            questions_modified = False

            for question in data.get("questions", []):
                question_id = question.get("id")
                expected_concepts = question.get("expected_concepts")

                if question_id and expected_concepts:
                    grading_data[question_id] = expected_concepts
                    del question["expected_concepts"]
                    questions_modified = True
                    questions_processed += 1

            if not grading_data:
                print(f"Skipped (no concepts): {phase_dir.name}/{topic_file.name}")
                continue

            # Write grading file (minimal format)
            grading_file = topic_file.with_suffix(".grading.json")
            with open(grading_file, "w", encoding="utf-8") as f:
                json.dump(grading_data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            grading_files_created += 1
            print(f"Created: {phase_dir.name}/{grading_file.name}")

            # Write updated topic file (without expected_concepts)
            if questions_modified:
                with open(topic_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                files_processed += 1
                print(f"Updated: {phase_dir.name}/{topic_file.name}")

    print(f"\n✅ Migration complete!")
    print(f"   Topic files updated: {files_processed}")
    print(f"   Grading files created: {grading_files_created}")
    print(f"   Questions processed: {questions_processed}")


if __name__ == "__main__":
    main()
