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
4. ``python -m learn_to_cloud_shared.cli.sync_curriculum`` — populate
   curriculum DB tables from packaged YAML (issue #463 / Phase B).
   Runs as a subprocess so its settings singleton starts fresh as
   ``WorkerSettings``; sharing the Alembic process would lock it to
   ``DatabaseSettings``.

Steps 1-3 share the same ``Config`` instance and run in the same Python
process, so the ``DefaultAzureCredential`` token cache is hit for the
second and third calls — only one IMDS roundtrip happens per job.

The sync CLI lives inside the installed package
(``learn_to_cloud_shared.cli.sync_curriculum``) rather than a
filesystem script, because the runtime container does not copy the
package source tree -- only the installed wheel ends up in
``/app/.venv``. ``python -m`` finds the module via the wheel's import
path, which is portable across local devcontainer, CI, and production.
"""

from __future__ import annotations

import logging
import subprocess
import sys

import alembic.command
import alembic.config

logger = logging.getLogger(__name__)


def _run_curriculum_sync() -> None:
    """Run the curriculum YAML -> DB sync as a separate subprocess.

    Settings-singleton isolation: this entry point's process has already
    instantiated ``DatabaseSettings`` via Alembic. The sync needs
    ``WorkerSettings`` (for ``content_dir_path``), so it must run in a
    fresh interpreter where ``configure_settings(WorkerSettings)`` can
    fire before any other code touches the settings tree.
    """
    logger.info("Running curriculum sync via subprocess")
    result = subprocess.run(
        [sys.executable, "-m", "learn_to_cloud_shared.cli.sync_curriculum"],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Curriculum sync failed with exit code {result.returncode}; "
            "see stderr above. Migration job fails so the deploy is gated."
        )


def main() -> None:
    cfg = alembic.config.Config("alembic.ini")
    alembic.command.upgrade(cfg, "head")
    alembic.command.current(cfg, check_heads=True)
    alembic.command.check(cfg)
    _run_curriculum_sync()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    main()
