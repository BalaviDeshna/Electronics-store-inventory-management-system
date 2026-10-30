import sqlite3
import pytest

from app import create_app
from scripts import backup_database


def test_create_backup_successfully(tmp_path, monkeypatch):
    source_path = tmp_path / "source.db"
    backup_dir = tmp_path / "backups"

    # Create a small SQLite database with sample data.
    with sqlite3.connect(source_path) as connection:
        connection.execute(
            "CREATE TABLE backup_test (id INTEGER PRIMARY KEY, name TEXT)"
        )
        connection.execute(
            "INSERT INTO backup_test (name) VALUES (?)",
            ("test record",),
        )

    # Configure the app to use the temporary database.
    test_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{source_path.as_posix()}",
    })

    monkeypatch.setattr(
        backup_database,
        "create_app",
        lambda: test_app,
    )
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))

    backup_path = backup_database.create_backup()

    assert backup_path.is_file()
    assert backup_path.stat().st_size > 0

    # Verify the backup contains the original data.
    with sqlite3.connect(backup_path) as connection:
        result = connection.execute(
            "SELECT name FROM backup_test"
        ).fetchone()
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()

    assert result == ("test record",)
    assert integrity == ("ok",)


def test_create_backup_fails_when_database_is_missing(tmp_path, monkeypatch):
    source_path = tmp_path / "missing.db"

    test_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{source_path.as_posix()}",
    })

    # Ensure the test database is not created.
    with test_app.app_context():
        from app.data.extensions import db
        db.engine.dispose()

    source_path.unlink(missing_ok=True)

    monkeypatch.setattr(
        backup_database,
        "create_app",
        lambda: test_app,
    )

    with pytest.raises(FileNotFoundError, match="Database file not found"):
        backup_database.create_backup()