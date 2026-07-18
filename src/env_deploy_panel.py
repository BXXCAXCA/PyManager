import os
import subprocess
import re
import shlex
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    QComboBox,
    QGroupBox,
    QProgressBar,
    QCheckBox,
    QFormLayout,
    QScrollArea,
    QFrame,
    QTabWidget,
    QTextEdit,
    QSizePolicy,
    QDialog,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal
from src.styles import COLORS, DARK_COLORS, get_dark_step_style, get_light_step_style, get_dark_log_style, get_light_log_style, get_dark_tab_style, get_light_tab_style, get_dark_delete_btn_style, get_light_delete_btn_style
from src.i18n import i18n
from src.worker import Worker
from src.command_executor import WSLCommandExecutor


def _run_wsl_command(args, timeout=10):
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(
        args, capture_output=True, timeout=timeout,
        creationflags=flags,
    )
    stdout = ""
    if result.stdout:
        for enc in ("utf-16-le", "utf-8", "gbk", "latin-1"):
            try:
                stdout = result.stdout.decode(enc).strip()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
    stderr = ""
    if result.stderr:
        for enc in ("utf-16-le", "utf-8", "gbk", "latin-1"):
            try:
                stderr = result.stderr.decode(enc).strip()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
    return result.returncode, stdout, stderr


@dataclass(frozen=True)
class DownloadSource:
    label_key: str
    base_url: str
    official: bool = False

    def label(self) -> str:
        return i18n.t(self.label_key)


OFFICIAL_CONDA_SOURCE = DownloadSource(
    "deploy_source_official",
    "https://repo.anaconda.com",
    official=True,
)
CONDA_DOWNLOAD_SOURCES = [
    DownloadSource("deploy_source_tuna", "https://mirrors.tuna.tsinghua.edu.cn/anaconda"),
    DownloadSource("deploy_source_ustc", "https://mirrors.ustc.edu.cn/anaconda"),
    DownloadSource("deploy_source_aliyun", "https://mirrors.aliyun.com/anaconda"),
    OFFICIAL_CONDA_SOURCE,
]

OFFICIAL_CUDA_SOURCE = DownloadSource(
    "deploy_source_official",
    "https://developer.download.nvidia.com/compute/cuda",
    official=True,
)
CUDA_DOWNLOAD_SOURCES = [
    DownloadSource("deploy_source_ustc", "https://mirrors.ustc.edu.cn/nvidia-cuda"),
    DownloadSource("deploy_source_tuna", "https://mirrors.tuna.tsinghua.edu.cn/nvidia-cuda"),
    DownloadSource("deploy_source_aliyun", "https://mirrors.aliyun.com/nvidia-cuda"),
    OFFICIAL_CUDA_SOURCE,
]

OFFICIAL_WSL_SOURCE = DownloadSource("deploy_source_official", "", official=True)
WSL_ROOTFS_SOURCES = [
    DownloadSource("deploy_source_tuna", "https://mirrors.tuna.tsinghua.edu.cn"),
    DownloadSource("deploy_source_ustc", "https://mirrors.ustc.edu.cn"),
    DownloadSource("deploy_source_aliyun", "https://mirrors.aliyun.com"),
    OFFICIAL_WSL_SOURCE,
]

FALLBACK_CUDA_VERSIONS = [
    "13.2.1",
    "13.2.0",
    "13.1.2",
    "13.1.1",
    "13.1.0",
    "13.0.3",
    "13.0.2",
    "13.0.1",
    "13.0.0",
    "12.9.2",
    "12.9.1",
    "12.9.0",
]

CUDA_MIN_VERSION = (12, 9, 0)
CUDA_ARCHIVE_URL = "https://developer.nvidia.com/cuda-toolkit-archive"
CUDA_DOWNLOAD_ROOT = "https://developer.download.nvidia.com/compute/cuda"


class InstallMirrorDialog(QDialog):
    def __init__(self, title_key: str, sources: list[DownloadSource], parent=None, theme="light"):
        super().__init__(parent)
        self.setWindowTitle(i18n.t(title_key))
        self.setMinimumWidth(420)
        self.selected_source = sources[0]

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        label = QLabel(i18n.t("deploy_install_source"))
        layout.addWidget(label)

        self.source_combo = QComboBox()
        for source in sources:
            suffix = "" if source.official else f" - {source.base_url}"
            self.source_combo.addItem(f"{source.label()}{suffix}", source)
        layout.addWidget(self.source_combo)

        hint = QLabel(i18n.t("deploy_source_fallback_hint"))
        hint.setWordWrap(True)
        hint_color = DARK_COLORS["text_secondary"] if theme == "dark" else COLORS["text_secondary"]
        hint.setStyleSheet(f"color: {hint_color}; font-size: 12px;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        self.selected_source = self.source_combo.currentData()
        super().accept()


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = [int(p) for p in re.findall(r"\d+", str(version))[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _parse_cuda_versions_from_archive(html: str) -> list[str]:
    versions = set()
    for match in re.finditer(r"cuda-(\d+)-(\d+)-(\d+)-download-archive", html):
        version = ".".join(match.groups())
        if _version_tuple(version) >= CUDA_MIN_VERSION:
            versions.add(version)
    return sorted(versions, key=_version_tuple, reverse=True)


def _cuda_archive_page_url(version: str) -> str:
    major, minor, patch = _version_tuple(version)
    return f"https://developer.nvidia.com/cuda-{major}-{minor}-{patch}-download-archive"


def _parse_cuda_installer_links(html: str, version: str, target: str) -> list[str]:
    urls = []
    pattern = r"https://developer\.download\.nvidia\.com/compute/cuda/[^\"'<>\\\s]+"
    for match in re.finditer(pattern, html):
        url = match.group(0)
        url = url.replace("\\u003c/span\\u003e\\u003cspan", "")
        url = url.replace("\\&quot;", "").replace("&quot;", "")
        url = urllib.parse.unquote(url).strip()
        if f"/{version}/" not in url or "/local_installers/" not in url:
            continue
        lower = url.lower()
        if target == "windows" and lower.endswith("_windows.exe"):
            urls.append(url)
        elif target == "wsl" and lower.endswith("_linux.run"):
            urls.append(url)
    return _unique_preserve_order(urls)


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _conda_installer_filename(conda_type: str, target: str) -> str:
    if conda_type == "Miniconda3":
        suffix = "Windows-x86_64.exe" if target == "windows" else "Linux-x86_64.sh"
        return f"Miniconda3-latest-{suffix}"
    suffix = "Windows-x86_64.exe" if target == "windows" else "Linux-x86_64.sh"
    return f"Anaconda3-2024.10-1-{suffix}"


def _build_conda_download_urls(conda_type: str, target: str, source: DownloadSource) -> list[str]:
    filename = _conda_installer_filename(conda_type, target)
    folder = "miniconda" if conda_type == "Miniconda3" else "archive"
    path = f"{folder}/{filename}"
    official_url = _join_url(OFFICIAL_CONDA_SOURCE.base_url, path)
    if source.official:
        return [official_url]
    return _unique_preserve_order([_join_url(source.base_url, path), official_url])


def _mirror_cuda_url(official_url: str, source: DownloadSource) -> str:
    if source.official or not official_url.startswith(CUDA_DOWNLOAD_ROOT):
        return official_url
    relative = official_url[len(CUDA_DOWNLOAD_ROOT):].lstrip("/")
    return _join_url(source.base_url, relative)


def _build_cuda_download_urls(official_urls: list[str], source: DownloadSource) -> list[str]:
    if source.official:
        return _unique_preserve_order(official_urls)
    urls = []
    for official_url in official_urls:
        urls.append(_mirror_cuda_url(official_url, source))
        urls.append(official_url)
    return _unique_preserve_order(urls)


def _ubuntu_rootfs_paths(official_name: str) -> list[str]:
    mapping = {
        "Ubuntu": ["24.04", "22.04"],
        "Ubuntu-24.04": ["24.04"],
        "Ubuntu-22.04": ["22.04"],
        "Ubuntu-20.04": ["20.04"],
    }
    versions = mapping.get(official_name, [])
    paths = []
    for version in versions:
        paths.append(
            f"ubuntu-cloud-images/wsl/releases/{version}/current/"
            f"ubuntu-{version}-server-cloudimg-amd64-wsl.rootfs.tar.gz"
        )
        paths.append(
            f"ubuntu-cloud-images/wsl/releases/{version}/release/"
            f"ubuntu-{version}-server-cloudimg-amd64-wsl.rootfs.tar.gz"
        )
    return paths


def _debian_rootfs_paths(official_name: str) -> list[str]:
    name = official_name.lower()
    if "bullseye" in name:
        return ["debian-cloud-images/generic/bullseye/latest/debian-11-generic-amd64.tar.xz"]
    return ["debian-cloud-images/generic/bookworm/latest/debian-12-generic-amd64.tar.xz"]


def _build_wsl_rootfs_urls(official_name: str, source: DownloadSource) -> list[str]:
    name = official_name.lower()
    if name.startswith("ubuntu"):
        paths = _ubuntu_rootfs_paths(official_name)
        official_base = "https://cloud-images.ubuntu.com"
    elif name.startswith("debian"):
        paths = _debian_rootfs_paths(official_name)
        official_base = "https://cloud.debian.org/images/cloud"
        paths = [p.replace("debian-cloud-images/", "", 1) for p in paths]
    else:
        return []

    urls = []
    for path in paths:
        if not source.official:
            if name.startswith("debian"):
                mirror_path = f"debian-cloud-images/{path}"
            else:
                mirror_path = path
            urls.append(_join_url(source.base_url, mirror_path))
        urls.append(_join_url(official_base, path))
    return _unique_preserve_order(urls)


def _url_filename(url: str, default_name: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = os.path.basename(parsed.path)
    return name or default_name


def _download_url_candidates(urls: list[str], destination: str, progress_signal=None, progress_span=50) -> tuple[bool, str]:
    last_error = ""
    for index, url in enumerate(urls):
        if progress_signal:
            progress_signal.emit(i18n.t("deploy_try_download_source").format(url))
        try:
            def report_hook(count, block_size, total_size):
                if progress_signal and total_size > 0:
                    pct = int(count * block_size / total_size * progress_span)
                    progress_signal.emit(f"PROGRESS:{min(max(pct, 0), progress_span)}")

            urllib.request.urlretrieve(url, destination, reporthook=report_hook)
            return True, url
        except Exception as exc:
            last_error = str(exc)
            if progress_signal:
                progress_signal.emit(f"[WARN] {i18n.t('deploy_source_failed')}: {last_error}")
    return False, last_error


def _send_windows_env_changed():
    if os.name != "nt":
        return
    try:
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0x0002, 5000, None
        )
    except Exception:
        pass


def _dedupe_windows_path(existing_path: str, paths_to_add: list[str]) -> str:
    parts = [p for p in (existing_path or "").split(";") if p]
    normalized = {os.path.normcase(os.path.normpath(p)) for p in parts}
    for path in paths_to_add:
        if not path:
            continue
        norm = os.path.normcase(os.path.normpath(path))
        if norm not in normalized:
            parts.append(path)
            normalized.add(norm)
    return ";".join(parts)


def _set_windows_user_env(env_vars: dict[str, str], paths_to_add: list[str] | None = None):
    import winreg

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        )
    except FileNotFoundError:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment")

    try:
        for name, value in env_vars.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)
            os.environ[name] = value

        if paths_to_add:
            try:
                existing_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                existing_path = ""
            new_path = _dedupe_windows_path(existing_path, paths_to_add)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            os.environ["PATH"] = _dedupe_windows_path(os.environ.get("PATH", ""), paths_to_add)
    finally:
        winreg.CloseKey(key)
    _send_windows_env_changed()


def _read_windows_user_env(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, name)
            return value
        finally:
            winreg.CloseKey(key)
    except Exception:
        return ""


def _detect_windows_conda_root() -> str:
    candidates = [
        os.environ.get("CONDA_ROOT"),
        _read_windows_user_env("CONDA_ROOT"),
        os.environ.get("CONDA_PREFIX"),
    ]
    conda_exe = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if conda_exe:
        candidates.append(os.path.dirname(os.path.dirname(conda_exe)))

    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.extend([
            os.path.join(user_profile, "miniconda3"),
            os.path.join(user_profile, "anaconda3"),
        ])
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        candidates.extend([
            os.path.join(localappdata, "miniconda3"),
            os.path.join(localappdata, "anaconda3"),
        ])

    for candidate in candidates:
        if not candidate:
            continue
        conda_path = os.path.join(candidate, "Scripts", "conda.exe")
        if os.path.exists(conda_path):
            return os.path.normpath(candidate)
    return ""


def _detect_windows_cuda_path() -> str:
    candidates = [
        os.environ.get("CUDA_PATH"),
        _read_windows_user_env("CUDA_PATH"),
    ]
    toolkit_root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "NVIDIA GPU Computing Toolkit" / "CUDA"
    if toolkit_root.exists():
        candidates.extend(str(path) for path in sorted(toolkit_root.glob("v*"), reverse=True))

    for candidate in candidates:
        if not candidate:
            continue
        nvcc = os.path.join(candidate, "bin", "nvcc.exe")
        if os.path.exists(nvcc):
            return os.path.normpath(candidate)
    return ""


def _cuda_windows_install_path(version: str) -> str:
    major, minor, _ = _version_tuple(version)
    return os.path.join(
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        "NVIDIA GPU Computing Toolkit",
        "CUDA",
        f"v{major}.{minor}",
    )


def _wsl_quote(value: str) -> str:
    return shlex.quote(str(value))


def _normalize_wsl_install_path(path: str, default_path: str) -> str:
    path = (path or default_path).strip()
    return path.rstrip("/") or default_path


def _default_wsl_import_root(distro_name: str) -> str:
    safe_name = (distro_name or "Ubuntu").strip() or "Ubuntu"
    return os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "PyManager",
        "WSL",
        safe_name,
    )


