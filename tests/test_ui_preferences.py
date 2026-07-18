import tempfile
import unittest
from pathlib import Path

from main import MainWindow
from src.database import DatabaseManager
from src.i18n import i18n


def _sqlite_uri(path: Path) -> str:
    return "sqlite:///" + str(path).replace("\\", "/")


class FakeSettingsDatabase:
    def __init__(self, values):
        self.values = values

    def load_app_setting(self, key, default=None):
        return self.values.get(key, default)


class UiPreferenceTests(unittest.TestCase):
    def test_app_setting_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(_sqlite_uri(Path(tmp) / "app.db"))
            try:
                db.save_app_setting("theme", "dark")
                db.save_app_setting("language", "en")

                self.assertEqual(db.load_app_setting("theme"), "dark")
                self.assertEqual(db.load_app_setting("language"), "en")
                self.assertEqual(db.load_app_setting("missing", "fallback"), "fallback")
            finally:
                db.close()

    def test_main_window_loads_saved_ui_preferences(self):
        original_language = i18n.current_lang
        window = MainWindow.__new__(MainWindow)
        window.db = FakeSettingsDatabase({"theme": "dark", "language": "en"})
        try:
            MainWindow._load_ui_preferences(window)

            self.assertEqual(window.current_theme, "dark")
            self.assertEqual(i18n.current_lang, "en")
        finally:
            i18n.set_language(original_language)


if __name__ == "__main__":
    unittest.main()
