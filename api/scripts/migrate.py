#!/usr/bin/env python3
"""Run Alembic migrations for the configured database.

This is the recommended way to create/update schema locally.

Usage:
    cd api
    .venv/bin/python -m scripts.migrate upgrade
    .venv/bin/python -m scripts.migrate downgrade -1
    .venv/bin/python -m scripts.migrate current
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Alembic migrations")
    sub = parser.add_subparsers(dest="cmd", required=True)

    upgrade = sub.add_parser("upgrade", help="Apply migrations")
    upgrade.add_argument(
        "target",
        nargs="?",
        default="head",
        help="Target revision (default: head)",
    )

    downgrade = sub.add_parser("downgrade", help="Revert migrations")
    downgrade.add_argument(
        "target",
        nargs="?",
        default="-1",
        help="Target revision (default: -1)",
    )

    sub.add_parser("current", help="Show current revision")
    sub.add_parser("history", help="Show revision history")

    stamp = sub.add_parser(
        "stamp",
        help="Mark a revision as applied without running migrations",
    )
    stamp.add_argument(
        "target",
        nargs="?",
        default="head",
        help="Target revision (default: head)",
    )

    return parser.parse_args()


def _get_alembic_config() -> Config:
    # Ensure we can import app modules regardless of cwd.
    api_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(api_dir))

    cfg = Config(str(api_dir / "alembic.ini"))
    # Make script_location absolute so it works from any working directory.
    cfg.set_main_option("script_location", str(api_dir / "alembic"))
    return cfg


def main() -> None:
    args = _parse_args()
    cfg = _get_alembic_config()

    match args.cmd:
        case "upgrade":
            command.upgrade(cfg, args.target)
        case "downgrade":
            command.downgrade(cfg, args.target)
        case "current":
            command.current(cfg)
        case "history":
            command.history(cfg)
        case "stamp":
            command.stamp(cfg, args.target)
        case _:
            raise ValueError(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
