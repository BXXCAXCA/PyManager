import os
import unittest
from dataclasses import dataclass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from main import CreateEnvDialog
from src.models import ToolType


def _app():
    return QApplication.instance() or QApplication([])


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
        self.load_count = 0

    def _load_from_db(self):
        self.load_count += 1

    def list_mirrors(self, mirror_type=None):
        if mirror_type:
            return [mirror for mirror in self.mirrors if mirror.mirror_type == mirror_type]
        return list(self.mirrors)


class CreateEnvDialogTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.manager = FakeMirrorManager()
        self.dialog = CreateEnvDialog(mirror_manager=self.manager)

    def tearDown(self):
        self.dialog.close()
        self.app.processEvents()

    def _combo_names(self):
        return [
            self.dialog.mirror_combo.itemText(index)
            for index in range(self.dialog.mirror_combo.count())
        ]

    def test_default_conda_tool_only_shows_conda_mirrors(self):
        names = self._combo_names()

        self.assertIn("Conda Mirror", names)
        self.assertNotIn("Pip Mirror", names)

    def test_venv_tool_only_shows_pip_mirrors(self):
        self.dialog.tool_combo.setCurrentText("venv")
        self.app.processEvents()

        names = self._combo_names()
        self.assertIn("Pip Mirror", names)
        self.assertNotIn("Conda Mirror", names)


if __name__ == "__main__":
    unittest.main()
