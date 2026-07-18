import unittest

from src.mirror_manager import Mirror, MirrorManager
from src.models import ToolType


class MirrorManagerTests(unittest.TestCase):
    def test_set_default_mirror_is_scoped_to_selected_type(self):
        manager = MirrorManager()
        manager.mirrors = [
            Mirror("pip-1", "Pip", "https://pypi.org/simple", 0, True, ToolType.VENV, True),
            Mirror("conda-1", "Conda", "https://repo.anaconda.com/pkgs/", 0, False, ToolType.CONDA, False),
        ]

        result = manager.set_default_mirror("conda-1")

        self.assertTrue(result)
        self.assertTrue(manager.mirrors[0].is_default)
        self.assertTrue(manager.mirrors[1].is_default)
        self.assertTrue(manager.mirrors[1].is_active)

    def test_set_default_mirror_reports_missing_id(self):
        manager = MirrorManager()
        manager.mirrors = [
            Mirror("pip-1", "Pip", "https://pypi.org/simple", 0, True, ToolType.VENV, True),
        ]

        result = manager.set_default_mirror("missing")

        self.assertFalse(result)
        self.assertTrue(manager.mirrors[0].is_default)

    def test_retired_mirror_urls_are_repaired_and_deduped(self):
        manager = MirrorManager()
        manager.mirrors = [
            Mirror(
                "old-pip",
                "USTC PyPI",
                "https://mirrors.ustc.edu.cn/pypi/simple",
                0,
                True,
                ToolType.VENV,
                True,
            ),
            Mirror(
                "new-pip",
                "Huawei PyPI",
                "https://repo.huaweicloud.com/repository/pypi/simple",
                0,
                True,
                ToolType.VENV,
                False,
            ),
            Mirror(
                "old-conda",
                "Tsinghua Anaconda Main",
                "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main",
                0,
                True,
                ToolType.CONDA,
                False,
            ),
        ]

        manager._repair_known_urls()
        manager._dedupe_mirrors()

        urls = sorted(mirror.url for mirror in manager.mirrors)
        self.assertEqual(
            urls,
            [
                "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
                "https://repo.huaweicloud.com/repository/pypi/simple",
            ],
        )
        pip_mirror = next(mirror for mirror in manager.mirrors if mirror.mirror_type == ToolType.VENV)
        self.assertTrue(pip_mirror.is_default)


if __name__ == "__main__":
    unittest.main()
