from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from src.models import ToolType


@dataclass
class Mirror:
    id: str
    name: str
    url: str
    priority: int
    is_active: bool
    mirror_type: ToolType
    is_default: bool = False


BUILTIN_MIRRORS = [
    ("PyPI", "https://pypi.org/simple", ToolType.VENV, True),
    ("Aliyun PyPI", "https://mirrors.aliyun.com/pypi/simple", ToolType.VENV, False),
    ("Huawei PyPI", "https://repo.huaweicloud.com/repository/pypi/simple", ToolType.VENV, False),
    ("Anaconda Main", "https://repo.anaconda.com/pkgs/main", ToolType.CONDA, True),
    ("SJTU Anaconda Main", "https://mirror.sjtu.edu.cn/anaconda/pkgs/main", ToolType.CONDA, False),
]

KNOWN_URL_REPLACEMENTS: Dict[str, str] = {
    "https://repo.anaconda.com/pkgs": "https://repo.anaconda.com/pkgs/main",
    "https://repo.anaconda.com/pkgs/": "https://repo.anaconda.com/pkgs/main",
    "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs": "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main",
    "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/": "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main",
    "https://mirrors.aliyun.com/anaconda/pkgs": "https://mirrors.aliyun.com/anaconda/pkgs/main",
    "https://mirrors.aliyun.com/anaconda/pkgs/": "https://mirrors.aliyun.com/anaconda/pkgs/main",
    "https://mirrors.cloud.tencent.com/anaconda/pkgs": "https://mirrors.cloud.tencent.com/anaconda/pkgs/main",
    "https://mirrors.cloud.tencent.com/anaconda/pkgs/": "https://mirrors.cloud.tencent.com/anaconda/pkgs/main",
}

