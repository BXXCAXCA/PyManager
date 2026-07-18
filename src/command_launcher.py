"""
统一命令生成组件 — CommandLauncher

将本地/WSL/远程三种环境的终端/Python/Jupyter启动命令生成逻辑
抽离为独立的 Builder 类，实现策略模式，统一通过
本地 cmd.exe 命令行启动系统终端。
"""
import os
import posixpath
import shlex
import subprocess
from abc import ABC, abstractmethod
from typing import Optional, Callable


def _cmd_exe() -> str:
    """返回 Windows cmd.exe 的可靠路径。"""
    return os.environ.get("ComSpec") or os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32",
        "cmd.exe",
    )


def _system_exe(name: str, *parts: str) -> str:
    """优先使用 System32 下的系统工具，避免 PATH 被沙箱或配置污染。"""
    if os.name != "nt":
        return name[:-4] if name.lower().endswith(".exe") else name
    candidate = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32",
        *parts,
        name,
    )
    return candidate if os.path.exists(candidate) else name


def _wsl_exe() -> str:
    return _system_exe("wsl.exe")


def _ssh_exe() -> str:
    return _system_exe("ssh.exe", "OpenSSH")


def _cmd_quote(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _cmd_preview(args: list[str]) -> str:
    if os.name == "nt":
        return f"{_cmd_exe()} /k {subprocess.list2cmdline(args)}"
    return " ".join(shlex.quote(str(part)) for part in args)


def _launch_args(args: list[str]) -> list[str]:
    if os.name == "nt":
        return [_cmd_exe(), "/k"] + args
    return args


def _posix_quote_path(path: str) -> str:
    """引用 Linux 路径，同时保留 ~/... 的 HOME 展开语义。"""
    path = str(path).strip()
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        rest = path[2:]
        return '"$HOME"' if not rest else f'"$HOME"/{shlex.quote(rest)}'
    return shlex.quote(path)


def _posix_join_path(base: str, suffix: str) -> str:
    return f"{str(base).rstrip('/')}/{suffix.lstrip('/')}"


def _posix_env_name(name: str) -> str:
    return shlex.quote(str(name))


def _conda_root_from_location(location: str, env_name: str) -> str:
    """根据 conda 环境路径推断 conda 根目录。"""
    path = os.path.normpath(str(location))
    envs_dir = os.path.basename(os.path.dirname(path)).lower()
    basename = os.path.basename(path).lower()
    if envs_dir == "envs" and basename == str(env_name).lower():
        return os.path.dirname(os.path.dirname(path))
    return path


def _conda_path_from_linux_env(location: str, env_name: str) -> Optional[str]:
    """从 Linux conda 环境路径推导 conda 可执行文件路径。"""
    location = str(location or "").strip()
    if not location or location == str(env_name):
        return None

    path = posixpath.normpath(location)
    envs_dir = posixpath.basename(posixpath.dirname(path)).lower()
    basename = posixpath.basename(path).lower()
    if envs_dir == "envs" and basename == str(env_name).lower():
        root = posixpath.dirname(posixpath.dirname(path))
    else:
        root = path
    return _posix_join_path(root, "bin/conda")


def _conda_activation_script(conda_path: str, env_name: str,
                             env_prefix: Optional[str] = None) -> str:
    """构建 bash 内可靠的 conda 激活脚本。"""
    conda_path = (conda_path or "conda").strip()
    env = _posix_quote_path(env_prefix) if env_prefix else _posix_env_name(env_name)

    if conda_path.endswith("/bin/conda"):
        conda_sh = conda_path[: -len("/bin/conda")] + "/etc/profile.d/conda.sh"
        return f". {_posix_quote_path(conda_sh)} && conda activate {env}"

    conda_cmd = _posix_quote_path(conda_path)
    return (
        f'eval "$({conda_cmd} shell.bash hook 2>/dev/null)" '
        f'|| {{ '
        f'[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ] && . "$HOME/miniconda3/etc/profile.d/conda.sh"; '
        f'}} '
        f'|| {{ '
        f'[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ] && . "$HOME/anaconda3/etc/profile.d/conda.sh"; '
        f'}} '
        f'&& conda activate {env}'
    )


def _keep_bash_open() -> str:
    return "exec bash --noprofile --norc -i"


def _prompt_script(env_name: str) -> str:
    prompt = f"({env_name}) \\u@\\h:\\w\\$ "
    return f"export PS1={shlex.quote(prompt)}"


class CommandBuilder(ABC):
    """命令构建器抽象基类"""

    @abstractmethod
    def build_terminal_command(self, env) -> Optional[str]:
        """构建打开终端的命令"""
        ...

    @abstractmethod
    def build_python_command(self, env) -> Optional[str]:
        """构建打开 Python 交互式解释器的命令"""
        ...

    @abstractmethod
    def build_jupyter_command(self, env) -> Optional[str]:
        """构建启动 Jupyter Notebook 的命令"""
        ...

    @abstractmethod
    def build_launch_args(self, env, command_type: str) -> Optional[list[str]]:
        """构建 subprocess.Popen 可直接使用的参数列表"""
        ...


class LocalCommandBuilder(CommandBuilder):
    """本地环境命令构建器

    生成 cmd.exe /k "激活命令" 格式，并通过 launch_args 走参数列表启动。
    非 Windows 平台回退到 gnome-terminal。
    """

    def _build_base_cmd(self, env) -> str:
        """构建本地环境的基础激活命令"""
        if env.tool == "conda":
            conda_root = _conda_root_from_location(env.location, env.name)
            activate_bat = os.path.join(conda_root, "Scripts", "activate.bat")
            if os.name == "nt":
                return f"call {_cmd_quote(activate_bat)} {_cmd_quote(env.location)}"
            return f'conda activate {shlex.quote(str(env.location))}'
        else:
            return f'call {_cmd_quote(os.path.join(env.location, "Scripts", "activate.bat"))}'

    def _build_base_parts(self, env) -> list[str]:
        """构建适用于 Windows cmd /k 的参数片段。

        这里不能把整条命令拼成一个字符串再交给 `cmd /k`，否则
        subprocess 的 Windows 转义会把内部双引号变成 `\"...\"`，
        最终导致 activate.bat 被当成普通可执行项而不是批处理命令。
        """
        if env.tool == "conda":
            conda_root = _conda_root_from_location(env.location, env.name)
            activate_bat = os.path.join(conda_root, "Scripts", "activate.bat")
            return ["call", activate_bat, env.location]
        return ["call", os.path.join(env.location, "Scripts", "activate.bat")]

    def _build_base_cmd_linux(self, env) -> str:
        """构建 Linux/Mac 本地环境的基础激活命令"""
        if env.tool == "conda":
            return f'conda activate {shlex.quote(str(env.location))}'
        else:
            return f'source {os.path.join(env.location, "bin", "activate")}'

    def build_terminal_command(self, env) -> Optional[str]:
        base_cmd = self._build_base_cmd(env)
        if os.name == 'nt':
            return _cmd_preview([base_cmd])
        else:
            base_cmd_linux = self._build_base_cmd_linux(env)
            return f'gnome-terminal -- bash -c "{base_cmd_linux}; exec bash"'

    def build_python_command(self, env) -> Optional[str]:
        base_cmd = self._build_base_cmd(env)
        if os.name == 'nt':
            return _cmd_preview([f"{base_cmd} && python"])
        else:
            base_cmd_linux = self._build_base_cmd_linux(env)
            return f'gnome-terminal -- bash -c "{base_cmd_linux}; python; exec bash"'

    def build_jupyter_command(self, env) -> Optional[str]:
        base_cmd = self._build_base_cmd(env)
        if os.name == 'nt':
            return _cmd_preview([f"{base_cmd} && jupyter notebook"])
        else:
            base_cmd_linux = self._build_base_cmd_linux(env)
            return f'gnome-terminal -- bash -c "{base_cmd_linux}; jupyter notebook"'

    def build_launch_args(self, env, command_type: str) -> Optional[list[str]]:
        if os.name != "nt":
            command = {
                "terminal": self.build_terminal_command,
                "python": self.build_python_command,
                "jupyter": self.build_jupyter_command,
            }.get(command_type)
            return None if not command else [command(env)]

        parts = self._build_base_parts(env)
        if command_type == "terminal":
            inner_parts = parts
        elif command_type == "python":
            inner_parts = parts + ["&&", "python"]
        elif command_type == "jupyter":
            inner_parts = parts + ["&&", "jupyter", "notebook"]
        else:
            return None
        return _launch_args(inner_parts)


class WSLCommandBuilder(CommandBuilder):
    """WSL 环境命令构建器

    在 Windows cmd 中通过 wsl 命令进入 WSL 子系统执行激活命令，
    统一通过 cmd.exe /k 在独立 cmd 窗口中运行。
    """

    def __init__(self, distro_name: Optional[str] = None,
                 username: Optional[str] = None,
                 conda_path_finder: Optional[Callable[[], str]] = None):
        self.distro_name = distro_name
        self.username = username
        self.conda_path_finder = conda_path_finder

    def _build_wsl_prefix(self) -> str:
        """构建 WSL 命令前缀，格式 wsl [-d distro] [-u user]"""
        parts = [_wsl_exe()]
        if self.distro_name:
            parts.extend(["-d", self.distro_name])
        if self.username:
            parts.extend(["-u", self.username])
        return subprocess.list2cmdline(parts) if os.name == "nt" else " ".join(shlex.quote(str(p)) for p in parts)

    def _build_wsl_args(self) -> list[str]:
        parts = [_wsl_exe()]
        if self.distro_name:
            parts.extend(["-d", self.distro_name])
        if self.username:
            parts.extend(["-u", self.username])
        return parts

    def _build_activation_cmd(self, env) -> str:
        """构建 WSL 内的激活命令"""
        if env.tool == "conda":
            conda_path = _conda_path_from_linux_env(env.location, env.name)
            if not conda_path and self.conda_path_finder:
                conda_path = self.conda_path_finder()
            if not conda_path:
                conda_path = "conda"
            return _conda_activation_script(conda_path, env.name, env.location)
        else:
            activate_path = _posix_join_path(env.location, "bin/activate")
            return f'. {_posix_quote_path(activate_path)}'

    def _build_bash_script(self, env, command_type: str) -> Optional[str]:
        activation = self._build_activation_cmd(env)
        prompt = _prompt_script(env.name)
        if command_type == "terminal":
            return f"{activation}; {prompt}; {_keep_bash_open()}"
        if command_type == "python":
            return f"{activation} && python; {prompt}; {_keep_bash_open()}"
        if command_type == "jupyter":
            return f"{activation} && jupyter notebook; {prompt}; {_keep_bash_open()}"
        return None

    def _build_wsl_launch_payload(self, env, command_type: str) -> Optional[list[str]]:
        script = self._build_bash_script(env, command_type)
        if not script:
            return None
        return self._build_wsl_args() + ["--", "bash", "-lc", script]

    def build_terminal_command(self, env) -> Optional[str]:
        if os.name == 'nt':
            args = self._build_wsl_launch_payload(env, "terminal")
            return None if not args else _cmd_preview(args)
        else:
            wsl_prefix = self._build_wsl_prefix()
            activation = self._build_activation_cmd(env)
            return f'gnome-terminal -- bash -c "{wsl_prefix} -- bash -c \\"{activation}; exec bash\\""'

    def build_python_command(self, env) -> Optional[str]:
        if os.name == 'nt':
            args = self._build_wsl_launch_payload(env, "python")
            return None if not args else _cmd_preview(args)
        else:
            wsl_prefix = self._build_wsl_prefix()
            activation = self._build_activation_cmd(env)
            return f'gnome-terminal -- bash -c "{wsl_prefix} -- bash -c \\"{activation} && python3; exec bash\\""'

    def build_jupyter_command(self, env) -> Optional[str]:
        if os.name == 'nt':
            args = self._build_wsl_launch_payload(env, "jupyter")
            return None if not args else _cmd_preview(args)
        else:
            wsl_prefix = self._build_wsl_prefix()
            activation = self._build_activation_cmd(env)
            return f'gnome-terminal -- bash -c "{wsl_prefix} -- bash -c \\"{activation} && jupyter notebook\\""'

    def build_launch_args(self, env, command_type: str) -> Optional[list[str]]:
        if os.name != "nt":
            command = {
                "terminal": self.build_terminal_command,
                "python": self.build_python_command,
                "jupyter": self.build_jupyter_command,
            }.get(command_type)
            return None if not command else [command(env)]
        args = self._build_wsl_launch_payload(env, command_type)
        return None if not args else _launch_args(args)

    def update_config(self, distro_name: Optional[str] = None,
                      username: Optional[str] = None,
                      conda_path_finder: Optional[Callable[[], str]] = None):
        """动态更新 WSL 配置（WSL 配置变更时调用）"""
        if distro_name is not None:
            self.distro_name = distro_name
        if username is not None:
            self.username = username
        if conda_path_finder is not None:
            self.conda_path_finder = conda_path_finder


class RemoteCommandBuilder(CommandBuilder):
    """远程环境命令构建器

    在 Windows cmd 中通过 ssh 命令建立交互式远程会话，
    取代原有的 RemoteTerminalPanel 内嵌对话框方式。
    """

    def __init__(self, ssh_connected_checker: Optional[Callable[[], bool]] = None,
                 ssh_info_provider: Optional[Callable[[], Optional[tuple]]] = None,
                 conda_path_finder: Optional[Callable[[], str]] = None):
        """
        Args:
            ssh_connected_checker: 返回 SSH 是否已连接的回调函数
            ssh_info_provider: 返回 (host, port, username) 元组的回调函数
        """
        self.ssh_connected_checker = ssh_connected_checker
        self.ssh_info_provider = ssh_info_provider
        self.conda_path_finder = conda_path_finder

    def _check_prerequisite(self) -> bool:
        """前置检查 SSH 是否已连接"""
        if self.ssh_connected_checker:
            return self.ssh_connected_checker()
        return False

    def _build_ssh_prefix(self, allocate_tty: bool = False) -> Optional[str]:
        """构建 SSH 命令前缀，格式 ssh [-p port] user@host"""
        if not self.ssh_info_provider:
            return None
        info = self.ssh_info_provider()
        if not info:
            return None
        host, port, username = info
        ssh_prefix = _ssh_exe()
        if port and port != 22:
            ssh_prefix += f" -p {port}"
        if allocate_tty:
            ssh_prefix += " -t"
        ssh_prefix += f" {username}@{host}"
        return ssh_prefix

    def _build_ssh_args(self, allocate_tty: bool = False) -> Optional[list[str]]:
        if not self.ssh_info_provider:
            return None
        info = self.ssh_info_provider()
        if not info:
            return None
        host, port, username = info
        args = [_ssh_exe()]
        if port and port != 22:
            args.extend(["-p", str(port)])
        if allocate_tty:
            args.append("-t")
        args.append(f"{username}@{host}")
        return args

    def _build_activation_cmd(self, env) -> str:
        """构建远程环境激活命令"""
        if env.tool == "conda":
            # conda activate 是 shell 函数，需先初始化 conda hook
            conda_path = _conda_path_from_linux_env(env.location, env.name)
            if not conda_path and self.conda_path_finder:
                try:
                    conda_path = self.conda_path_finder()
                except Exception:
                    conda_path = "conda"
            if not conda_path:
                conda_path = "conda"
            return _conda_activation_script(conda_path, env.name, env.location)
        else:
            activate_path = _posix_join_path(env.location, "bin/activate")
            return f'. {_posix_quote_path(activate_path)}'

    def _build_remote_script(self, env, command_type: str) -> Optional[str]:
        activation = self._build_activation_cmd(env)
        prompt = _prompt_script(env.name)
        if command_type == "terminal":
            return f"{activation}; {prompt}; {_keep_bash_open()}"
        if command_type == "python":
            return f"{activation} && python; {prompt}; {_keep_bash_open()}"
        if command_type == "jupyter":
            return f"{activation} && jupyter notebook; {prompt}; {_keep_bash_open()}"
        return None

    def _build_remote_launch_payload(self, env, command_type: str) -> Optional[list[str]]:
        if not self._check_prerequisite():
            return None
        ssh_args = self._build_ssh_args(allocate_tty=True)
        if not ssh_args:
            return None
        script = self._build_remote_script(env, command_type)
        if not script:
            return None
        return ssh_args + [f"bash -lc {shlex.quote(script)}"]

    def build_terminal_command(self, env) -> Optional[str]:
        if os.name == 'nt':
            args = self._build_remote_launch_payload(env, "terminal")
            return None if not args else _cmd_preview(args)
        else:
            ssh_prefix = self._build_ssh_prefix(allocate_tty=True)
            activation = self._build_activation_cmd(env)
            remote_cmd = f'{activation} && exec bash -l'
            return f'gnome-terminal -- bash -c \'{ssh_prefix} "{remote_cmd}"\''

    def build_python_command(self, env) -> Optional[str]:
        if os.name == 'nt':
            args = self._build_remote_launch_payload(env, "python")
            return None if not args else _cmd_preview(args)
        else:
            ssh_prefix = self._build_ssh_prefix(allocate_tty=True)
            activation = self._build_activation_cmd(env)
            remote_cmd = f'{activation} && python3; exec bash -l'
            return f'gnome-terminal -- bash -c \'{ssh_prefix} "{remote_cmd}"\''

    def build_jupyter_command(self, env) -> Optional[str]:
        if os.name == 'nt':
            args = self._build_remote_launch_payload(env, "jupyter")
            return None if not args else _cmd_preview(args)
        else:
            ssh_prefix = self._build_ssh_prefix(allocate_tty=True)
            activation = self._build_activation_cmd(env)
            remote_cmd = f'{activation} && jupyter notebook; exec bash -l'
            return f'gnome-terminal -- bash -c \'{ssh_prefix} "{remote_cmd}"\''

    def update_config(self, ssh_connected_checker: Optional[Callable[[], bool]] = None,
                      ssh_info_provider: Optional[Callable[[], tuple]] = None,
                      conda_path_finder: Optional[Callable[[], str]] = None):
        """动态更新 SSH 配置（连接状态变更时调用）"""
        if ssh_connected_checker is not None:
            self.ssh_connected_checker = ssh_connected_checker
        if ssh_info_provider is not None:
            self.ssh_info_provider = ssh_info_provider
        if conda_path_finder is not None:
            self.conda_path_finder = conda_path_finder

    def build_launch_args(self, env, command_type: str) -> Optional[list[str]]:
        if os.name != "nt":
            command = {
                "terminal": self.build_terminal_command,
                "python": self.build_python_command,
                "jupyter": self.build_jupyter_command,
            }.get(command_type)
            return None if not command else [command(env)]
        args = self._build_remote_launch_payload(env, command_type)
        return None if not args else _launch_args(args)


class CommandLauncher:
    """统一命令生成入口

    根据环境类型分发到对应 Builder 的 build 方法，
    可生成展示用命令字符串，也可生成 subprocess.Popen 参数列表。
    """

    def __init__(self):
        self._builders: dict = {}

    def register_builder(self, env_type: str, builder: CommandBuilder) -> None:
        """注册指定环境类型的命令构建器"""
        self._builders[env_type] = builder

    def get_builder(self, env_type: str) -> Optional[CommandBuilder]:
        """获取指定环境类型的构建器"""
        return self._builders.get(env_type)

    def generate_command(self, env, env_type: str,
                         command_type: str) -> Optional[str]:
        """
        统一命令生成入口

        Args:
            env: EnvironmentInfo 环境信息对象
            env_type: 环境类型 ("local" / "wsl" / "remote")
            command_type: 命令类型 ("terminal" / "python" / "jupyter")

        Returns:
            可执行命令字符串，或 None（未注册 builder / 前置检查不通过）
        """
        builder = self._builders.get(env_type)
        if not builder:
            return None

        if command_type == "terminal":
            return builder.build_terminal_command(env)
        elif command_type == "python":
            return builder.build_python_command(env)
        elif command_type == "jupyter":
            return builder.build_jupyter_command(env)

        return None

    def generate_launch_args(self, env, env_type: str,
                             command_type: str) -> Optional[list[str]]:
        """生成 subprocess.Popen 参数，Windows 下统一打开本地 cmd.exe。"""
        builder = self._builders.get(env_type)
        if not builder:
            return None
        return builder.build_launch_args(env, command_type)

    def launch(self, env, env_type: str, command_type: str):
        """启动终端命令。返回 Popen 对象；失败时返回 None。"""
        args = self.generate_launch_args(env, env_type, command_type)
        if not args:
            return None

        if os.name == "nt":
            return subprocess.Popen(
                args,
                shell=False,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )

        command = args[0] if len(args) == 1 else " ".join(shlex.quote(str(a)) for a in args)
        return subprocess.Popen(command, shell=True)
