#!/usr/bin/env python3
"""Prepare content for frontend deployment.

This script:
1. Copies content/phases to frontend/public/content
2. Strips expected_concepts from all topic JSON files (security)
3. Preserves all other content data

Usage:
    python scripts/prepare_frontend_content.py

Run this before deploying to Azure Static Web Apps.
"""

import json
import shutil
import sys
from pathlib import Path


def main() -> None:
    # Paths
    root = Path(__file__).parent.parent
    source_dir = root / "content" / "phases"
    target_dir = root / "frontend" / "public" / "content"

    if not source_dir.exists():
        print(f"ERROR: Source directory not found: {source_dir}")
        sys.exit(1)

    # Clean target directory
    if target_dir.exists():
        shutil.rmtree(target_dir)
        print(f"Cleaned existing: {target_dir}")

    # Copy directory structure
    target_dir.mkdir(parents=True, exist_ok=True)

    files_processed = 0
    concepts_stripped = 0

    for phase_dir in sorted(source_dir.iterdir()):
        if not phase_dir.is_dir() or phase_dir.name.startswith("."):
            continue

        target_phase_dir = target_dir / phase_dir.name
        target_phase_dir.mkdir(exist_ok=True)

        for json_file in sorted(phase_dir.glob("*.json")):
            target_file = target_phase_dir / json_file.name

            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)

            # Strip expected_concepts from questions
            if "questions" in data:
                for question in data["questions"]:
                    if "expected_concepts" in question:
                        del question["expected_concepts"]
                        concepts_stripped += 1

            # Write cleaned content
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")

            files_processed += 1
            print(f"Processed: {phase_dir.name}/{json_file.name}")

    print(f"\n✅ Done!")
    print(f"   Files processed: {files_processed}")
    print(f"   Questions stripped of expected_concepts: {concepts_stripped}")
    print(f"   Output directory: {target_dir}")


if __name__ == "__main__":
    main()