RETIRED_CONDA_URL_REPLACEMENTS: Dict[str, Tuple[str, str]] = {
    "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.bfsu.edu.cn/anaconda/pkgs/main": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.bfsu.edu.cn/anaconda/pkgs/main/": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.nju.edu.cn/anaconda/pkgs/main": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.nju.edu.cn/anaconda/pkgs/main/": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.aliyun.com/anaconda/pkgs/main": (
        "NJU Anaconda Main",
        "https://mirrors.nju.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.aliyun.com/anaconda/pkgs/main/": (
        "NJU Anaconda Main",
        "https://mirrors.nju.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.cloud.tencent.com/anaconda/pkgs/main": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
    "https://mirrors.cloud.tencent.com/anaconda/pkgs/main/": (
        "SJTU Anaconda Main",
        "https://mirror.sjtu.edu.cn/anaconda/pkgs/main",
    ),
}

RETIRED_PIP_URL_REPLACEMENTS: Dict[str, Tuple[str, str]] = {
    "https://pypi.tuna.tsinghua.edu.cn/simple": (
        "Huawei PyPI",
        "https://repo.huaweicloud.com/repository/pypi/simple",
    ),
    "https://pypi.tuna.tsinghua.edu.cn/simple/": (
        "Huawei PyPI",
        "https://repo.huaweicloud.com/repository/pypi/simple",
    ),
    "https://mirrors.ustc.edu.cn/pypi/simple": (
        "Huawei PyPI",
        "https://repo.huaweicloud.com/repository/pypi/simple",
    ),
    "https://mirrors.ustc.edu.cn/pypi/simple/": (
        "Huawei PyPI",
        "https://repo.huaweicloud.com/repository/pypi/simple",
    ),
    "https://mirrors.cloud.tencent.com/pypi/simple": (
        "Huawei PyPI",
        "https://repo.huaweicloud.com/repository/pypi/simple",
    ),
    "https://mirrors.cloud.tencent.com/pypi/simple/": (
        "Huawei PyPI",
        "https://repo.huaweicloud.com/repository/pypi/simple",
    ),
}


class MirrorManager:
    def __init__(self, db_manager=None):
        self.db = db_manager
        self.mirrors: List[Mirror] = []

        if self.db:
            self._load_from_db()
            self._ensure_builtin_mirrors()
            self._ensure_type_defaults()

    def _load_from_db(self):
        if not self.db:
            return

        mirror_models = self.db.list_mirrors()
        self.mirrors = []
        for m in mirror_models:
            self.mirrors.append(
                Mirror(
                    id=m.id,
                    name=m.name,
                    url=m.url,
                    priority=m.priority,
                    is_active=m.is_active,
                    mirror_type=ToolType(m.mirror_type),
                    is_default=m.is_default if hasattr(m, "is_default") else False,
                )
            )

    def _save_mirror(self, mirror: Mirror):
        if self.db:
            self.db.save_mirror(mirror)

    @staticmethod
    def _normalized_url(url: str) -> str:
        return str(url or "").strip().rstrip("/")

    def _repair_known_urls(self):
        for mirror in self.mirrors:
            mirror_url = str(mirror.url or "").strip()
            retired_replacement = RETIRED_CONDA_URL_REPLACEMENTS.get(mirror_url)
            if retired_replacement and mirror.mirror_type == ToolType.CONDA:
                mirror.name, mirror.url = retired_replacement
                self._save_mirror(mirror)
                continue

            retired_replacement = RETIRED_PIP_URL_REPLACEMENTS.get(mirror_url)
            if retired_replacement and mirror.mirror_type == ToolType.VENV:
                mirror.name, mirror.url = retired_replacement
                self._save_mirror(mirror)
                continue

            replacement = KNOWN_URL_REPLACEMENTS.get(mirror_url)
            if replacement and mirror.url != replacement:
                mirror.url = replacement
                retired_replacement = RETIRED_CONDA_URL_REPLACEMENTS.get(mirror.url)
                if retired_replacement and mirror.mirror_type == ToolType.CONDA:
                    mirror.name, mirror.url = retired_replacement
                self._save_mirror(mirror)

    def _dedupe_mirrors(self):
        deduped = []
        seen = {}
        for mirror in list(self.mirrors):
            key = (mirror.mirror_type, self._normalized_url(mirror.url))
            existing = seen.get(key)
            if not existing:
                seen[key] = mirror
                deduped.append(mirror)
                continue

            changed = False
            if mirror.is_default and not existing.is_default:
                existing.is_default = True
                changed = True
            if mirror.is_active and not existing.is_active:
                existing.is_active = True
                changed = True
            if changed:
                self._save_mirror(existing)
            if self.db:
                self.db.delete_mirror(mirror.id)
        self.mirrors = deduped

    def _ensure_builtin_mirrors(self):
        self._repair_known_urls()
        self._dedupe_mirrors()

        for name, url, mirror_type, is_default in BUILTIN_MIRRORS:
            normalized_url = self._normalized_url(url)
            existing = next(
                (
                    mirror
                    for mirror in self.mirrors
                    if mirror.mirror_type == mirror_type
                    and self._normalized_url(mirror.url) == normalized_url
                ),
                None,
            )
            if existing:
                if existing.url != url:
                    existing.url = url
                    self._save_mirror(existing)
                if is_default and not self.get_default_mirror(mirror_type):
                    existing.is_default = True
                    existing.is_active = True
                    self._save_mirror(existing)
                continue

            mirror = Mirror(
                id=str(uuid.uuid4()),
                name=name,
                url=url,
                priority=0,
                is_active=True,
                mirror_type=mirror_type,
                is_default=is_default and not self.get_default_mirror(mirror_type),
            )
            self.mirrors.append(mirror)
            self._save_mirror(mirror)

    def _ensure_type_defaults(self):
        for mirror_type in (ToolType.VENV, ToolType.CONDA):
            type_mirrors = [m for m in self.mirrors if m.mirror_type == mirror_type]
            if not type_mirrors:
                continue

            defaults = [m for m in type_mirrors if m.is_default]
            if not defaults:
                selected = next((m for m in type_mirrors if m.is_active), type_mirrors[0])
                selected.is_default = True
                selected.is_active = True
                self._save_mirror(selected)
                defaults = [selected]

            keep_default = defaults[0]
            for mirror in defaults[1:]:
                mirror.is_default = False
                self._save_mirror(mirror)
            if not keep_default.is_active:
                keep_default.is_active = True
                self._save_mirror(keep_default)

    def add_mirror(self, name: str, url: str, mirror_type: ToolType) -> Mirror:
        mirror = Mirror(str(uuid.uuid4()), name, url, 0, False, mirror_type)
        self.mirrors.append(mirror)
        self._save_mirror(mirror)
        return mirror

    def list_mirrors(self, mirror_type: Optional[ToolType] = None) -> List[Mirror]:
        if mirror_type:
            return [m for m in self.mirrors if m.mirror_type == mirror_type]
        return self.mirrors

    def set_active_mirror(self, mirror_id: str) -> bool:
        target = next((m for m in self.mirrors if m.id == mirror_id), None)
        if not target:
            return False

        for mirror in self.mirrors:
            if mirror.mirror_type == target.mirror_type:
                mirror.is_active = mirror.id == mirror_id
                self._save_mirror(mirror)
        return True

    def get_active_mirror(self, mirror_type: ToolType) -> Optional[Mirror]:
        return next(
            (m for m in self.mirrors if m.mirror_type == mirror_type and m.is_active),
            None,
        )

    def toggle_mirror(self, mirror_id: str) -> bool:
        for mirror in self.mirrors:
            if mirror.id == mirror_id:
                mirror.is_active = not mirror.is_active
                if mirror.is_default:
                    mirror.is_active = True
                self._save_mirror(mirror)
                return mirror.is_active
        return False

    def set_default_mirror(self, mirror_id: str) -> bool:
        target = next((m for m in self.mirrors if m.id == mirror_id), None)
        if not target:
            return False

        for mirror in self.mirrors:
            if mirror.mirror_type == target.mirror_type:
                mirror.is_default = mirror.id == mirror_id
                if mirror.is_default:
                    mirror.is_active = True
                self._save_mirror(mirror)
        return True

    def get_default_mirror(self, mirror_type: Optional[ToolType] = None) -> Optional[Mirror]:
        for mirror in self.mirrors:
            if mirror.is_default and (mirror_type is None or mirror.mirror_type == mirror_type):
                return mirror
        return None

    def delete_mirror(self, mirror_id: str) -> bool:
        target = next((m for m in self.mirrors if m.id == mirror_id), None)
        self.mirrors = [m for m in self.mirrors if m.id != mirror_id]
        if self.db:
            self.db.delete_mirror(mirror_id)
        if target:
            self._ensure_type_defaults()
        return True

    def _probe_url(self, mirror: Mirror) -> str:
        base_url = self._normalized_url(mirror.url)
        if mirror.mirror_type == ToolType.CONDA:
            if base_url.endswith("/repodata.json"):
                return base_url
            return f"{base_url}/noarch/repodata.json"
        return f"{base_url}/pip/"

    def check_mirror(self, mirror: Mirror, timeout: int = 8) -> Tuple[bool, str]:
        probe_url = self._probe_url(mirror)
        request = Request(
            probe_url,
            headers={"User-Agent": "PyManager/1.0 mirror-check"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                response.read(512)
                status = response.getcode()
                if 200 <= status < 400:
                    return True, f"HTTP {status}: {probe_url}"
                return False, f"HTTP {status}: {probe_url}"
        except HTTPError as exc:
            return False, f"HTTP {exc.code}: {probe_url}"
        except URLError as exc:
            return False, f"{exc.reason}: {probe_url}"
        except Exception as exc:
            return False, f"{exc}: {probe_url}"
