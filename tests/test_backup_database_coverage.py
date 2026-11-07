import os
import runpy
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import create_app
from scripts import backup_database


def test_backup_non_sqlite_backend(monkeypatch):
    class FakeURL:
        def get_backend_name(self):
            return "postgresql"
        database = "test.db"

    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    monkeypatch.setattr(backup_database, "create_app", lambda: app)

    with app.app_context():
        monkeypatch.setattr(backup_database.db.engine, "url", FakeURL())
        with pytest.raises(RuntimeError, match="supports SQLite only"):
            backup_database.create_backup()


def test_backup_in_memory_sqlite(monkeypatch):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    monkeypatch.setattr(backup_database, "create_app", lambda: app)

    with pytest.raises(RuntimeError, match="file-based SQLite database is required"):
        backup_database.create_backup()


def test_backup_relative_database_path(tmp_path, monkeypatch):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })

    # create relative_test.db in parent of app.root_path
    target = Path(app.root_path).parent / "relative_test.db"
    conn = sqlite3.connect(str(target))
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INT)")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(backup_database, "create_app", lambda: app)

    with app.app_context():
        new_url = backup_database.db.engine.url.set(database="relative_test.db")
        monkeypatch.setattr(backup_database.db.engine, "url", new_url)

        res = backup_database.create_backup()
        assert res.is_file()
        assert res.parent == backup_dir

    target.unlink(missing_ok=True)


def test_backup_integrity_check_failure(tmp_path, monkeypatch):
    db_file = tmp_path / "test_corrupt.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INT)")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file.as_posix()}",
    })
    monkeypatch.setattr(backup_database, "create_app", lambda: app)

    class ConnectionWrapper:
        def __init__(self, real_conn, corrupt=False):
            self._conn = real_conn
            self._corrupt = corrupt
        def backup(self, target):
            return self._conn.backup(getattr(target, "_conn", target))
        def execute(self, sql, *args, **kwargs):
            if self._corrupt and "PRAGMA integrity_check" in sql:
                m = MagicMock()
                m.fetchone.return_value = ("corrupt",)
                return m
            return self._conn.execute(sql, *args, **kwargs)
        def close(self):
            return self._conn.close()
        def __getattr__(self, name):
            return getattr(self._conn, name)

    orig_connect = sqlite3.connect
    def custom_connect(path, *args, **kwargs):
        c = orig_connect(path, *args, **kwargs)
        if "electronics_store_" in str(path):
            return ConnectionWrapper(c, corrupt=True)
        return ConnectionWrapper(c, corrupt=False)

    monkeypatch.setattr(backup_database.sqlite3, "connect", custom_connect)

    with pytest.raises(RuntimeError, match="Backup integrity check failed"):
        backup_database.create_backup()


def test_backup_empty_file_failure(tmp_path, monkeypatch):
    db_file = tmp_path / "test_empty.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INT)")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file.as_posix()}",
    })
    monkeypatch.setattr(backup_database, "create_app", lambda: app)

    orig_stat = Path.stat
    def custom_stat(self, *a, **k):
        if "electronics_store_" in self.name:
            class FakeStat:
                st_size = 0
            return FakeStat()
        return orig_stat(self, *a, **k)

    monkeypatch.setattr(Path, "stat", custom_stat)

    with pytest.raises(RuntimeError, match="Backup file is empty"):
        backup_database.create_backup()


def test_backup_main_cli_success(tmp_path, monkeypatch):
    backup_dir = tmp_path / "cli_backups"
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    runpy.run_path("scripts/backup_database.py", run_name="__main__")


def test_backup_main_cli_failure():
    with patch("app.create_app", side_effect=RuntimeError("simulated error")):
        with pytest.raises(SystemExit) as exc:
            runpy.run_path("scripts/backup_database.py", run_name="__main__")
        assert exc.value.code == 1
