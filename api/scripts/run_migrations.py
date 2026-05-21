"""Entry point for the migration Container App Job.

Schema verification happens inside ``alembic/env.py`` on the same
connection that ran the upgrade, so this stays a thin wrapper. Kept as a
separate script (rather than calling ``alembic`` directly) so the job
command line stays stable across changes to alembic's CLI.
"""

from __future__ import annotations

import logging

import alembic.command
import alembic.config


def main() -> None:
    alembic.command.upgrade(alembic.config.Config("alembic.ini"), "head")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    main()
