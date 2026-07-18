import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QHeaderView

from src.remote_file_browser_panel import RemoteFileBrowserPanel
from src.ssh_client import RemoteFile


def _app():
    return QApplication.instance() or QApplication([])


class FakeSSHClient:
    def __init__(self):
        self.client = object()
        self.sftp = object()
        self.calls = []

    def list_directory(self, path):
        self.calls.append(path)
        return [
            RemoteFile(
                path=f"{path.rstrip('/')}/demo.txt",
                name="demo.txt",
                size=1536,
                is_directory=False,
                permissions="-rw-r--r--",
                modified_time="2026-06-25 12:00:00",
            ),
            RemoteFile(
                path=f"{path.rstrip('/')}/folder",
                name="folder",
                size=0,
                is_directory=True,
                permissions="drwxr-xr-x",
                modified_time="2026-06-25 12:01:00",
            ),
        ]


class RemoteFileBrowserPanelTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.panel = RemoteFileBrowserPanel(FakeSSHClient())

    def tearDown(self):
        self.panel.close()
        self._drain_events()

    def _drain_events(self, timeout=2.0):
        deadline = time.time() + timeout
        while self.panel.workers and time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(self.panel.workers)

    def test_refresh_files_runs_in_worker_and_populates_table(self):
        seen_paths = []
        self.panel.path_changed.connect(seen_paths.append)

        self.panel.refresh_files("~/project dir")
        self._drain_events()

        self.assertEqual(self.panel.current_path, "~/project dir")
        self.assertEqual(seen_paths, ["~/project dir"])
        self.assertEqual(self.panel.file_table.rowCount(), 2)
        self.assertEqual(self.panel.file_table.item(0, 0).text(), "demo.txt")
        self.assertEqual(self.panel.file_table.item(0, 1).text(), "1.5 KB")
        self.assertEqual(self.panel.file_table.item(1, 1).text(), "")

    def test_stale_refresh_result_is_ignored(self):
        self.panel._refresh_seq = 2

        self.panel._on_files_loaded((1, "/old", []))

        self.assertEqual(self.panel.current_path, ".")

    def test_file_table_column_allocation_prioritizes_name(self):
        header = self.panel.file_table.horizontalHeader()

        self.assertEqual(header.sectionResizeMode(0), QHeaderView.ResizeMode.Stretch)
        self.assertEqual(header.sectionResizeMode(1), QHeaderView.ResizeMode.Fixed)
        self.assertEqual(header.sectionResizeMode(2), QHeaderView.ResizeMode.Fixed)
        self.assertEqual(header.sectionResizeMode(3), QHeaderView.ResizeMode.Fixed)
        self.assertEqual(self.panel.file_table.columnWidth(1), 110)
        self.assertEqual(self.panel.file_table.columnWidth(2), 140)
        self.assertEqual(self.panel.file_table.columnWidth(3), 190)

    def test_remote_path_helpers(self):
        self.assertEqual(self.panel._join_remote_path("~/base", "file.txt"), "~/base/file.txt")
        self.assertEqual(self.panel._join_remote_path("/", "file.txt"), "/file.txt")
        self.assertEqual(self.panel._quote_remote_path("~/dir with space"), "~/'dir with space'")

    def test_format_size(self):
        self.assertEqual(self.panel._format_size(0), "0 B")
        self.assertEqual(self.panel._format_size(1023), "1023 B")
        self.assertEqual(self.panel._format_size(1024), "1.0 KB")
        self.assertEqual(self.panel._format_size(1024 * 1024), "1.0 MB")


if __name__ == "__main__":
    unittest.main()
