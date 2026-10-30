import logging
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contextlib import closing
from datetime import datetime

from app import create_app
from app.data.extensions import db


logger = logging.getLogger("database_backup")


def create_backup():
    app = create_app()

    with app.app_context():
        database_url = db.engine.url

        if database_url.get_backend_name() != "sqlite":
            raise RuntimeError(
                "This backup script currently supports SQLite only."
            )

        if database_url.database in (None, "", ":memory:"):
            raise RuntimeError(
                "A file-based SQLite database is required."
            )

        source_path = Path(database_url.database)

        if not source_path.is_absolute():
            source_path = Path(app.root_path).parent / source_path

        if not source_path.is_file():
            raise FileNotFoundError(
                f"Database file not found: {source_path}"
            )

        destination = Path(
            os.getenv(
                "BACKUP_DIR",
                str(Path.home() / "Documents" / "ElectronicsStoreBackups"),
            )
        )
        destination.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_path = destination / f"electronics_store_{timestamp}.db"

        try:
            with closing(sqlite3.connect(str(source_path))) as source:
                with closing(sqlite3.connect(str(backup_path))) as backup:
                    source.backup(backup)

                    result = backup.execute(
                        "PRAGMA integrity_check"
                    ).fetchone()

                    if not result or result[0] != "ok":
                        raise RuntimeError(
                            f"Backup integrity check failed: {result}"
                        )

            if backup_path.stat().st_size == 0:
                raise RuntimeError("Backup file is empty.")

            logger.info("Backup completed successfully: %s", backup_path)
            return backup_path

        except Exception:
            backup_path.unlink(missing_ok=True)
            raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        created_backup = create_backup()
        print(f"Backup successful: {created_backup}")
    except Exception:
        logger.exception("Database backup failed")
        sys.exit(1)