def _resolve_wsl_import_root(distro_name: str, install_path: str) -> str:
    path = (install_path or "").strip()
    if not path:
        return _default_wsl_import_root(distro_name)
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))


def get_deploy_panel_container_style(theme: str) -> str:
    colors = DARK_COLORS if theme == "dark" else COLORS
    return (
        f"QWidget#envDeployPanel {{ background-color: {colors['background']}; color: {colors['text_primary']}; }}"
        f"QScrollArea#deployScrollArea {{ background-color: {colors['background']}; border: none; }}"
        f"QScrollArea#deployScrollArea > QWidget > QWidget {{ background-color: {colors['background']}; }}"
        f"QWidget#deployPage {{ background-color: {colors['background']}; color: {colors['text_primary']}; }}"
    )


class StepIndicator(QWidget):
    step_changed = Signal(int)

    def __init__(self, steps: list, parent=None, theme="light"):
        super().__init__(parent)
        self.steps = steps
        self.current_step = 0
        self.theme = theme
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.labels = []
        for i, step_text in enumerate(steps):
            lbl = QLabel(f"{i + 1}. {step_text}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setMinimumHeight(28)
            self.labels.append(lbl)
            layout.addWidget(lbl)
        self._update_style()

    def set_step(self, index: int):
        self.current_step = index
        self._update_style()
        self.step_changed.emit(index)

    def set_theme(self, theme: str):
        self.theme = theme
        self._update_style()

    def _update_style(self):
        styles = get_dark_step_style() if self.theme == "dark" else get_light_step_style()
        for i, lbl in enumerate(self.labels):
            if i < self.current_step:
                lbl.setStyleSheet(styles["completed"])
            elif i == self.current_step:
                lbl.setStyleSheet(styles["current"])
            else:
                lbl.setStyleSheet(styles["pending"])


class LogOutput(QTextEdit):
    def __init__(self, parent=None, theme="light"):
        super().__init__(parent)
        self.theme = theme
        self.setReadOnly(True)
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(get_light_log_style() if theme == "light" else get_dark_log_style())

    def set_theme(self, theme: str):
        self.theme = theme
        self.setStyleSheet(get_light_log_style() if theme == "light" else get_dark_log_style())

    def append_log(self, message: str, level: str = "info"):
        color_map = {
            "info": "#e0e0e0",
            "success": "#10B981",
            "warning": "#F59E0B",
            "error": "#EF4444",
            "step": "#3B82F6",
        }
        color = color_map.get(level, "#e0e0e0")
        self.append(f'<span style="color:{color}">{message}</span>')
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def clear_logs(self):
        self.clear()


class CondaInstaller(QWidget):
    install_started = Signal()
    install_finished = Signal(bool, str)

    def __init__(self, parent=None, wsl_config=None, theme="light"):
        super().__init__(parent)
        self.wsl_config = wsl_config or {}
        self.theme = theme
        self._worker = None
        self._version_worker = None
        self.setObjectName("deployPage")
        self._setup_ui()

    def set_theme(self, theme: str):
        self.theme = theme
        self.step_indicator.set_theme(theme)
        self.log_output.set_theme(theme)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)



        target_group = QGroupBox(i18n.t("deploy_target"))
        target_layout = QFormLayout(target_group)
        target_layout.setSpacing(10)

        self.target_combo = QComboBox()
        self.target_combo.addItems(["Windows (本地)", "WSL (Linux)"])
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        target_layout.addRow(i18n.t("deploy_install_target"), self.target_combo)

        self.wsl_distro_combo = QComboBox()
        self.wsl_distro_combo.setEnabled(False)
        self.wsl_distro_combo.currentIndexChanged.connect(self._load_wsl_users)
        target_layout.addRow(i18n.t("deploy_wsl_distro"), self.wsl_distro_combo)

        self.wsl_user_combo = QComboBox()
        self.wsl_user_combo.setEnabled(False)
        target_layout.addRow(i18n.t("deploy_wsl_user"), self.wsl_user_combo)

        self.wsl_password_edit = QLineEdit()
        self.wsl_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.wsl_password_edit.setEnabled(False)
        self.wsl_password_edit.setPlaceholderText(i18n.t("deploy_wsl_password_ph"))
        target_layout.addRow(i18n.t("deploy_wsl_password"), self.wsl_password_edit)

        layout.addWidget(target_group)

        conda_group = QGroupBox(i18n.t("deploy_conda_config"))
        conda_layout = QFormLayout(conda_group)
        conda_layout.setSpacing(10)

        self.conda_type_combo = QComboBox()
        self.conda_type_combo.addItems(["Miniconda3", "Anaconda3"])
        conda_layout.addRow(i18n.t("deploy_conda_type"), self.conda_type_combo)

        self.install_path_edit = QLineEdit()
        self.install_path_edit.setPlaceholderText(i18n.t("deploy_conda_path_placeholder"))
        self._update_default_path()
        conda_layout.addRow(i18n.t("deploy_install_path"), self.install_path_edit)

        self.auto_envvar_check = QCheckBox(i18n.t("deploy_auto_envvar"))
        self.auto_envvar_check.setChecked(True)
        conda_layout.addRow(self.auto_envvar_check)

        self.init_conda_check = QCheckBox(i18n.t("deploy_init_conda"))
        self.init_conda_check.setChecked(True)
        conda_layout.addRow(self.init_conda_check)

        layout.addWidget(conda_group)

        step_labels = [
            i18n.t("deploy_step_download"),
            i18n.t("deploy_step_install"),
            i18n.t("deploy_step_envvar"),
            i18n.t("deploy_step_init"),
        ]
        self.step_indicator = StepIndicator(step_labels, theme=self.theme)
        layout.addWidget(self.step_indicator)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_output = LogOutput(theme=self.theme)
        layout.addWidget(self.log_output, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.check_btn = QPushButton(i18n.t("deploy_check_conda"))
        self.check_btn.clicked.connect(self._check_conda)

        self.install_btn = QPushButton(i18n.t("deploy_install_conda"))
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self._start_install)

        btn_layout.addWidget(self.check_btn)
        btn_layout.addWidget(self.install_btn)
        layout.addLayout(btn_layout)

        self._load_wsl_distros()

    def _on_target_changed(self, index):
        is_wsl = index == 1
        self.wsl_distro_combo.setEnabled(is_wsl)
        self.wsl_user_combo.setEnabled(is_wsl)
        self.wsl_password_edit.setEnabled(is_wsl)
        if not is_wsl:
            self.wsl_distro_combo.setCurrentIndex(-1)
            self.wsl_user_combo.setCurrentIndex(-1)
            self.wsl_password_edit.clear()
        self._update_default_path()

    def _update_default_path(self):
        is_wsl = self.target_combo.currentIndex() == 1
        if is_wsl:
            self.install_path_edit.setPlaceholderText("~/miniconda3")
        else:
            username = os.getenv("USERNAME") or os.getenv("USER") or "user"
            self.install_path_edit.setPlaceholderText(
                f"C:/Users/{username}/miniconda3"
            )

    def _load_wsl_distros(self):
        self.wsl_distro_combo.clear()
        try:
            rc, stdout, stderr = _run_wsl_command(["wsl", "-l", "-q"])
            if rc == 0 and stdout:
                distros = [d.strip() for d in stdout.split("\n") if d.strip()]
                self.wsl_distro_combo.addItems(distros)
            else:
                self.wsl_distro_combo.addItem("Ubuntu")
        except Exception:
            self.wsl_distro_combo.addItem("Ubuntu")
        if self.target_combo.currentIndex() != 1:
            self.wsl_distro_combo.setCurrentIndex(-1)
        self._load_wsl_users()

    def _load_wsl_users(self):
        self.wsl_user_combo.clear()
        if self.target_combo.currentIndex() != 1:
            self.wsl_user_combo.setCurrentIndex(-1)
            return
        distro = self.wsl_distro_combo.currentText() or None
        executor = WSLCommandExecutor(distro=distro)
        users = ["root"]
        try:
            cmd = (
                "awk -F: '($3 >= 1000 && $7 !~ /(false|nologin)$/) "
                "{print $1}' /etc/passwd"
            )
            rc, out, err = executor.execute(cmd, timeout=10)
            if rc == 0 and out.strip():
                for user in out.splitlines():
                    user = user.strip()
                    if user and user not in users:
                        users.append(user)
        except Exception:
            pass
        self.wsl_user_combo.addItems(users)
        preferred = self.wsl_config.get("username")
        if preferred:
            idx = self.wsl_user_combo.findText(preferred)
            if idx >= 0:
                self.wsl_user_combo.setCurrentIndex(idx)

    def _check_conda(self):
        is_wsl = self.target_combo.currentIndex() == 1
        self.log_output.clear_logs()
        self.log_output.append_log(i18n.t("deploy_checking_conda"), "step")

        if is_wsl:
            distro = self.wsl_distro_combo.currentText() or None
            user = self.wsl_user_combo.currentText().strip() or None
            executor = WSLCommandExecutor(distro=distro, user=user)
            try:
                rc, out, err = executor.execute("which conda && conda --version", timeout=15)
                if rc == 0 and out.strip():
                    self.log_output.append_log(
                        i18n.t("deploy_conda_found_wsl").format(out.strip()), "success"
                    )
                else:
                    self.log_output.append_log(i18n.t("deploy_conda_not_found_wsl"), "warning")
            except Exception as e:
                self.log_output.append_log(f"Error: {e}", "error")
        else:
            try:
                result = subprocess.run(
                    ["conda", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    self.log_output.append_log(
                        i18n.t("deploy_conda_found_local").format(result.stdout.strip()),
                        "success",
                    )
                else:
                    self.log_output.append_log(i18n.t("deploy_conda_not_found_local"), "warning")
            except FileNotFoundError:
                self.log_output.append_log(i18n.t("deploy_conda_not_found_local"), "warning")
            except Exception as e:
                self.log_output.append_log(f"Error: {e}", "error")

    def _start_install(self):
        is_wsl = self.target_combo.currentIndex() == 1
        conda_type = self.conda_type_combo.currentText()
        install_path = self.install_path_edit.text().strip()
        auto_envvar = self.auto_envvar_check.isChecked()
        init_conda = self.init_conda_check.isChecked()
        distro = self.wsl_distro_combo.currentText() if is_wsl else None
        wsl_user = self.wsl_user_combo.currentText().strip() if is_wsl else None
        wsl_password = self.wsl_password_edit.text() if is_wsl else None

        mirror_dialog = InstallMirrorDialog(
            "deploy_conda_source_title", CONDA_DOWNLOAD_SOURCES, self, self.theme
        )
        if mirror_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = mirror_dialog.selected_source

        self.install_btn.setEnabled(False)
        self.check_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_output.clear_logs()
        self.install_started.emit()

        if is_wsl:
            func = self._install_conda_wsl
            args = (
                conda_type,
                install_path or "~/miniconda3",
                auto_envvar,
                init_conda,
                distro,
                wsl_user,
                wsl_password,
                source,
            )
        else:
            func = self._install_conda_local
            args = (conda_type, install_path, auto_envvar, init_conda, source)

        self._worker = Worker(func, *args)
        self._worker.progress.connect(self._on_progress)
        self._worker.result.connect(self._on_install_result)
        self._worker.error.connect(self._on_install_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        if msg.startswith("STEP:"):
            step = int(msg.split(":")[1])
            self.step_indicator.set_step(step)
            pct = min(step * 25, 100)
            self.progress_bar.setValue(pct)
        elif msg.startswith("PROGRESS:"):
            pct = int(msg.split(":")[1])
            self.progress_bar.setValue(pct)
        else:
            level = "info"
            if msg.startswith("[OK]"):
                level = "success"
            elif msg.startswith("[WARN]"):
                level = "warning"
            elif msg.startswith("[ERR]"):
                level = "error"
            self.log_output.append_log(msg, level)

    def _on_install_result(self, result):
        self.install_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        success, message = result
        if success:
            self.progress_bar.setValue(100)
            self.step_indicator.set_step(4)
            self.log_output.append_log(message, "success")
        else:
            self.log_output.append_log(message, "error")
        self.install_finished.emit(success, message)

    def _on_install_error(self, error_msg: str):
        self.install_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        self.log_output.append_log(f"[ERR] {error_msg}", "error")
        self.install_finished.emit(False, error_msg)

    def _install_conda_local(
        self,
        conda_type: str,
        install_path: str,
        auto_envvar: bool,
        init_conda: bool,
        source: DownloadSource,
    ):
        progress = self._worker.progress

        if not install_path:
            username = os.getenv("USERNAME") or os.getenv("USER") or "user"
            install_path = f"C:/Users/{username}/miniconda3"

        urls = _build_conda_download_urls(conda_type, "windows", source)
        filename = _conda_installer_filename(conda_type, "windows")

        progress.emit("STEP:0")
        progress.emit(i18n.t("deploy_downloading").format(conda_type))

        tmp_dir = tempfile.gettempdir()
        installer_path = os.path.join(tmp_dir, filename)

        ok, info = _download_url_candidates(urls, installer_path, progress, progress_span=50)
        if not ok:
            progress.emit(f"[ERR] {i18n.t('deploy_download_failed')}: {info}")
            return False, info
        progress.emit(f"[OK] {i18n.t('deploy_download_complete')}: {info}")

        progress.emit("STEP:1")
        progress.emit(i18n.t("deploy_installing").format(install_path))

        try:
            cmd = [
                installer_path,
                "/S",
                "/InstallationType=JustMe",
                "/AddToPath=0",
                "/RegisterPython=0",
                f"/D={install_path}",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                progress.emit(f"[ERR] {i18n.t('deploy_install_failed')}: {result.stderr}")
                return False, result.stderr
            progress.emit(f"[OK] {i18n.t('deploy_install_complete')}")
        except Exception as e:
            progress.emit(f"[ERR] {i18n.t('deploy_install_failed')}: {e}")
            return False, str(e)

        progress.emit("STEP:2")
        if auto_envvar:
            progress.emit(i18n.t("deploy_configuring_envvar"))
            try:
                import winreg

                conda_path = install_path
                scripts_path = os.path.join(install_path, "Scripts")
                condabin_path = os.path.join(install_path, "condabin")

                try:
                    key = winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        "Environment",
                        0,
                        winreg.KEY_READ | winreg.KEY_WRITE,
                    )
                except FileNotFoundError:
                    key = winreg.CreateKey(
                        winreg.HKEY_CURRENT_USER, "Environment"
                    )

                try:
                    existing_path, _ = winreg.QueryValueEx(key, "Path")
                except FileNotFoundError:
                    existing_path = ""

                paths_to_add = [conda_path, scripts_path, condabin_path]
                existing_parts = existing_path.split(";") if existing_path else []
                new_parts = [p for p in paths_to_add if p not in existing_parts]
                if new_parts:
                    new_path = ";".join(existing_parts + new_parts)
                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                    progress.emit(f"[OK] {i18n.t('deploy_envvar_added')}")
                else:
                    progress.emit(f"[WARN] {i18n.t('deploy_envvar_exists')}")

                winreg.CloseKey(key)

                _send_windows_env_changed()

                _set_windows_user_env(
                    {
                        "CONDA_ROOT": install_path,
                        "CONDA_EXE": os.path.join(install_path, "Scripts", "conda.exe"),
                    },
                    [conda_path, scripts_path, condabin_path],
                )
                progress.emit(f"[OK] CONDA_ROOT = {install_path}")
            except Exception as e:
                progress.emit(f"[ERR] {i18n.t('deploy_envvar_failed')}: {e}")
        else:
            progress.emit(f"[WARN] {i18n.t('deploy_envvar_skipped')}")

        progress.emit("STEP:3")
        if init_conda:
            progress.emit(i18n.t("deploy_running_conda_init"))
            try:
                conda_exe = os.path.join(install_path, "Scripts", "conda.exe")
                if os.path.exists(conda_exe):
                    result = subprocess.run(
                        [conda_exe, "init", "cmd.exe", "powershell"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if result.returncode == 0:
                        progress.emit(f"[OK] {i18n.t('deploy_conda_init_done')}")
                    else:
                        progress.emit(f"[WARN] conda init: {result.stderr}")
                else:
                    progress.emit(f"[WARN] conda.exe not found at {conda_exe}")
            except Exception as e:
                progress.emit(f"[WARN] conda init failed: {e}")
        else:
            progress.emit(f"[WARN] {i18n.t('deploy_conda_init_skipped')}")

        try:
            os.remove(installer_path)
        except Exception:
            pass

        return True, i18n.t("deploy_conda_install_success").format(install_path)

    def _install_conda_wsl(
        self,
        conda_type: str,
        install_path: str,
        auto_envvar: bool,
        init_conda: bool,
        distro: str,
        user: str,
        password: str,
        source: DownloadSource,
    ):
        progress = self._worker.progress
        executor = WSLCommandExecutor(
            distro=distro if distro else None,
            user=user if user else None,
            password=password if password else None,
        )
        install_path = _normalize_wsl_install_path(install_path, "~/miniconda3")

        urls = _build_conda_download_urls(conda_type, "wsl", source)
        filename = _conda_installer_filename(conda_type, "wsl")

        progress.emit("STEP:0")
        progress.emit(i18n.t("deploy_downloading_wsl").format(conda_type))

        try:
            rc, out, err = executor.execute("which wget curl", timeout=10)
            if rc != 0:
                progress.emit(i18n.t("deploy_installing_wget"))
                executor.execute_sudo("apt-get update && apt-get install -y wget curl", timeout=120)

            commands = []
            for url in urls:
                quoted_url = _wsl_quote(url)
                output_path = _wsl_quote(f"/tmp/{filename}")
                commands.append(
                    f"(wget -q --show-progress -O {output_path} {quoted_url} 2>&1 "
                    f"|| curl -fL -o {output_path} {quoted_url} 2>&1)"
                )
            download_cmd = " || ".join(commands)
            rc, out, err = executor.execute(download_cmd, timeout=600)
            if rc != 0:
                progress.emit(f"[ERR] {i18n.t('deploy_download_failed')}: {err or out}")
                return False, err or out
            progress.emit(f"[OK] {i18n.t('deploy_download_complete')}")
        except Exception as e:
            progress.emit(f"[ERR] {i18n.t('deploy_download_failed')}: {e}")
            return False, str(e)

        progress.emit("STEP:1")
        progress.emit(i18n.t("deploy_installing").format(install_path))

        try:
            install_cmd = f"bash {_wsl_quote('/tmp/' + filename)} -b -p {_wsl_quote(install_path)}"
            rc, out, err = executor.execute(install_cmd, timeout=600)
            if rc != 0:
                progress.emit(f"[ERR] {i18n.t('deploy_install_failed')}: {err}")
                return False, err
            progress.emit(f"[OK] {i18n.t('deploy_install_complete')}")
        except Exception as e:
            progress.emit(f"[ERR] {i18n.t('deploy_install_failed')}: {e}")
            return False, str(e)

        progress.emit("STEP:2")
        if auto_envvar:
            progress.emit(i18n.t("deploy_configuring_envvar_wsl"))
            try:
                conda_bin = f"{install_path}/bin"
                bashrc_line = f'export PATH="{conda_bin}:$PATH"'
                conda_root_line = f'export CONDA_ROOT="{install_path}"'

                check_cmd = 'grep -q "CONDA_ROOT" ~/.bashrc 2>/dev/null && echo "exists" || echo "not_found"'
                rc, out, err = executor.execute(check_cmd, timeout=10)

                if "not_found" in out:
                    append_cmd = (
                        f'echo \'\' >> ~/.bashrc && '
                        f'echo \'# >>> conda initialize >>>\' >> ~/.bashrc && '
                        f'echo \'{conda_root_line}\' >> ~/.bashrc && '
                        f'echo \'{bashrc_line}\' >> ~/.bashrc && '
                        f'echo \'# <<< conda initialize <<<\' >> ~/.bashrc'
                    )
                    executor.execute(append_cmd, timeout=10)
                    progress.emit(f"[OK] {i18n.t('deploy_envvar_added_wsl')}")
                else:
                    progress.emit(f"[WARN] {i18n.t('deploy_envvar_exists')}")
            except Exception as e:
                progress.emit(f"[ERR] {i18n.t('deploy_envvar_failed')}: {e}")
        else:
            progress.emit(f"[WARN] {i18n.t('deploy_envvar_skipped')}")

        progress.emit("STEP:3")
        if init_conda:
            progress.emit(i18n.t("deploy_running_conda_init_wsl"))
            try:
                init_cmd = f"{_wsl_quote(install_path + '/bin/conda')} init bash"
                rc, out, err = executor.execute(init_cmd, timeout=30)
                if rc == 0:
                    progress.emit(f"[OK] {i18n.t('deploy_conda_init_done')}")
                else:
                    progress.emit(f"[WARN] conda init: {err}")
            except Exception as e:
                progress.emit(f"[WARN] conda init failed: {e}")
        else:
            progress.emit(f"[WARN] {i18n.t('deploy_conda_init_skipped')}")

        try:
            executor.execute(f"rm -f /tmp/{filename}", timeout=10)
        except Exception:
            pass

        return True, i18n.t("deploy_conda_install_success_wsl").format(install_path)

    def update_wsl_config(self, config: dict):
        self.wsl_config = config
        if config.get("distro") and self.target_combo.currentIndex() == 1:
            idx = self.wsl_distro_combo.findText(config["distro"])
            if idx >= 0:
                self.wsl_distro_combo.setCurrentIndex(idx)
        if config.get("username"):
            idx = self.wsl_user_combo.findText(config["username"])
            if idx >= 0:
                self.wsl_user_combo.setCurrentIndex(idx)
        if config.get("password"):
            self.wsl_password_edit.setText(config["password"])


class EnvVarConfig(QWidget):
    config_finished = Signal(bool, str)

    def __init__(self, parent=None, wsl_config=None, theme="light"):
        super().__init__(parent)
        self.wsl_config = wsl_config or {}
        self.theme = theme
        self._worker = None
        self.setObjectName("deployPage")
        self._setup_ui()

    def set_theme(self, theme: str):
        self.theme = theme
        self.log_output.set_theme(theme)
        self._refresh_delete_btn_styles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)



        target_group = QGroupBox(i18n.t("deploy_target"))
        target_layout = QFormLayout(target_group)
        target_layout.setSpacing(10)

        self.target_combo = QComboBox()
        self.target_combo.addItems(["Windows (本地)", "WSL (Linux)"])
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        target_layout.addRow(i18n.t("deploy_envvar_target"), self.target_combo)

        self.wsl_distro_combo = QComboBox()
        self.wsl_distro_combo.setEnabled(False)
        self.wsl_distro_combo.currentIndexChanged.connect(self._load_wsl_users)
        target_layout.addRow(i18n.t("deploy_wsl_distro"), self.wsl_distro_combo)

        self.wsl_user_combo = QComboBox()
        self.wsl_user_combo.setEnabled(False)
        target_layout.addRow(i18n.t("deploy_wsl_user"), self.wsl_user_combo)

        layout.addWidget(target_group)

        vars_group = QGroupBox(i18n.t("deploy_envvar_vars"))
        vars_layout = QVBoxLayout(vars_group)
        vars_layout.setSpacing(8)

        self.env_vars_layout = QGridLayout()
        self.env_vars_layout.setSpacing(6)
        self.env_vars_layout.addWidget(QLabel(i18n.t("deploy_envvar_name")), 0, 0)
        self.env_vars_layout.addWidget(QLabel(i18n.t("deploy_envvar_value")), 0, 1)
        self.env_vars_layout.addWidget(QLabel(""), 0, 2)
        vars_layout.addLayout(self.env_vars_layout)

        add_row_btn = QPushButton(i18n.t("deploy_envvar_add_row"))
        add_row_btn.clicked.connect(self._add_env_row)
        vars_layout.addWidget(add_row_btn)

        layout.addWidget(vars_group)

        preset_group = QGroupBox(i18n.t("deploy_envvar_presets"))
        preset_layout = QVBoxLayout(preset_group)

        self.preset_conda_check = QCheckBox(i18n.t("deploy_envvar_preset_conda"))
        self.preset_conda_check.setChecked(True)
        preset_layout.addWidget(self.preset_conda_check)

        self.preset_cuda_check = QCheckBox(i18n.t("deploy_envvar_preset_cuda"))
        preset_layout.addWidget(self.preset_cuda_check)

        self.preset_path_check = QCheckBox(i18n.t("deploy_envvar_preset_path"))
        self.preset_path_check.setChecked(True)
        preset_layout.addWidget(self.preset_path_check)

        layout.addWidget(preset_group)

        self.log_output = LogOutput(theme=self.theme)
        layout.addWidget(self.log_output, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.detect_btn = QPushButton(i18n.t("deploy_envvar_detect"))
        self.detect_btn.clicked.connect(self._detect_env)

        self.apply_btn = QPushButton(i18n.t("deploy_envvar_apply"))
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self._apply_env)

        btn_layout.addWidget(self.detect_btn)
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)

        self._add_env_row("CONDA_ROOT", "")
        self._add_env_row("CUDA_PATH", "")
        self._load_wsl_distros()

    def _on_target_changed(self, index):
        is_wsl = index == 1
        self.wsl_distro_combo.setEnabled(is_wsl)
        self.wsl_user_combo.setEnabled(is_wsl)
        if not is_wsl:
            self.wsl_distro_combo.setCurrentIndex(-1)
            self.wsl_user_combo.setCurrentIndex(-1)

    def _load_wsl_distros(self):
        self.wsl_distro_combo.clear()
        try:
            rc, stdout, stderr = _run_wsl_command(["wsl", "-l", "-q"])
            if rc == 0 and stdout:
                distros = [d.strip() for d in stdout.split("\n") if d.strip()]
                self.wsl_distro_combo.addItems(distros)
            else:
                self.wsl_distro_combo.addItem("Ubuntu")
        except Exception:
            self.wsl_distro_combo.addItem("Ubuntu")
        if self.target_combo.currentIndex() != 1:
            self.wsl_distro_combo.setCurrentIndex(-1)
        self._load_wsl_users()

    def _load_wsl_users(self):
        self.wsl_user_combo.clear()
        if self.target_combo.currentIndex() != 1:
            self.wsl_user_combo.setCurrentIndex(-1)
            return
        distro = self.wsl_distro_combo.currentText() or None
        executor = WSLCommandExecutor(distro=distro)
        users = ["root"]
        try:
            rc, out, err = executor.execute(
                "awk -F: '($3 >= 1000 && $7 !~ /(false|nologin)$/) {print $1}' /etc/passwd",
                timeout=10,
            )
            if rc == 0 and out.strip():
                for user in out.splitlines():
                    user = user.strip()
                    if user and user not in users:
                        users.append(user)
        except Exception:
            pass
        self.wsl_user_combo.addItems(users)
        preferred = self.wsl_config.get("username")
        if preferred:
            idx = self.wsl_user_combo.findText(preferred)
            if idx >= 0:
                self.wsl_user_combo.setCurrentIndex(idx)

    def _add_env_row(self, name: str = "", value: str = ""):
        row = self.env_vars_layout.rowCount()
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText(i18n.t("deploy_envvar_name_ph"))
        value_edit = QLineEdit(value)
        value_edit.setPlaceholderText(i18n.t("deploy_envvar_value_ph"))
        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(28)
        del_btn.setStyleSheet(get_dark_delete_btn_style() if self.theme == "dark" else get_light_delete_btn_style())
        del_btn.clicked.connect(lambda: self._remove_env_row(row))
        self.env_vars_layout.addWidget(name_edit, row, 0)
        self.env_vars_layout.addWidget(value_edit, row, 1)
        self.env_vars_layout.addWidget(del_btn, row, 2)

    def _remove_env_row(self, row: int):
        for col in range(3):
            item = self.env_vars_layout.itemAtPosition(row, col)
            if item and item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()

    def _set_env_row_value(self, name: str, value: str):
        if not value:
            return
        for row in range(1, self.env_vars_layout.rowCount()):
            name_item = self.env_vars_layout.itemAtPosition(row, 0)
            value_item = self.env_vars_layout.itemAtPosition(row, 1)
            if name_item and value_item and name_item.widget().text().strip() == name:
                value_item.widget().setText(value)
                return
        self._add_env_row(name, value)

    def _detect_wsl_conda_root(self, executor: WSLCommandExecutor) -> str:
        commands = [
            "which conda 2>/dev/null && dirname $(dirname $(which conda))",
            "grep -E '^export CONDA_ROOT=' ~/.bashrc ~/.profile 2>/dev/null | tail -1 | sed -E 's/^export CONDA_ROOT=\"?([^\" ]+)\"?.*/\\1/'",
            "for d in \"$HOME/miniconda3\" \"$HOME/anaconda3\" /opt/conda /opt/miniconda3 /opt/anaconda3; do [ -x \"$d/bin/conda\" ] && echo \"$d\" && break; done",
        ]
        for command in commands:
            rc, out, err = executor.execute(command, timeout=15)
            if rc == 0 and out.strip():
                return out.strip().splitlines()[-1]
        return ""

    def _detect_wsl_cuda_path(self, executor: WSLCommandExecutor) -> str:
        commands = [
            "which nvcc 2>/dev/null && dirname $(dirname $(which nvcc))",
            "grep -E '^export CUDA_PATH=' ~/.bashrc ~/.profile 2>/dev/null | tail -1 | sed -E 's/^export CUDA_PATH=\"?([^\" ]+)\"?.*/\\1/'",
            "ls -d /usr/local/cuda-* /usr/local/cuda 2>/dev/null | sort -Vr | head -1",
        ]
        for command in commands:
            rc, out, err = executor.execute(command, timeout=15)
            if rc == 0 and out.strip():
                return out.strip().splitlines()[-1]
        return ""

    def _detect_env(self):
        is_wsl = self.target_combo.currentIndex() == 1
        self.log_output.clear_logs()
        self.log_output.append_log(i18n.t("deploy_envvar_detecting"), "step")

        if is_wsl:
            distro = self.wsl_distro_combo.currentText() or None
            user = self.wsl_user_combo.currentText().strip() or None
            executor = WSLCommandExecutor(distro=distro, user=user)
            try:
                conda_root = self._detect_wsl_conda_root(executor)
                cuda_path = self._detect_wsl_cuda_path(executor)
                if conda_root:
                    self._set_env_row_value("CONDA_ROOT", conda_root)
                    self.log_output.append_log(f"CONDA_ROOT = {conda_root}", "success")
                else:
                    self.log_output.append_log(i18n.t("deploy_conda_not_found_wsl"), "warning")
                if cuda_path:
                    self._set_env_row_value("CUDA_PATH", cuda_path)
                    self.log_output.append_log(f"CUDA_PATH = {cuda_path}", "success")
                else:
                    self.log_output.append_log(i18n.t("deploy_cuda_not_found_wsl"), "warning")
            except Exception as e:
                self.log_output.append_log(f"Error: {e}", "error")
        else:
            conda_root = _detect_windows_conda_root()
            cuda_path = _detect_windows_cuda_path()
            if conda_root:
                self._set_env_row_value("CONDA_ROOT", conda_root)
                self.log_output.append_log(f"CONDA_ROOT = {conda_root}", "success")
            else:
                self.log_output.append_log(i18n.t("deploy_conda_not_found_local"), "warning")
            if cuda_path:
                self._set_env_row_value("CUDA_PATH", cuda_path)
                self.log_output.append_log(f"CUDA_PATH = {cuda_path}", "success")
            else:
                self.log_output.append_log(i18n.t("deploy_cuda_not_found_local"), "warning")

    def _apply_env(self):
        is_wsl = self.target_combo.currentIndex() == 1
        self.log_output.clear_logs()

        env_vars = {}
        for row in range(1, self.env_vars_layout.rowCount()):
            name_item = self.env_vars_layout.itemAtPosition(row, 0)
            value_item = self.env_vars_layout.itemAtPosition(row, 1)
            if name_item and value_item:
                name = name_item.widget().text().strip()
                value = value_item.widget().text().strip()
                if name and value:
                    env_vars[name] = value

        if is_wsl:
            distro = self.wsl_distro_combo.currentText() or None
            user = self.wsl_user_combo.currentText().strip() or None
            executor = WSLCommandExecutor(distro=distro, user=user)
            try:
                for name, value in env_vars.items():
                    line = f'export {name}="{value}"'
                    check_cmd = f'grep -q "^export {name}=" ~/.bashrc 2>/dev/null && echo "exists" || echo "not_found"'
                    rc, out, err = executor.execute(check_cmd, timeout=10)
                    if "exists" in out:
                        sed_cmd = f"sed -i 's|^export {name}=.*|{line}|' ~/.bashrc"
                        executor.execute(sed_cmd, timeout=10)
                    else:
                        append_cmd = f'echo \'{line}\' >> ~/.bashrc'
                        executor.execute(append_cmd, timeout=10)
                    self.log_output.append_log(f"{name} = {value}", "success")
                if self.preset_path_check.isChecked():
                    path_lines = []
                    conda_root = env_vars.get("CONDA_ROOT")
                    cuda_path = env_vars.get("CUDA_PATH")
                    if conda_root:
                        path_lines.append(f'export PATH="{conda_root}/bin:$PATH"')
                    if cuda_path:
                        path_lines.extend([
                            f'export PATH="{cuda_path}/bin:$PATH"',
                            f'export LD_LIBRARY_PATH="{cuda_path}/lib64:$LD_LIBRARY_PATH"',
                        ])
                    for line in path_lines:
                        var_name = line.split("=")[0].replace("export ", "")
                        check_cmd = f'grep -q "^export {var_name}=" ~/.bashrc 2>/dev/null && echo "exists" || echo "not_found"'
                        rc, out, err = executor.execute(check_cmd, timeout=10)
                        if "exists" in out:
                            executor.execute(f"sed -i 's|^export {var_name}=.*|{line}|' ~/.bashrc", timeout=10)
                        else:
                            executor.execute(f"echo '{line}' >> ~/.bashrc", timeout=10)
                self.log_output.append_log(i18n.t("deploy_envvar_applied_wsl"), "success")
                self.config_finished.emit(True, i18n.t("deploy_envvar_applied_wsl"))
            except Exception as e:
                self.log_output.append_log(f"Error: {e}", "error")
                self.config_finished.emit(False, str(e))
        else:
            try:
                paths_to_add = []
                if self.preset_path_check.isChecked():
                    conda_root = env_vars.get("CONDA_ROOT")
                    cuda_path = env_vars.get("CUDA_PATH")
                    if conda_root:
                        paths_to_add.extend([
                            conda_root,
                            os.path.join(conda_root, "Scripts"),
                            os.path.join(conda_root, "condabin"),
                        ])
                    if cuda_path:
                        paths_to_add.extend([
                            os.path.join(cuda_path, "bin"),
                            os.path.join(cuda_path, "libnvvp"),
                        ])
                _set_windows_user_env(env_vars, paths_to_add)
                for name, value in env_vars.items():
                    self.log_output.append_log(f"{name} = {value}", "success")
                self.log_output.append_log(i18n.t("deploy_envvar_applied_local"), "success")
                self.config_finished.emit(True, i18n.t("deploy_envvar_applied_local"))
            except Exception as e:
                self.log_output.append_log(f"Error: {e}", "error")
                self.config_finished.emit(False, str(e))

    def update_wsl_config(self, config: dict):
        self.wsl_config = config
        if config.get("distro") and self.target_combo.currentIndex() == 1:
            idx = self.wsl_distro_combo.findText(config["distro"])
            if idx >= 0:
                self.wsl_distro_combo.setCurrentIndex(idx)

    def _refresh_delete_btn_styles(self):
        style = get_dark_delete_btn_style() if self.theme == "dark" else get_light_delete_btn_style()
        for row in range(1, self.env_vars_layout.rowCount()):
            item = self.env_vars_layout.itemAtPosition(row, 2)
            if item and item.widget():
                item.widget().setStyleSheet(style)


class CudaInstaller(QWidget):
    install_started = Signal()
    install_finished = Signal(bool, str)

    def __init__(self, parent=None, wsl_config=None, theme="light"):
        super().__init__(parent)
        self.wsl_config = wsl_config or {}
        self.theme = theme
        self._worker = None
        self.setObjectName("deployPage")
        self._setup_ui()

    def set_theme(self, theme: str):
        self.theme = theme
        self.step_indicator.set_theme(theme)
        self.log_output.set_theme(theme)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)



        target_group = QGroupBox(i18n.t("deploy_target"))
        target_layout = QFormLayout(target_group)
        target_layout.setSpacing(10)

        self.target_combo = QComboBox()
        self.target_combo.addItems(["Windows (本地)", "WSL (Linux)"])
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        target_layout.addRow(i18n.t("deploy_install_target"), self.target_combo)

        self.wsl_distro_combo = QComboBox()
        self.wsl_distro_combo.setEnabled(False)
        self.wsl_distro_combo.currentIndexChanged.connect(self._load_wsl_users)
        target_layout.addRow(i18n.t("deploy_wsl_distro"), self.wsl_distro_combo)

        self.wsl_user_combo = QComboBox()
        self.wsl_user_combo.setEnabled(False)
        target_layout.addRow(i18n.t("deploy_wsl_user"), self.wsl_user_combo)

        self.wsl_password_edit = QLineEdit()
        self.wsl_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.wsl_password_edit.setEnabled(False)
        self.wsl_password_edit.setPlaceholderText(i18n.t("deploy_wsl_password_ph"))
        target_layout.addRow(i18n.t("deploy_wsl_password"), self.wsl_password_edit)

        layout.addWidget(target_group)

        cuda_group = QGroupBox(i18n.t("deploy_cuda_config"))
        cuda_layout = QFormLayout(cuda_group)
        cuda_layout.setSpacing(10)

        version_row = QHBoxLayout()
        self.cuda_version_combo = QComboBox()
        self.cuda_version_combo.addItems(FALLBACK_CUDA_VERSIONS)
        version_row.addWidget(self.cuda_version_combo, 1)

        self.refresh_versions_btn = QPushButton(i18n.t("deploy_cuda_refresh_versions"))
        self.refresh_versions_btn.clicked.connect(self._load_cuda_versions)
        version_row.addWidget(self.refresh_versions_btn)
        cuda_layout.addRow(i18n.t("deploy_cuda_version"), version_row)

        self.auto_cuda_envvar_check = QCheckBox(i18n.t("deploy_auto_envvar"))
        self.auto_cuda_envvar_check.setChecked(True)
        cuda_layout.addRow(self.auto_cuda_envvar_check)

        layout.addWidget(cuda_group)

        step_labels = [
            i18n.t("deploy_cuda_step_check"),
            i18n.t("deploy_cuda_step_install"),
            i18n.t("deploy_cuda_step_verify"),
        ]
        self.step_indicator = StepIndicator(step_labels, theme=self.theme)
        layout.addWidget(self.step_indicator)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_output = LogOutput(theme=self.theme)
        layout.addWidget(self.log_output, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.check_btn = QPushButton(i18n.t("deploy_cuda_check"))
        self.check_btn.clicked.connect(self._check_cuda)

        self.install_btn = QPushButton(i18n.t("deploy_cuda_install"))
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self._start_install)

        btn_layout.addWidget(self.check_btn)
        btn_layout.addWidget(self.install_btn)
        layout.addLayout(btn_layout)

        self._load_wsl_distros()
        self._on_target_changed(self.target_combo.currentIndex())
        self._load_cuda_versions()

    def _on_target_changed(self, index):
        is_wsl = index == 1
        self.wsl_distro_combo.setEnabled(is_wsl)
        self.wsl_user_combo.setEnabled(is_wsl)
        self.wsl_password_edit.setEnabled(is_wsl)
        if not is_wsl:
            self.wsl_distro_combo.setCurrentIndex(-1)
            self.wsl_user_combo.setCurrentIndex(-1)
            self.wsl_password_edit.clear()
        else:
            if self.wsl_distro_combo.currentIndex() < 0 and self.wsl_distro_combo.count() > 0:
                self.wsl_distro_combo.setCurrentIndex(0)
            self._load_wsl_users()

    def _load_wsl_distros(self):
        self.wsl_distro_combo.clear()
        try:
            rc, stdout, stderr = _run_wsl_command(["wsl", "-l", "-q"])
            if rc == 0 and stdout:
                distros = [d.strip() for d in stdout.split("\n") if d.strip()]
                self.wsl_distro_combo.addItems(distros)
            else:
                self.wsl_distro_combo.addItem("Ubuntu")
        except Exception:
            self.wsl_distro_combo.addItem("Ubuntu")
        if self.target_combo.currentIndex() != 1:
            self.wsl_distro_combo.setCurrentIndex(-1)
        self._load_wsl_users()

    def _load_wsl_users(self):
        self.wsl_user_combo.clear()
        if self.target_combo.currentIndex() != 1:
            self.wsl_user_combo.setCurrentIndex(-1)
            return
        distro = self.wsl_distro_combo.currentText() or None
        executor = WSLCommandExecutor(distro=distro)
        users = ["root"]
        try:
            rc, out, err = executor.execute(
                "awk -F: '($3 >= 1000 && $7 !~ /(false|nologin)$/) {print $1}' /etc/passwd",
                timeout=10,
            )
            if rc == 0 and out.strip():
                for user in out.splitlines():
                    user = user.strip()
                    if user and user not in users:
                        users.append(user)
        except Exception:
            pass
        self.wsl_user_combo.addItems(users)
        preferred = self.wsl_config.get("username")
        if preferred:
            idx = self.wsl_user_combo.findText(preferred)
            if idx >= 0:
                self.wsl_user_combo.setCurrentIndex(idx)

    def _load_cuda_versions(self):
        self.refresh_versions_btn.setEnabled(False)
        self.refresh_versions_btn.setText(i18n.t("deploy_cuda_loading_versions"))
        self._version_worker = Worker(self._fetch_cuda_versions)
        self._version_worker.result.connect(self._on_cuda_versions_loaded)
        self._version_worker.error.connect(self._on_cuda_versions_error)
        self._version_worker.start()

    def _fetch_cuda_versions(self):
        try:
            with urllib.request.urlopen(CUDA_ARCHIVE_URL, timeout=25) as response:
                html = response.read().decode("utf-8", errors="ignore")
            versions = _parse_cuda_versions_from_archive(html)
            return versions or FALLBACK_CUDA_VERSIONS
        except Exception:
            return FALLBACK_CUDA_VERSIONS

    def _on_cuda_versions_loaded(self, versions):
        current = self.cuda_version_combo.currentText()
        self.cuda_version_combo.clear()
        self.cuda_version_combo.addItems(versions)
        if current:
            idx = self.cuda_version_combo.findText(current)
            if idx >= 0:
                self.cuda_version_combo.setCurrentIndex(idx)
        self.refresh_versions_btn.setText(i18n.t("deploy_cuda_refresh_versions"))
        self.refresh_versions_btn.setEnabled(True)

    def _on_cuda_versions_error(self, error_msg: str):
        self.refresh_versions_btn.setText(i18n.t("deploy_cuda_refresh_versions"))
        self.refresh_versions_btn.setEnabled(True)
        self.log_output.append_log(
            f"[WARN] {i18n.t('deploy_cuda_versions_failed')}: {error_msg}", "warning"
        )

    def _check_cuda(self):
        self.log_output.clear_logs()
        self.log_output.append_log(i18n.t("deploy_cuda_checking"), "step")

        if self.target_combo.currentIndex() == 1:
            distro = self.wsl_distro_combo.currentText() or None
            user = self.wsl_user_combo.currentText().strip() or None
            executor = WSLCommandExecutor(distro=distro, user=user)
            try:
                rc, out, err = executor.execute("nvcc --version 2>/dev/null", timeout=15)
                if rc == 0 and out.strip():
                    self.log_output.append_log(
                        i18n.t("deploy_cuda_found").format(out.strip()), "success"
                    )
                else:
                    self.log_output.append_log(i18n.t("deploy_cuda_not_found"), "warning")

                rc, out, err = executor.execute("nvidia-smi 2>/dev/null | head -3", timeout=15)
                if rc == 0 and out.strip():
                    self.log_output.append_log(
                        i18n.t("deploy_nvidia_smi_found").format(out.strip()), "success"
                    )
                else:
                    self.log_output.append_log(i18n.t("deploy_nvidia_smi_not_found"), "warning")

                rc, out, err = executor.execute("ls /usr/local/cuda*/bin/nvcc 2>/dev/null", timeout=15)
                if rc == 0 and out.strip():
                    self.log_output.append_log(f"CUDA installations: {out.strip()}", "info")
            except Exception as e:
                self.log_output.append_log(f"Error: {e}", "error")
            return

        cuda_path = _detect_windows_cuda_path()
        if cuda_path:
            self.log_output.append_log(f"CUDA_PATH = {cuda_path}", "success")
        try:
            result = subprocess.run(
                ["nvcc", "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode == 0:
                self.log_output.append_log(
                    i18n.t("deploy_cuda_found").format(result.stdout.strip() or result.stderr.strip()),
                    "success",
                )
            else:
                self.log_output.append_log(i18n.t("deploy_cuda_not_found"), "warning")
        except FileNotFoundError:
            self.log_output.append_log(i18n.t("deploy_cuda_not_found"), "warning")
        except Exception as e:
            self.log_output.append_log(f"Error: {e}", "error")

        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode == 0:
                self.log_output.append_log(
                    i18n.t("deploy_nvidia_smi_found").format("\n".join(result.stdout.splitlines()[:3])),
                    "success",
                )
            else:
                self.log_output.append_log(i18n.t("deploy_nvidia_smi_not_found"), "warning")
        except Exception:
            self.log_output.append_log(i18n.t("deploy_nvidia_smi_not_found"), "warning")

    def _resolve_cuda_installer_urls(self, cuda_version: str, target: str) -> list[str]:
        try:
            with urllib.request.urlopen(_cuda_archive_page_url(cuda_version), timeout=30) as response:
                html = response.read().decode("utf-8", errors="ignore")
            urls = _parse_cuda_installer_links(html, cuda_version, target)
            if urls:
                return urls
        except Exception:
            pass

        if target == "windows":
            return [
                f"{CUDA_DOWNLOAD_ROOT}/{cuda_version}/local_installers/cuda_{cuda_version}_windows.exe"
            ]
        return [
            f"{CUDA_DOWNLOAD_ROOT}/{cuda_version}/local_installers/cuda_{cuda_version}_linux.run"
        ]

    def _start_install(self):
        cuda_version_text = self.cuda_version_combo.currentText()
        cuda_version = cuda_version_text.split(" ")[0].strip()
        if not cuda_version:
            self.log_output.append_log(i18n.t("deploy_cuda_no_version"), "error")
            return

        mirror_dialog = InstallMirrorDialog(
            "deploy_cuda_source_title", CUDA_DOWNLOAD_SOURCES, self, self.theme
        )
        if mirror_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = mirror_dialog.selected_source

        is_wsl = self.target_combo.currentIndex() == 1
        distro = self.wsl_distro_combo.currentText() or None
        user = self.wsl_user_combo.currentText().strip() if is_wsl else None
        password = self.wsl_password_edit.text() if is_wsl else None
        auto_envvar = self.auto_cuda_envvar_check.isChecked()

        self.install_btn.setEnabled(False)
        self.check_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_output.clear_logs()
        self.install_started.emit()

        if is_wsl:
            self._worker = Worker(
                self._install_cuda_wsl, distro, user, password, cuda_version, source, auto_envvar
            )
        else:
            self._worker = Worker(
                self._install_cuda_windows, cuda_version, source, auto_envvar
            )
        self._worker.progress.connect(self._on_progress)
        self._worker.result.connect(self._on_install_result)
        self._worker.error.connect(self._on_install_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        if msg.startswith("STEP:"):
            step = int(msg.split(":")[1])
            self.step_indicator.set_step(step)
            self.progress_bar.setValue(min(step * 33, 100))
        elif msg.startswith("PROGRESS:"):
            pct = int(msg.split(":")[1])
            self.progress_bar.setValue(pct)
        else:
            level = "info"
            if msg.startswith("[OK]"):
                level = "success"
            elif msg.startswith("[WARN]"):
                level = "warning"
            elif msg.startswith("[ERR]"):
                level = "error"
            self.log_output.append_log(msg, level)

    def _on_install_result(self, result):
        self.install_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        success, message = result
        if success:
            self.progress_bar.setValue(100)
            self.step_indicator.set_step(3)
            self.log_output.append_log(message, "success")
        else:
            self.log_output.append_log(message, "error")
        self.install_finished.emit(success, message)

    def _on_install_error(self, error_msg: str):
        self.install_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        self.log_output.append_log(f"[ERR] {error_msg}", "error")
        self.install_finished.emit(False, error_msg)

    def _install_cuda_windows(self, cuda_version: str, source: DownloadSource, auto_envvar: bool):
        progress = self._worker.progress

        progress.emit("STEP:0")
        progress.emit(i18n.t("deploy_cuda_resolving_installer").format(cuda_version))
        official_urls = self._resolve_cuda_installer_urls(cuda_version, "windows")
        urls = _build_cuda_download_urls(official_urls, source)
        filename = _url_filename(urls[0], f"cuda_{cuda_version}_windows.exe")
        installer_path = os.path.join(tempfile.gettempdir(), filename)

        ok, info = _download_url_candidates(urls, installer_path, progress, progress_span=50)
        if not ok:
            progress.emit(f"[ERR] {i18n.t('deploy_download_failed')}: {info}")
            return False, info
        progress.emit(f"[OK] {i18n.t('deploy_download_complete')}: {info}")

        progress.emit("STEP:1")
        progress.emit(i18n.t("deploy_cuda_running_windows_installer"))
        try:
            result = subprocess.run(
                [installer_path, "-s"],
                capture_output=True,
                text=True,
                timeout=3600,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode != 0:
                progress.emit(f"[ERR] {i18n.t('deploy_cuda_install_failed')}: {result.stderr or result.stdout}")
                return False, result.stderr or result.stdout
            progress.emit(f"[OK] {i18n.t('deploy_cuda_install_complete')}")
        except Exception as e:
            progress.emit(f"[ERR] {i18n.t('deploy_cuda_install_failed')}: {e}")
            return False, str(e)

        progress.emit("STEP:2")
        if auto_envvar:
            progress.emit(i18n.t("deploy_cuda_configuring_env"))
            try:
                cuda_path = _detect_windows_cuda_path() or _cuda_windows_install_path(cuda_version)
                _set_windows_user_env(
                    {"CUDA_PATH": cuda_path},
                    [os.path.join(cuda_path, "bin"), os.path.join(cuda_path, "libnvvp")],
                )
                progress.emit(f"[OK] CUDA_PATH = {cuda_path}")
            except Exception as e:
                progress.emit(f"[WARN] {i18n.t('deploy_cuda_env_failed')}: {e}")

        try:
            cuda_path = _detect_windows_cuda_path() or _cuda_windows_install_path(cuda_version)
            nvcc_path = os.path.join(cuda_path, "bin", "nvcc.exe")
            result = subprocess.run(
                [nvcc_path, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode == 0:
                progress.emit(f"[OK] {result.stdout.strip() or result.stderr.strip()}")
            else:
                progress.emit(f"[WARN] {i18n.t('deploy_cuda_verify_failed')}")
        except Exception as e:
            progress.emit(f"[WARN] {i18n.t('deploy_cuda_verify_failed')}: {e}")

        try:
            os.remove(installer_path)
        except Exception:
            pass

        return True, i18n.t("deploy_cuda_install_success").format(cuda_version)

    def _install_cuda_wsl(
        self,
        distro: str,
        user: str,
        password: str,
        cuda_version: str,
        source: DownloadSource,
        auto_envvar: bool,
    ):
        progress = self._worker.progress
        executor = WSLCommandExecutor(
            distro=distro if distro else None,
            user=user if user else None,
            password=password if password else None,
        )

        progress.emit("STEP:0")
        progress.emit(i18n.t("deploy_cuda_checking_env"))

        try:
            rc, out, err = executor.execute("which gcc g++ make wget curl 2>/dev/null | wc -l", timeout=15)
            if rc != 0 or not out.strip() or int(out.strip()) < 5:
                progress.emit(i18n.t("deploy_cuda_install_deps"))
                executor.execute_sudo("apt-get update", timeout=120)
                executor.execute_sudo(
                    "apt-get install -y gcc g++ make wget curl",
                    timeout=300,
                )
                progress.emit(f"[OK] {i18n.t('deploy_cuda_deps_installed')}")
            else:
                progress.emit(f"[OK] {i18n.t('deploy_cuda_deps_ok')}")
        except Exception as e:
            progress.emit(f"[WARN] {i18n.t('deploy_cuda_deps_check_failed')}: {e}")

        progress.emit("STEP:1")
        progress.emit(i18n.t("deploy_cuda_downloading_runfile").format(cuda_version))
        official_urls = self._resolve_cuda_installer_urls(cuda_version, "wsl")
        urls = _build_cuda_download_urls(official_urls, source)
        installer_path = "/tmp/cuda_installer.run"

        try:
            commands = []
            for url in urls:
                commands.append(
                    f"(wget -q --show-progress -O {_wsl_quote(installer_path)} {_wsl_quote(url)} 2>&1 "
                    f"|| curl -fL -o {_wsl_quote(installer_path)} {_wsl_quote(url)} 2>&1)"
                )
            rc, out, err = executor.execute(" || ".join(commands), timeout=1800)
            if rc != 0:
                progress.emit(f"[ERR] {i18n.t('deploy_download_failed')}: {err or out}")
                return False, err or out

            progress.emit(i18n.t("deploy_cuda_running_runfile"))
            install_path = f"/usr/local/cuda-{cuda_version}"
            rc, out, err = executor.execute_sudo(
                f"sh {_wsl_quote(installer_path)} --toolkit --silent --override --installpath={_wsl_quote(install_path)}",
                timeout=1800,
            )
            if rc != 0:
                progress.emit(f"[ERR] {i18n.t('deploy_cuda_install_failed')}: {err or out}")
                return False, err or out

            executor.execute_sudo(
                f"ln -sf {_wsl_quote(install_path)} /usr/local/cuda",
                timeout=15,
            )
            progress.emit(f"[OK] {i18n.t('deploy_cuda_install_complete')}")
        except Exception as e:
            progress.emit(f"[ERR] {i18n.t('deploy_cuda_install_failed')}: {e}")
            return False, str(e)

        progress.emit("STEP:2")

        if auto_envvar:
            progress.emit(i18n.t("deploy_cuda_configuring_env"))
            try:
                cuda_path = f"/usr/local/cuda-{cuda_version}"
                bashrc_lines = [
                    f'export CUDA_PATH="{cuda_path}"',
                    f'export PATH="{cuda_path}/bin:$PATH"',
                    f'export LD_LIBRARY_PATH="{cuda_path}/lib64:$LD_LIBRARY_PATH"',
                ]
                for line in bashrc_lines:
                    var_name = line.split("=")[0].replace("export ", "")
                    check_cmd = f'grep -q "^export {var_name}=" ~/.bashrc 2>/dev/null && echo "exists" || echo "not_found"'
                    rc, out, err = executor.execute(check_cmd, timeout=10)
                    if "exists" in out:
                        executor.execute(f"sed -i 's|^export {var_name}=.*|{line}|' ~/.bashrc", timeout=10)
                    else:
                        executor.execute(f"echo '{line}' >> ~/.bashrc", timeout=10)
                progress.emit(f"[OK] {i18n.t('deploy_cuda_env_configured')}")
            except Exception as e:
                progress.emit(f"[WARN] {i18n.t('deploy_cuda_env_failed')}: {e}")

        try:
            cuda_path = f"/usr/local/cuda-{cuda_version}"
            rc, out, err = executor.execute(f"{_wsl_quote(cuda_path + '/bin/nvcc')} --version", timeout=15)
            if rc == 0 and out.strip():
                progress.emit(f"[OK] {out.strip()}")
            else:
                progress.emit(f"[WARN] {i18n.t('deploy_cuda_verify_failed')}")
        except Exception as e:
            progress.emit(f"[WARN] {i18n.t('deploy_cuda_verify_failed')}: {e}")

        try:
            executor.execute(f"rm -f {_wsl_quote(installer_path)}", timeout=10)
        except Exception:
            pass

        return True, i18n.t("deploy_cuda_install_success").format(cuda_version)

    def update_wsl_config(self, config: dict):
        self.wsl_config = config
        if config.get("distro"):
            idx = self.wsl_distro_combo.findText(config["distro"])
            if idx >= 0:
                self.wsl_distro_combo.setCurrentIndex(idx)
        if config.get("username"):
            idx = self.wsl_user_combo.findText(config["username"])
            if idx >= 0:
                self.wsl_user_combo.setCurrentIndex(idx)
        if config.get("password"):
            self.wsl_password_edit.setText(config["password"])


class WSLFeatureInstaller(QWidget):
    install_started = Signal()
    install_finished = Signal(bool, str)

    def __init__(self, parent=None, theme="light"):
        super().__init__(parent)
        self.theme = theme
        self._worker = None
        self.setObjectName("deployPage")
        self._setup_ui()

    def set_theme(self, theme: str):
        self.theme = theme
        self.step_indicator.set_theme(theme)
        self.log_output.set_theme(theme)
        if hasattr(self, '_info_label'):
            color = DARK_COLORS['text_secondary'] if theme == "dark" else COLORS['text_secondary']
            self._info_label.setStyleSheet(f"color: {color}; font-size: 12px; padding: 4px;")

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)



        status_group = QGroupBox(i18n.t("deploy_wsl_install_status"))
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)

        layout.addWidget(status_group)

        info_group = QGroupBox(i18n.t("deploy_wsl_feature_info"))
        info_layout = QVBoxLayout(info_group)
        info_label = QLabel(i18n.t("deploy_wsl_feature_info_text"))
        info_label.setWordWrap(True)
        info_label_color = DARK_COLORS['text_secondary'] if self.theme == "dark" else COLORS['text_secondary']
        info_label.setStyleSheet(f"color: {info_label_color}; font-size: 12px; padding: 4px;")
        self._info_label = info_label
        info_layout.addWidget(info_label)
        layout.addWidget(info_group)

        step_labels = [
            i18n.t("deploy_wsl_step_check"),
            i18n.t("deploy_wsl_step_enable"),
            i18n.t("deploy_wsl_step_verify"),
        ]
        self.step_indicator = StepIndicator(step_labels, theme=self.theme)
        layout.addWidget(self.step_indicator)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_output = LogOutput(theme=self.theme)
        layout.addWidget(self.log_output, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.check_btn = QPushButton(i18n.t("deploy_wsl_check"))
        self.check_btn.clicked.connect(self._check_wsl_status)

        self.install_btn = QPushButton(i18n.t("deploy_wsl_feature_install_btn"))
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self._start_install)

        btn_layout.addWidget(self.check_btn)
        btn_layout.addWidget(self.install_btn)
        layout.addLayout(btn_layout)

        self._check_wsl_status()

    def _check_wsl_status(self):
        self.log_output.clear_logs()
        self.log_output.append_log(i18n.t("deploy_wsl_checking"), "step")

        wsl_available = False

        try:
            rc, stdout, stderr = _run_wsl_command(["wsl", "--status"])
            if rc == 0:
                wsl_available = True
                self.log_output.append_log(
                    i18n.t("deploy_wsl_feature_enabled"), "success"
                )
                if stdout:
                    self.log_output.append_log(stdout, "info")
            else:
                self.log_output.append_log(i18n.t("deploy_wsl_not_installed"), "warning")
        except FileNotFoundError:
            self.log_output.append_log(i18n.t("deploy_wsl_not_installed"), "warning")
        except subprocess.TimeoutExpired:
            self.log_output.append_log(i18n.t("deploy_wsl_timeout"), "warning")
        except Exception as e:
            self.log_output.append_log(f"Error: {e}", "error")

        if wsl_available:
            self.status_label.setText(i18n.t("deploy_wsl_status_installed"))
            success_color = DARK_COLORS['success'] if self.theme == "dark" else COLORS['success']
            self.status_label.setStyleSheet(
                f"color: {success_color}; font-weight: bold; font-size: 13px;"
            )
        else:
            self.status_label.setText(i18n.t("deploy_wsl_status_not_installed"))
            danger_color = DARK_COLORS['danger'] if self.theme == "dark" else COLORS['danger']
            self.status_label.setStyleSheet(
                f"color: {danger_color}; font-weight: bold; font-size: 13px;"
            )

        return wsl_available

    def _start_install(self):
        self.install_btn.setEnabled(False)
        self.check_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_output.clear_logs()
        self.install_started.emit()

        self._worker = Worker(self._install_wsl_feature)
        self._worker.progress.connect(self._on_progress)
        self._worker.result.connect(self._on_install_result)
        self._worker.error.connect(self._on_install_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        if msg.startswith("STEP:"):
            step = int(msg.split(":")[1])
            self.step_indicator.set_step(step)
            self.progress_bar.setValue(min(step * 33, 100))
        elif msg.startswith("PROGRESS:"):
            pct = int(msg.split(":")[1])
            self.progress_bar.setValue(pct)
        else:
            level = "info"
            if msg.startswith("[OK]"):
                level = "success"
            elif msg.startswith("[WARN]"):
                level = "warning"
            elif msg.startswith("[ERR]"):
                level = "error"
            self.log_output.append_log(msg, level)

    def _on_install_result(self, result):
        self.install_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        success, message = result
        if success:
            self.progress_bar.setValue(100)
            self.step_indicator.set_step(3)
            self.log_output.append_log(message, "success")
            self._check_wsl_status()
        else:
            self.log_output.append_log(message, "error")
        self.install_finished.emit(success, message)

    def _on_install_error(self, error_msg: str):
        self.install_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        self.log_output.append_log(f"[ERR] {error_msg}", "error")
        self.install_finished.emit(False, error_msg)

    def _install_wsl_feature(self):
        progress = self._worker.progress

        progress.emit("STEP:0")
        progress.emit(i18n.t("deploy_wsl_checking"))

        try:
            rc, stdout, stderr = _run_wsl_command(["wsl", "--status"])
            if rc == 0:
                progress.emit(f"[OK] {i18n.t('deploy_wsl_feature_enabled')}")
                progress.emit("STEP:2")
                progress.emit(f"[OK] {i18n.t('deploy_wsl_verify_ok')}")
                return True, i18n.t("deploy_wsl_feature_already_enabled")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception as e:
            progress.emit(f"[WARN] Check error: {e}")

        progress.emit(i18n.t("deploy_wsl_not_installed"))
        progress.emit("STEP:1")
        progress.emit(i18n.t("deploy_wsl_enabling"))

        try:
            subprocess.run(
                ["powershell", "-Command",
                 "Start-Process powershell -ArgumentList '-Command','dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart' -Verb RunAs -Wait"],
                capture_output=True,
                timeout=120,
            )
            subprocess.run(
                ["powershell", "-Command",
                 "Start-Process powershell -ArgumentList '-Command','dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart' -Verb RunAs -Wait"],
                capture_output=True,
                timeout=120,
            )
            progress.emit(f"[OK] {i18n.t('deploy_wsl_feature_enabled')}")
        except Exception as e:
            progress.emit(f"[ERR] {i18n.t('deploy_wsl_enable_failed')}: {e}")
            progress.emit(i18n.t("deploy_wsl_enable_hint"))
            return False, str(e)

        progress.emit("STEP:2")
        progress.emit(i18n.t("deploy_wsl_verifying"))

        try:
            rc, stdout, stderr = _run_wsl_command(["wsl", "--status"])
            if rc == 0:
                progress.emit(f"[OK] {i18n.t('deploy_wsl_verify_ok')}")
            else:
                progress.emit(f"[WARN] {i18n.t('deploy_wsl_verify_partial')}")
        except Exception:
            progress.emit(f"[WARN] {i18n.t('deploy_wsl_verify_partial')}")

        return True, i18n.t("deploy_wsl_feature_install_success")


class WSLDistroInstaller(QWidget):
    install_started = Signal()
    install_finished = Signal(bool, str)

    def __init__(self, parent=None, theme="light"):
        super().__init__(parent)
        self.theme = theme
        self._worker = None
        self.setObjectName("deployPage")
        self._setup_ui()

    def set_theme(self, theme: str):
        self.theme = theme
        self.step_indicator.set_theme(theme)
        self.log_output.set_theme(theme)
        if hasattr(self, '_installed_list_label'):
            color = DARK_COLORS['text_secondary'] if theme == "dark" else COLORS['text_secondary']
            self._installed_list_label.setStyleSheet(f"color: {color}; font-size: 12px; padding: 4px;")

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)



        installed_group = QGroupBox(i18n.t("deploy_wsl_installed"))
        installed_layout = QVBoxLayout(installed_group)

        self.installed_list = QLabel()
        self.installed_list.setWordWrap(True)
        installed_list_color = DARK_COLORS['text_secondary'] if self.theme == "dark" else COLORS['text_secondary']
        self.installed_list.setStyleSheet(
            f"color: {installed_list_color}; font-size: 12px; padding: 4px;"
        )
        self._installed_list_label = self.installed_list
        installed_layout.addWidget(self.installed_list)

        refresh_btn = QPushButton(i18n.t("btn_refresh"))
        refresh_btn.clicked.connect(self._refresh_distros)
        installed_layout.addWidget(refresh_btn)

        layout.addWidget(installed_group)

        config_group = QGroupBox(i18n.t("deploy_wsl_distro_config"))
        config_layout = QFormLayout(config_group)
        config_layout.setSpacing(10)

        self.distro_combo = QComboBox()
        self.distro_combo.setPlaceholderText(
            i18n.t("deploy_wsl_distro_name_ph")
        )
        self.distro_combo.currentIndexChanged.connect(self._on_distro_index_changed)
        config_layout.addRow(i18n.t("deploy_wsl_install_distro"), self.distro_combo)

        self.version_combo = QComboBox()
        self.version_combo.setPlaceholderText(
            i18n.t("deploy_wsl_version_ph")
        )
        self.version_combo.currentIndexChanged.connect(self._on_version_index_changed)
        config_layout.addRow(i18n.t("deploy_wsl_version"), self.version_combo)

        self.distro_custom_name_edit = QLineEdit()
        self.distro_custom_name_edit.setPlaceholderText(
            i18n.t("deploy_wsl_custom_name_ph")
        )
        self.distro_custom_name_edit.textChanged.connect(self._update_install_path_placeholder)
        config_layout.addRow(i18n.t("deploy_wsl_custom_name"), self.distro_custom_name_edit)

        self.distro_install_path_edit = QLineEdit()
        self.distro_install_path_edit.setPlaceholderText(
            _default_wsl_import_root(self.distro_custom_name_edit.text().strip() or "Ubuntu")
        )
        config_layout.addRow(i18n.t("deploy_wsl_import_path"), self.distro_install_path_edit)

        root_group = QGroupBox(i18n.t("deploy_wsl_root_config"))
        root_layout = QFormLayout(root_group)
        root_layout.setSpacing(10)

        self.root_password_edit = QLineEdit()
        self.root_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.root_password_edit.setPlaceholderText(
            i18n.t("deploy_wsl_root_pass_ph")
        )
        root_layout.addRow(i18n.t("deploy_wsl_root_pass"), self.root_password_edit)

        config_layout.addRow(root_group)

        user_group = QGroupBox(i18n.t("deploy_wsl_new_user_config"))
        user_layout = QFormLayout(user_group)
        user_layout.setSpacing(10)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(
            i18n.t("deploy_wsl_distro_user_ph")
        )
        user_layout.addRow(i18n.t("deploy_wsl_distro_user"), self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(
            i18n.t("deploy_wsl_distro_pass_ph")
        )
        user_layout.addRow(i18n.t("deploy_wsl_distro_pass"), self.password_edit)

        config_layout.addRow(user_group)

        self.set_default_check = QCheckBox(i18n.t("deploy_wsl_distro_set_default"))
        self.set_default_check.setChecked(True)
        config_layout.addRow(self.set_default_check)

        layout.addWidget(config_group)

        step_labels = [
            i18n.t("deploy_wsl_step_install"),
            i18n.t("deploy_wsl_step_config"),
            i18n.t("deploy_wsl_step_verify"),
        ]
        self.step_indicator = StepIndicator(step_labels, theme=self.theme)
        layout.addWidget(self.step_indicator)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_output = LogOutput(theme=self.theme)
        layout.addWidget(self.log_output, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.check_btn = QPushButton(i18n.t("deploy_wsl_check"))
        self.check_btn.clicked.connect(self._refresh_distros)

        self.install_btn = QPushButton(i18n.t("deploy_wsl_distro_install_btn"))
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self._start_install)

        btn_layout.addWidget(self.check_btn)
        btn_layout.addWidget(self.install_btn)
        layout.addLayout(btn_layout)

        self._refresh_distros()
        self._fetch_online_distros()

    def _fetch_online_distros(self):
        self.log_output.append_log(i18n.t("deploy_wsl_fetching_online"), "step")
        self.distro_combo.clear()
        self.version_combo.clear()
        self._online_distros = {}

        try:
            rc, stdout, stderr = _run_wsl_command(["wsl", "--list", "--online"], timeout=30)
            if rc == 0 and stdout.strip():
                self._parse_online_distros(stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception:
            pass

        if not self._online_distros:
            self._use_fallback_distros()

        for distro_name in sorted(self._online_distros.keys()):
            versions = self._online_distros[distro_name]
            if len(versions) == 1 and versions[0][0] == distro_name:
                self.distro_combo.addItem(distro_name, versions[0][0])
            else:
                self.distro_combo.addItem(distro_name, "")

        if self.distro_combo.count() > 0:
            self.distro_combo.setCurrentIndex(0)
            self.log_output.append_log(
                i18n.t("deploy_wsl_online_count").format(self.distro_combo.count()), "success"
            )
        else:
            self.log_output.append_log(i18n.t("deploy_wsl_online_failed"), "warning")

    def _parse_online_distros(self, output: str):
        for enc in ("utf-16-le", "utf-8", "gbk", "latin-1"):
            try:
                text = output if isinstance(output, str) else output.decode(enc)
                break
            except (UnicodeDecodeError, AttributeError):
                continue
        else:
            text = str(output)

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines:
            parts = line.split(None, 1)
            if len(parts) >= 1 and parts[0] and not parts[0].startswith("NAME"):
                official_name = parts[0]
                friendly = parts[1] if len(parts) > 1 else official_name
                base_name = official_name.split("-")[0] if "-" in official_name else official_name
                if base_name not in self._online_distros:
                    self._online_distros[base_name] = []
                self._online_distros[base_name].append((official_name, friendly))

        merged = {}
        for base, versions in self._online_distros.items():
            if len(versions) == 1 and versions[0][0] == base:
                merged[base] = versions
            else:
                seen = set()
                unique = []
                for official, friendly in versions:
                    if official not in seen:
                        seen.add(official)
                        unique.append((official, friendly))
                merged[base] = unique
        self._online_distros = merged

    def _use_fallback_distros(self):
        self._online_distros = {
            "Ubuntu": [
                ("Ubuntu", "Ubuntu"),
                ("Ubuntu-24.04", "Ubuntu 24.04 LTS"),
                ("Ubuntu-22.04", "Ubuntu 22.04 LTS"),
                ("Ubuntu-20.04", "Ubuntu 20.04 LTS"),
            ],
            "Debian": [
                ("Debian", "Debian GNU/Linux"),
                ("debian-bookworm", "Debian Bookworm"),
                ("debian-bullseye", "Debian Bullseye"),
            ],
            "openSUSE": [
                ("openSUSE-Leap-15.5", "openSUSE Leap 15.5"),
                ("openSUSE-Leap-15.4", "openSUSE Leap 15.4"),
                ("openSUSE-Tumbleweed", "openSUSE Tumbleweed"),
            ],
            "SLES": [("SUSE-Linux-Enterprise-Server-15-SP4", "SUSE Linux Enterprise Server 15 SP4")],
            "Arch": [("Arch", "Arch Linux")],
            "kali-linux": [("kali-linux", "Kali Linux Rolling")],
            "Alpine": [("Alpine", "Alpine Linux")],
        }
        self.log_output.append_log(i18n.t("deploy_wsl_using_fallback"), "warning")

    def _on_distro_index_changed(self, index: int):
        self.version_combo.clear()
        if index < 0:
            return
        base_name = self.distro_combo.itemText(index)
        versions = self._online_distros.get(base_name, [])

        if len(versions) <= 1 and versions and versions[0][0] == base_name:
            self.version_combo.addItem(versions[0][1], versions[0][0])
            self._update_custom_name()
            return

        for official_name, friendly in versions:
            self.version_combo.addItem(friendly, official_name)

        if self.version_combo.count() > 0:
            self.version_combo.setCurrentIndex(0)
        self._update_custom_name()

    def _on_version_index_changed(self, index: int):
        self._update_custom_name()

    def _update_custom_name(self):
        official_name = self._get_selected_official_name()
        if official_name and not self.distro_custom_name_edit.text().strip():
            self.distro_custom_name_edit.setText(official_name)
        self._update_install_path_placeholder()

    def _update_install_path_placeholder(self):
        if not hasattr(self, "distro_install_path_edit"):
            return
        distro_name = self.distro_custom_name_edit.text().strip() or self._get_selected_official_name()
        self.distro_install_path_edit.setPlaceholderText(_default_wsl_import_root(distro_name))

    def _get_selected_official_name(self) -> str:
        version_data = self.version_combo.currentData()
        if version_data:
            return version_data
        distro_data = self.distro_combo.currentData()
        if distro_data:
            return distro_data
        return self.distro_combo.currentText()

    def _refresh_distros(self):
        self.log_output.clear_logs()
        self.log_output.append_log(i18n.t("deploy_wsl_checking"), "step")

        distros = []
        try:
            rc, stdout, stderr = _run_wsl_command(["wsl", "--list", "--verbose"])
            if rc == 0:
                lines = [line.strip() for line in stdout.split("\n") if line.strip()]
                if len(lines) > 1:
                    distros = lines[1:]
                    self.log_output.append_log(
                        i18n.t("deploy_wsl_available").format(len(distros)), "success"
                    )
                    for d in distros:
                        self.log_output.append_log(f"  {d}", "info")
                else:
                    self.log_output.append_log(i18n.t("deploy_wsl_no_distro"), "warning")
            else:
                self.log_output.append_log(i18n.t("deploy_wsl_not_installed"), "warning")
        except FileNotFoundError:
            self.log_output.append_log(i18n.t("deploy_wsl_not_installed"), "warning")
        except subprocess.TimeoutExpired:
            self.log_output.append_log(i18n.t("deploy_wsl_timeout"), "warning")
        except Exception as e:
            self.log_output.append_log(f"Error: {e}", "error")

        self.installed_list.setText("\n".join(distros) if distros else i18n.t("deploy_wsl_no_distro"))

    def _start_install(self):
        install_distro = self._get_selected_official_name()
        custom_name = self.distro_custom_name_edit.text().strip()
        install_path = self.distro_install_path_edit.text().strip()
        root_password = self.root_password_edit.text()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        set_default = self.set_default_check.isChecked()

        if not install_distro:
            self.log_output.append_log(i18n.t("deploy_wsl_no_distro_selected"), "error")
            return

        if not custom_name:
            custom_name = install_distro

        mirror_dialog = InstallMirrorDialog(
            "deploy_wsl_source_title", WSL_ROOTFS_SOURCES, self, self.theme
        )
        if mirror_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = mirror_dialog.selected_source

        self.install_btn.setEnabled(False)
        self.check_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_output.clear_logs()
        self.install_started.emit()

        self._worker = Worker(
            self._install_distro,
            install_distro,
            custom_name,
            install_path,
            root_password,
            username,
            password,
            set_default,
            source,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.result.connect(self._on_install_result)
        self._worker.error.connect(self._on_install_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        if msg.startswith("STEP:"):
            step = int(msg.split(":")[1])
            self.step_indicator.set_step(step)
            self.progress_bar.setValue(min(step * 33, 100))
        elif msg.startswith("PROGRESS:"):
            pct = int(msg.split(":")[1])
            self.progress_bar.setValue(pct)
        else:
            level = "info"
            if msg.startswith("[OK]"):
                level = "success"
            elif msg.startswith("[WARN]"):
                level = "warning"
            elif msg.startswith("[ERR]"):
                level = "error"
            self.log_output.append_log(msg, level)

    def _on_install_result(self, result):
        self.install_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        success, message = result
        if success:
            self.progress_bar.setValue(100)
            self.step_indicator.set_step(3)
            self.log_output.append_log(message, "success")
            self._refresh_distros()
        else:
            self.log_output.append_log(message, "error")
        self.install_finished.emit(success, message)

    def _on_install_error(self, error_msg: str):
        self.install_btn.setEnabled(True)
        self.check_btn.setEnabled(True)
        self.log_output.append_log(f"[ERR] {error_msg}", "error")
        self.install_finished.emit(False, error_msg)

    def _install_distro(
        self,
        install_distro: str,
        custom_name: str,
        install_path: str,
        root_password: str,
        username: str,
        password: str,
        set_default: bool,
        source: DownloadSource,
    ):
        progress = self._worker.progress
        effective_name = custom_name or install_distro
        installed_by_rootfs = False

        progress.emit("STEP:0")
        progress.emit(i18n.t("deploy_wsl_installing_distro").format(install_distro))

        rootfs_urls = _build_wsl_rootfs_urls(install_distro, source)
        if rootfs_urls:
            try:
                progress.emit(i18n.t("deploy_wsl_try_rootfs"))
                rootfs_name = _url_filename(rootfs_urls[0], f"{effective_name}.tar.gz")
                rootfs_path = os.path.join(tempfile.gettempdir(), rootfs_name)
                ok, info = _download_url_candidates(rootfs_urls, rootfs_path, progress, progress_span=50)
                if ok:
                    import_root = _resolve_wsl_import_root(effective_name, install_path)
                    os.makedirs(import_root, exist_ok=True)
                    import_result = subprocess.run(
                        ["wsl", "--import", effective_name, import_root, rootfs_path, "--version", "2"],
                        capture_output=True,
                        text=True,
                        timeout=600,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                    if import_result.returncode == 0:
                        installed_by_rootfs = True
                        progress.emit(f"[OK] {i18n.t('deploy_wsl_distro_installed').format(effective_name)}")
                    else:
                        progress.emit(
                            f"[WARN] {i18n.t('deploy_wsl_rootfs_failed')}: "
                            f"{import_result.stderr or import_result.stdout}"
                        )
                else:
                    progress.emit(f"[WARN] {i18n.t('deploy_wsl_rootfs_failed')}: {info}")
                try:
                    os.remove(rootfs_path)
                except Exception:
                    pass
            except Exception as e:
                progress.emit(f"[WARN] {i18n.t('deploy_wsl_rootfs_failed')}: {e}")

        if not installed_by_rootfs:
            try:
                rc, stdout, stderr = _run_wsl_command(["wsl", "--install", "-d", install_distro], timeout=1800)
                if rc == 0:
                    progress.emit(f"[OK] {i18n.t('deploy_wsl_distro_installed').format(install_distro)}")
                else:
                    error_msg = stderr or stdout
                    if error_msg:
                        progress.emit(f"[WARN] {error_msg}")
                    progress.emit(i18n.t("deploy_wsl_try_winget"))
                    try:
                        result2 = subprocess.run(
                            ["winget", "install", f"Microsoft.{install_distro.replace('-', '.')}", "--accept-source-agreements", "--accept-package-agreements"],
                            capture_output=True,
                            text=True,
                            timeout=1800,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        )
                        if result2.returncode == 0:
                            progress.emit(f"[OK] {i18n.t('deploy_wsl_distro_installed').format(install_distro)}")
                        else:
                            progress.emit(f"[ERR] {i18n.t('deploy_wsl_install_failed')}")
                            return False, result2.stderr or result2.stdout or "Unknown error"
                    except FileNotFoundError:
                        progress.emit(f"[ERR] {i18n.t('deploy_wsl_install_failed')}")
                        return False, error_msg or "WSL install failed and winget not available"
            except subprocess.TimeoutExpired:
                progress.emit(f"[ERR] {i18n.t('deploy_wsl_install_timeout')}")
                return False, "Install timed out"
            except Exception as e:
                progress.emit(f"[ERR] {i18n.t('deploy_wsl_install_failed')}: {e}")
                return False, str(e)

        if installed_by_rootfs:
            progress.emit(f"[OK] {i18n.t('deploy_wsl_rootfs_imported')}")
        elif (custom_name and custom_name != install_distro) or install_path:
            try:
                progress.emit(i18n.t("deploy_wsl_renaming_distro").format(install_distro, custom_name))
                export_result = subprocess.run(
                    ["wsl", "--export", install_distro, "-"],
                    capture_output=True,
                    timeout=300,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                if export_result.returncode == 0:
                    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
                        tmp.write(export_result.stdout)
                        tmp_path = tmp.name
                    try:
                        subprocess.run(
                            ["wsl", "--unregister", install_distro],
                            capture_output=True,
                            timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        )
                        import_root = _resolve_wsl_import_root(custom_name, install_path)
                        os.makedirs(import_root, exist_ok=True)
                        import_result = subprocess.run(
                            ["wsl", "--import", custom_name, import_root, tmp_path],
                            capture_output=True,
                            timeout=300,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        )
                        if import_result.returncode == 0:
                            progress.emit(f"[OK] {i18n.t('deploy_wsl_renamed').format(custom_name)}")
                            effective_name = custom_name
                        else:
                            progress.emit(f"[WARN] {i18n.t('deploy_wsl_rename_failed')}")
                            effective_name = install_distro
                    finally:
                        os.unlink(tmp_path)
                else:
                    progress.emit(f"[WARN] {i18n.t('deploy_wsl_rename_failed')}")
                    effective_name = install_distro
            except Exception as e:
                progress.emit(f"[WARN] {i18n.t('deploy_wsl_rename_failed')}: {e}")
                effective_name = install_distro

        progress.emit("STEP:1")
        progress.emit(i18n.t("deploy_wsl_configuring_user"))

        if root_password:
            try:
                progress.emit(i18n.t("deploy_wsl_setting_root"))
                executor = WSLCommandExecutor(distro=effective_name)
                chpasswd_cmd = f"echo 'root:{root_password}' | chpasswd"
                executor.execute_sudo(chpasswd_cmd, timeout=15)
                progress.emit(f"[OK] {i18n.t('deploy_wsl_root_set')}")
            except Exception as e:
                progress.emit(f"[WARN] {i18n.t('deploy_wsl_root_set_failed')}: {e}")

        if username and password:
            try:
                progress.emit(i18n.t("deploy_wsl_setting_user").format(username))
                executor = WSLCommandExecutor(distro=effective_name)
                useradd_cmd = f"useradd -m -s /bin/bash {username} 2>/dev/null || echo 'user_exists'"
                rc, out, err = executor.execute_sudo(useradd_cmd, timeout=30)
                if "user_exists" not in out:
                    chpasswd_cmd = f"echo '{username}:{password}' | chpasswd"
                    executor.execute_sudo(chpasswd_cmd, timeout=15)
                    progress.emit(f"[OK] {i18n.t('deploy_wsl_user_created').format(username)}")
                else:
                    chpasswd_cmd = f"echo '{username}:{password}' | chpasswd"
                    executor.execute_sudo(chpasswd_cmd, timeout=15)
                    progress.emit(f"[OK] {i18n.t('deploy_wsl_user_updated').format(username)}")

                executor_sudo = WSLCommandExecutor(distro=effective_name, user=username)
                rc, out, err = executor_sudo.execute("whoami", timeout=10)
                if rc == 0 and username in out:
                    progress.emit(f"[OK] {i18n.t('deploy_wsl_user_verified').format(username)}")
                else:
                    progress.emit(f"[WARN] {i18n.t('deploy_wsl_user_verify_failed')}")
            except Exception as e:
                progress.emit(f"[WARN] {i18n.t('deploy_wsl_user_config_failed')}: {e}")
        elif username:
            progress.emit(f"[WARN] {i18n.t('deploy_wsl_user_no_password')}")
        elif not root_password:
            progress.emit(i18n.t("deploy_wsl_user_skipped"))

        if set_default:
            try:
                subprocess.run(
                    ["wsl", "--set-default-distro", effective_name],
                    capture_output=True,
                    timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                progress.emit(f"[OK] {i18n.t('deploy_wsl_set_default').format(effective_name)}")
            except Exception as e:
                progress.emit(f"[WARN] {i18n.t('deploy_wsl_set_default_failed')}: {e}")

        progress.emit("STEP:2")
        progress.emit(i18n.t("deploy_wsl_verifying"))

        try:
            rc, stdout, stderr = _run_wsl_command(["wsl", "-l", "-v"], timeout=15)
            if rc == 0:
                progress.emit(f"[OK] {i18n.t('deploy_wsl_verify_ok')}")
                progress.emit(stdout)
            else:
                progress.emit(f"[WARN] {i18n.t('deploy_wsl_verify_partial')}")
        except Exception as e:
            progress.emit(f"[WARN] {i18n.t('deploy_wsl_verify_partial')}: {e}")

        try:
            executor = WSLCommandExecutor(distro=effective_name)
            rc, out, err = executor.execute("cat /etc/os-release | head -4", timeout=15)
            if rc == 0 and out.strip():
                progress.emit(f"[OK] {out.strip()}")
        except Exception:
            pass

        return True, i18n.t("deploy_wsl_install_success").format(effective_name)


class EnvDeployPanel(QWidget):
    def __init__(self, parent=None, wsl_config=None, theme="light"):
        super().__init__(parent)
        self.wsl_config = wsl_config or {}
        self.theme = theme
        self.setObjectName("envDeployPanel")
        self._setup_ui()

    def set_theme(self, theme: str):
        self.theme = theme
        self.setStyleSheet(get_deploy_panel_container_style(theme))
        self.tabs.setStyleSheet(get_dark_tab_style() if theme == "dark" else get_light_tab_style())
        for installer in [self.wsl_feature_installer, self.wsl_distro_installer, self.conda_installer, self.cuda_installer, self.envvar_config]:
            if hasattr(installer, 'set_theme'):
                installer.set_theme(theme)

    def _setup_ui(self):
        self.setStyleSheet(get_deploy_panel_container_style(self.theme))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)



        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tabs.setStyleSheet(get_dark_tab_style() if self.theme == "dark" else get_light_tab_style())

        scroll1 = QScrollArea()
        scroll1.setObjectName("deployScrollArea")
        scroll1.setWidgetResizable(True)
        scroll1.setFrameShape(QFrame.Shape.NoFrame)
        scroll1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.wsl_feature_installer = WSLFeatureInstaller(theme=self.theme)
        scroll1.setWidget(self.wsl_feature_installer)
        self.tabs.addTab(scroll1, i18n.t("deploy_tab_wsl_feature"))

        scroll2 = QScrollArea()
        scroll2.setObjectName("deployScrollArea")
        scroll2.setWidgetResizable(True)
        scroll2.setFrameShape(QFrame.Shape.NoFrame)
        scroll2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.wsl_distro_installer = WSLDistroInstaller(theme=self.theme)
        scroll2.setWidget(self.wsl_distro_installer)
        self.tabs.addTab(scroll2, i18n.t("deploy_tab_wsl_distro"))

        scroll3 = QScrollArea()
        scroll3.setObjectName("deployScrollArea")
        scroll3.setWidgetResizable(True)
        scroll3.setFrameShape(QFrame.Shape.NoFrame)
        scroll3.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.conda_installer = CondaInstaller(wsl_config=self.wsl_config, theme=self.theme)
        scroll3.setWidget(self.conda_installer)
        self.tabs.addTab(scroll3, i18n.t("deploy_tab_conda"))

        scroll4 = QScrollArea()
        scroll4.setObjectName("deployScrollArea")
        scroll4.setWidgetResizable(True)
        scroll4.setFrameShape(QFrame.Shape.NoFrame)
        scroll4.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.cuda_installer = CudaInstaller(wsl_config=self.wsl_config, theme=self.theme)
        scroll4.setWidget(self.cuda_installer)
        self.tabs.addTab(scroll4, i18n.t("deploy_tab_cuda"))

        scroll5 = QScrollArea()
        scroll5.setObjectName("deployScrollArea")
        scroll5.setWidgetResizable(True)
        scroll5.setFrameShape(QFrame.Shape.NoFrame)
        scroll5.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.envvar_config = EnvVarConfig(wsl_config=self.wsl_config, theme=self.theme)
        scroll5.setWidget(self.envvar_config)
        self.tabs.addTab(scroll5, i18n.t("deploy_tab_envvar"))

        layout.addWidget(self.tabs, 1)

    def update_wsl_config(self, config: dict):
        self.wsl_config = config
        self.conda_installer.update_wsl_config(config)
        self.envvar_config.update_wsl_config(config)
        self.cuda_installer.update_wsl_config(config)
