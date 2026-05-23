"""Entry point for the migration Container App Job.

Runs the full deploy-gate sequence:

1. ``alembic upgrade head`` — apply pending migrations
2. ``alembic current --check-heads`` — assert the database's
   ``alembic_version`` matches the script directory head(s); raises
   :class:`alembic.util.DatabaseNotAtHead` if not. This is the official
   replacement for the previous custom ``_verify_schema_at_head`` check
   removed from ``env.py``.
3. ``alembic check`` — assert the live schema matches ``Base.metadata``
   (autogenerate dry-run). Catches model fields added without
   corresponding migrations.

All three share the same ``Config`` instance and run in the same Python
process, so the ``DefaultAzureCredential`` token cache is hit for the
second and third calls — only one IMDS roundtrip happens per job.
"""

from __future__ import annotations

import logging

import alembic.command
import alembic.config


def main() -> None:
    cfg = alembic.config.Config("alembic.ini")
    alembic.command.upgrade(cfg, "head")
    alembic.command.current(cfg, check_heads=True)
    alembic.command.check(cfg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    main()
