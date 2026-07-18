import sqlite3
import tempfile
import unittest
import gc
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from src.database import DatabaseManager


def _sqlite_uri(path: Path) -> str:
    return "sqlite:///" + str(path).replace("\\", "/")


class DatabaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.temp_dir.name) / "old_app.db"

    def tearDown(self):
        gc.collect()
        self.temp_dir.cleanup()

    @contextmanager
    def _connect_old_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def test_old_server_table_gets_remote_defaults(self):
        with self._connect_old_db() as conn:
            conn.execute(
                """
                CREATE TABLE servers (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    host VARCHAR NOT NULL,
                    port INTEGER,
                    username VARCHAR NOT NULL,
                    auth_type VARCHAR NOT NULL,
                    password VARCHAR,
                    key_path VARCHAR
                )
                """
            )
            conn.execute(
                """
                INSERT INTO servers
                    (id, name, host, port, username, auth_type, password, key_path)
                VALUES
                    ('s1', 'local test', '127.0.0.1', 9999, 'user', 'password', 'user', NULL)
                """
            )

        db = DatabaseManager(_sqlite_uri(self.db_path))
        try:
            server = db.get_server("s1")
            self.assertEqual(server.default_python_path, "/usr/bin/python3")
            self.assertEqual(server.default_env_location, "~/python_envs")
        finally:
            db.close()

    def test_old_mirror_table_gets_default_flag(self):
        with self._connect_old_db() as conn:
            conn.execute(
                """
                CREATE TABLE mirrors (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    url VARCHAR NOT NULL,
                    priority INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1,
                    mirror_type VARCHAR NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO mirrors
                    (id, name, url, priority, is_active, mirror_type)
                VALUES
                    ('m1', 'PyPI', 'https://pypi.org/simple', 0, 1, 'venv')
                """
            )

        db = DatabaseManager(_sqlite_uri(self.db_path))
        try:
            mirror = db.list_mirrors()[0]
            self.assertFalse(mirror.is_default)

            db.set_default_mirror("m1")
            mirror = db.list_mirrors()[0]
            self.assertTrue(mirror.is_default)
            self.assertTrue(mirror.is_active)
        finally:
            db.close()

    def test_default_database_moves_to_config_directory(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp_path = Path(tmp)
            old_config = tmp_path / "config"
            old_config.mkdir()
            old_db = old_config / "app.db"

            with sqlite3.connect(old_db) as conn:
                conn.execute(
                    """
                    CREATE TABLE app_settings (
                        key VARCHAR PRIMARY KEY,
                        value VARCHAR,
                        updated_at DATETIME
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO app_settings (key, value) VALUES ('theme', 'dark')"
                )

            new_config = tmp_path / "PyManagerConfig"
            previous_cwd = os.getcwd()
            os.chdir(tmp_path)
            try:
                with patch.dict(os.environ, {"PYMANAGER_CONFIG_DIR": str(new_config)}):
                    db = DatabaseManager()
                    try:
                        self.assertTrue((new_config / "app.db").exists())
                        self.assertEqual(db.load_app_setting("theme"), "dark")
                    finally:
                        db.close()
            finally:
                os.chdir(previous_cwd)

if __name__ == "__main__":
    unittest.main()
