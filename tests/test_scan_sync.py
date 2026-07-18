import os
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from main import MainWindow


class FakeDatabase:
    def __init__(self, envs):
        self.envs = list(envs)
        self.saved = []
        self.deleted = []

    def list_environments(self, env_type=None):
        if env_type:
            return [env for env in self.envs if env.env_type == env_type]
        return list(self.envs)

    def save_environment(self, env):
        self.saved.append(env)

    def delete_environment(self, env_id):
        self.deleted.append(env_id)

    def get_environment_by_location(self, location):
        for env in reversed(self.saved + self.envs):
            if env.location == location:
                return env
        return None


def env(env_id, name, location, env_type="local"):
    return SimpleNamespace(
        id=env_id,
        name=name,
        location=location,
        env_type=env_type,
        python_version="3.11",
        packages=[],
        created_at="",
        size_mb=0.0,
        tool="venv",
        metadata_json={},
    )


class ScanSyncTests(unittest.TestCase):
    def _window_with_db(self, db):
        window = MainWindow.__new__(MainWindow)
        window.db = db
        return window

    def test_prune_missing_removes_stale_database_environment(self):
        db = FakeDatabase([
            env("keep", "keep", "C:/envs/keep"),
            env("stale", "stale", "C:/envs/stale"),
        ])
        window = self._window_with_db(db)

        new_envs, updated_envs, removed_envs = window._save_scanned_environments(
            [env("scanned-keep", "keep", "C:/envs/keep")],
            "local",
            prune_missing=True,
        )

        self.assertEqual(new_envs, [])
        self.assertEqual(len(updated_envs), 1)
        self.assertEqual([item.id for item in removed_envs], ["stale"])
        self.assertEqual(db.deleted, ["stale"])

    def test_non_pruning_save_keeps_stale_database_environment(self):
        db = FakeDatabase([
            env("keep", "keep", "C:/envs/keep"),
            env("stale", "stale", "C:/envs/stale"),
        ])
        window = self._window_with_db(db)

        window._save_scanned_environments(
            [env("scanned-keep", "keep", "C:/envs/keep")],
            "local",
            prune_missing=False,
        )

        self.assertEqual(db.deleted, [])

    def test_import_finished_refreshes_current_environment_without_full_scan(self):
        imported = env("keep", "keep", "C:/envs/keep")
        imported.packages = ["requests==2.31.0", "numpy==2.0.0"]
        db = FakeDatabase([imported])
        window = self._window_with_db(db)
        scan_calls = []
        window.scan_all_environments = lambda: scan_calls.append(True)
        window.set_status_message = lambda *args, **kwargs: None
        window._show_info_box = lambda *args, **kwargs: None
        window._get_live_widget_attr = lambda _attr: None

        window.on_import_finished(imported, "local")

        self.assertEqual(scan_calls, [])
        self.assertEqual(db.saved[-1].name, "keep")
        self.assertEqual(len(db.saved[-1].packages), 2)

    def test_export_finished_does_not_scan_environments(self):
        window = self._window_with_db(FakeDatabase([]))
        scan_calls = []
        window.scan_all_environments = lambda: scan_calls.append(True)
        window.set_status_message = lambda *args, **kwargs: None
        window._show_info_box = lambda *args, **kwargs: None

        with tempfile.TemporaryDirectory() as tmp:
            file_name = os.path.join(tmp, "environment.yml")
            window.on_export_finished("name: demo\n", file_name, "demo", "local")
            with open(file_name, "r", encoding="utf-8") as handle:
                content = handle.read()

        self.assertEqual(content, "name: demo\n")
        self.assertEqual(scan_calls, [])


if __name__ == "__main__":
    unittest.main()
