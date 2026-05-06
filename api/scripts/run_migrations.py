import alembic.command
import alembic.config


def main() -> None:
    """Run all Alembic migrations."""
    alembic.command.upgrade(alembic.config.Config("alembic.ini"), "head")


if __name__ == "__main__":
    main()
