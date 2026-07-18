import os
import time
import unittest
from dataclasses import dataclass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.package_management_panel import PackageManagementPanel
from src.models import ToolType


def _app():
    return QApplication.instance() or QApplication([])


class FakePackageManager:
    def __init__(self):
        self.packages = ["requests==2.31.0", "numpy 2.0.0"]

    def _get_installed_packages(self, env_path, use_conda, env_name):
        return list(self.packages)

    def install_package(self, env_name, env_path, package, use_conda, mirror_url=None):
        return True

    def uninstall_package(self, env_name, env_path, package, use_conda):
        return True

    def update_package(self, env_name, env_path, package, use_conda, mirror_url=None):
        return True


@dataclass
class FakeMirror:
    id: str
    name: str
    url: str
    mirror_type: ToolType
    is_active: bool = True


class FakeMirrorManager:
    def __init__(self):
        self.mirrors = [
            FakeMirror("pip-1", "Pip Mirror", "https://example.test/simple", ToolType.VENV),
            FakeMirror("conda-1", "Conda Mirror", "https://conda.example.test/pkgs", ToolType.CONDA),
        ]

    def list_mirrors(self, mirror_type=None):
        if mirror_type:
            return [mirror for mirror in self.mirrors if mirror.mirror_type == mirror_type]
        return list(self.mirrors)


class PackageManagementPanelTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.panel = PackageManagementPanel(
            FakePackageManager(),
            "demo",
            "/tmp/demo",
            False,
            mirror_manager=FakeMirrorManager(),
        )
        self._drain_events()

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

    def test_package_rows_are_marked_as_real_packages(self):
        self.assertEqual(self.panel.package_table.rowCount(), 2)
        self.panel.package_table.selectRow(0)

        self.assertEqual(self.panel._selected_package_name(), "requests")
        self.assertEqual(self.panel.package_table.item(0, 1).text(), "2.31.0")

    def test_placeholder_row_is_not_selectable_as_package(self):
        self.panel._package_load_seq = 10
        self.panel.on_packages_loaded((10, []))
        self.panel.package_table.selectRow(0)

        self.assertIsNone(self.panel._selected_package_name())

    def test_stale_package_load_result_is_ignored(self):
        self.panel._package_load_seq = 2

        self.panel.on_packages_loaded((1, ["old==0.1"]))

        self.assertNotEqual(self.panel.package_table.item(0, 0).text(), "old")

    def test_current_mirror_url_uses_selected_mirror(self):
        self.panel.mirror_combo.setCurrentIndex(1)

        self.assertEqual(self.panel._current_mirror_url(), "https://example.test/simple")

    def test_pip_panel_only_shows_pip_mirrors(self):
        names = [
            self.panel.mirror_combo.itemText(index)
            for index in range(self.panel.mirror_combo.count())
        ]

        self.assertIn("Pip Mirror", names)
        self.assertNotIn("Conda Mirror", names)

    def test_conda_panel_only_shows_conda_mirrors(self):
        conda_panel = PackageManagementPanel(
            FakePackageManager(),
            "demo",
            "/tmp/demo",
            True,
            mirror_manager=FakeMirrorManager(),
        )
        try:
            self._drain_events_for(conda_panel)
            names = [
                conda_panel.mirror_combo.itemText(index)
                for index in range(conda_panel.mirror_combo.count())
            ]

            self.assertIn("Conda Mirror", names)
            self.assertNotIn("Pip Mirror", names)
        finally:
            conda_panel.close()
            self._drain_events_for(conda_panel)

    def test_action_button_state_changes_together(self):
        self.panel._set_action_buttons_enabled(False)
        self.assertFalse(self.panel.install_btn.isEnabled())
        self.assertFalse(self.panel.delete_btn.isEnabled())
        self.assertFalse(self.panel.update_btn.isEnabled())
        self.assertFalse(self.panel.search_btn.isEnabled())

        self.panel._set_action_buttons_enabled(True)
        self.assertTrue(self.panel.install_btn.isEnabled())
        self.assertTrue(self.panel.delete_btn.isEnabled())
        self.assertTrue(self.panel.update_btn.isEnabled())
        self.assertTrue(self.panel.search_btn.isEnabled())

    def _drain_events_for(self, panel, timeout=2.0):
        deadline = time.time() + timeout
        while panel.workers and time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(panel.workers)


if __name__ == "__main__":
    unittest.main()
