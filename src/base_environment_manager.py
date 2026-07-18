import os
import uuid
import subprocess
import shlex
import shutil
import re
from typing import List
from datetime import datetime
from dataclasses import dataclass

from src.command_executor import CommandExecutor
from src.exceptions import (
    CommandExecutionError,
    EnvironmentCreationError,
    EnvironmentDeleteError,
)


@dataclass
class EnvironmentInfo:
    id: str
    name: str
    python_version: str
    location: str
    env_type: str
    packages: List[str]
    created_at: str
    size_mb: float
    tool: str = "venv"
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


CONDA_POSSIBLE_PATHS = [
    "~/miniconda3/bin/conda",
    "~/anaconda3/bin/conda",
    "~/miniconda/bin/conda",
    "~/anaconda/bin/conda",
    "/opt/conda/bin/conda",
    "/opt/miniconda3/bin/conda",
    "/opt/anaconda3/bin/conda",
    "/usr/local/miniconda3/bin/conda",
    "/usr/local/anaconda3/bin/conda",
]


class BaseEnvironmentManager:
    def __init__(self, executor: CommandExecutor):
        self.executor = executor
        self._conda_path = None

    def _quote_local_arg(self, value: str) -> str:
        """Quote arguments for the local Windows shell while preserving spaces."""
        value = os.path.normpath(os.path.expanduser(str(value)))
        if self.executor.get_environment_type() == "local" and os.name == "nt":
            return '"' + value.replace('"', '""') + '"'
        return shlex.quote(value)

    def _quote_token(self, value: str) -> str:
        """Quote a plain shell token such as an environment or package name."""
        value = str(value)
        if self.executor.get_environment_type() == "local" and os.name == "nt":
            return '"' + value.replace('"', '""') + '"'
        return shlex.quote(value)

    def _shell_path(self, path: str) -> str:
        """Render a path for shell execution, expanding user paths locally."""
        path = str(path)
        if self.executor.get_environment_type() == "local":
            if os.name == "nt":
                return self._quote_local_arg(path)
        if path == "~":
            return "~"
        if path.startswith("~/"):
            rest = path[2:]
            return f"~/{shlex.quote(rest)}" if rest else "~"
        return shlex.quote(path)

    def _find_conda_path(self) -> str:
        if self._conda_path:
            if self._conda_path != "conda":
                if self.executor.get_environment_type() == "local":
                    if os.path.exists(self._conda_path):
                        return self._conda_path
                else:
                    try:
                        exit_code, stdout, _ = self.executor.execute(
                            f"test -f {self._shell_path(self._conda_path)} && echo exists",
                            timeout=5,
                        )
                        if exit_code == 0 and "exists" in stdout:
                            return self._conda_path
                    except CommandExecutionError:
                        pass
            self._conda_path = None

        if self.executor.get_environment_type() == "local" and os.name == "nt":
            candidates = [
                os.environ.get("CONDA_EXE"),
                os.environ.get("MAMBA_EXE"),
            ]

            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ)
                try:
                    conda_root, _ = winreg.QueryValueEx(key, "CONDA_ROOT")
                    if conda_root:
                        candidates.append(os.path.join(conda_root, "Scripts", "conda.exe"))
                finally:
                    winreg.CloseKey(key)
            except Exception:
                pass

            prefix_candidates = [
                os.environ.get("CONDA_PREFIX"),
                os.environ.get("MAMBA_ROOT_PREFIX"),
                os.environ.get("CONDA_ROOT"),
            ]
            for prefix in prefix_candidates:
                if prefix:
                    candidates.extend(
                        [
                            os.path.join(prefix, "Scripts", "conda.exe"),
                            os.path.join(prefix, "Scripts", "conda.bat"),
                            os.path.join(prefix, "condabin", "conda.bat"),
                        ]
                    )

            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                candidates.extend(
                    [
                        os.path.join(user_profile, "miniconda3", "Scripts", "conda.exe"),
                        os.path.join(user_profile, "anaconda3", "Scripts", "conda.exe"),
                        os.path.join(user_profile, "miniconda3", "condabin", "conda.bat"),
                        os.path.join(user_profile, "anaconda3", "condabin", "conda.bat"),
                    ]
                )

            localappdata = os.environ.get("LOCALAPPDATA")
            if localappdata:
                candidates.extend(
                    [
                        os.path.join(localappdata, "miniconda3", "Scripts", "conda.exe"),
                        os.path.join(localappdata, "anaconda3", "Scripts", "conda.exe"),
                    ]
                )

            which_conda = shutil.which("conda")
            if which_conda and which_conda.lower().endswith((".bat", ".cmd")):
                sibling_exe = os.path.join(os.path.dirname(os.path.dirname(which_conda)), "Scripts", "conda.exe")
                if os.path.exists(sibling_exe):
                    which_conda = sibling_exe
            candidates.append(which_conda)
            for candidate in candidates:
                if candidate and os.path.exists(candidate):
                    self._conda_path = candidate
                    return candidate

        for path in CONDA_POSSIBLE_PATHS:
            try:
                expanded = path
                if path.startswith("~"):
                    exit_code, stdout, _ = self.executor.execute(f"echo {path}", timeout=5)
                    if exit_code == 0:
                        expanded = stdout.strip()

                exit_code, stdout, _ = self.executor.execute(
                    f"test -f {expanded} && echo exists", timeout=5
                )
                if exit_code == 0 and "exists" in stdout:
                    self._conda_path = expanded
                    return expanded
            except CommandExecutionError:
                continue

        try:
            exit_code, stdout, _ = self.executor.execute(
                "grep -E '^export CONDA_ROOT=' ~/.bashrc ~/.profile 2>/dev/null "
                "| tail -1 | sed -E 's/^export CONDA_ROOT=\"?([^\" ]+)\"?.*/\\1/'",
                timeout=5,
            )
            if exit_code == 0 and stdout.strip():
                conda_root = stdout.strip().splitlines()[-1]
                conda_path = f"{conda_root.rstrip('/')}/bin/conda"
                exit_code, check_out, _ = self.executor.execute(
                    f"test -f {self._shell_path(conda_path)} && echo exists",
                    timeout=5,
                )
                if exit_code == 0 and "exists" in check_out:
                    self._conda_path = conda_path
                    return conda_path
        except CommandExecutionError:
            pass

        try:
            exit_code, stdout, _ = self.executor.execute("which conda", timeout=5)
            if exit_code == 0 and stdout.strip():
                self._conda_path = stdout.strip()
                return self._conda_path
        except CommandExecutionError:
            pass

        try:
            exit_code, stdout, _ = self.executor.execute(
                "find ~ -name conda -type f -path '*/bin/conda' 2>/dev/null | head -1",
                timeout=10,
            )
            if exit_code == 0 and stdout.strip():
                self._conda_path = stdout.strip()
                return self._conda_path
        except CommandExecutionError:
            pass

        if self.executor.get_environment_type() == "local":
            self._conda_path = shutil.which("conda") or "conda"
            return self._conda_path

        self._conda_path = "conda"
        return "conda"

    def _get_python_version(self, env_path: str) -> str:
        if self.executor.get_environment_type() == 'local':
            if os.name == 'nt':
                python_paths = [
                    os.path.join(env_path, "Scripts", "python.exe"),
                    os.path.join(env_path, "python.exe"),
                    os.path.join(env_path, "bin", "python.exe"),
                    os.path.join(env_path, "bin", "python3.exe"),
                ]
            else:
                python_paths = [
                    os.path.join(env_path, "bin", "python"),
                    os.path.join(env_path, "bin", "python3"),
                    os.path.join(env_path, "python"),
                ]
            
            for python_path in python_paths:
                if os.path.exists(python_path):
                    try:
                        result = subprocess.run(
                            [python_path, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                        if result.returncode == 0:
                            version_output = result.stdout.strip() or result.stderr.strip()
                            return version_output.replace("Python ", "")
                    except Exception:
                        continue
        else:
            python_paths = [
                f"{env_path}/bin/python",
                f"{env_path}/bin/python3",
                f"{env_path}/python",
            ]
            
            for python_path in python_paths:
                try:
                    exit_code, stdout, stderr = self.executor.execute(
                        f"{self._shell_path(python_path)} --version", timeout=5
                    )
                    if exit_code == 0:
                        version_output = stdout.strip() or stderr.strip()
                        return version_output.replace("Python ", "")
                except CommandExecutionError:
                    continue
        return "Unknown"

    def _parse_conda_env_list(self, output: str) -> List[dict]:
        envs = []
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = re.match(r"^(?P<name>\S+)(?:\s+\*)?\s+(?P<path>.+)$", line)
            if not match:
                continue
            env_name = match.group("name").replace("*", "").strip()
            env_path = match.group("path").strip()
            envs.append({"name": env_name, "path": env_path})
        return envs

    def _list_conda_environments(self) -> List[EnvironmentInfo]:
        envs = []
        conda_path = self._find_conda_path()
        try:
            conda_cmd = self._shell_path(conda_path)
            exit_code, stdout, stderr = self.executor.execute(
                f"{conda_cmd} env list", timeout=30
            )
            if exit_code != 0:
                return envs

            parsed = self._parse_conda_env_list(stdout)
            for env_data in parsed:
                env_name = env_data["name"]
                env_path = env_data["path"]

                if self.executor.get_environment_type() == 'local':
                    if not os.path.exists(env_path):
                        continue

                python_version = self._get_python_version(env_path)
                packages = self._get_installed_packages(env_path, True, env_name)

                envs.append(
                    EnvironmentInfo(
                        id=str(uuid.uuid4()),
                        name=env_name,
                        python_version=python_version,
                        location=env_path,
                        env_type=self.executor.get_environment_type(),
                        packages=packages,
                        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        size_mb=0.0,
                        tool="conda",
                        metadata={"source": "conda_env_list"},
                    )
                )
        except CommandExecutionError:
            pass
        return envs

    def _list_venv_environments(self, location: str) -> List[EnvironmentInfo]:
        envs = []
        try:
            location_arg = self._shell_path(location)
            exit_code, stdout, _ = self.executor.execute(
                f"test -d {location_arg} && echo exists", timeout=5
            )
            if exit_code != 0 or "exists" not in stdout:
                return envs

            exit_code, stdout, _ = self.executor.execute(
                f"ls -1 {location_arg}", timeout=10
            )
            if exit_code != 0:
                return envs

            items = [line.strip() for line in stdout.splitlines() if line.strip()]

            for item in items:
                item_path = f"{location}/{item}".replace("\\", "/")
                item_arg = self._shell_path(item_path)

                exit_code, stdout, _ = self.executor.execute(
                    f"test -f {item_arg}/bin/python && echo venv", timeout=5
                )
                is_venv = exit_code == 0 and "venv" in stdout

                exit_code, stdout, _ = self.executor.execute(
                    f"test -d {item_arg}/conda-meta && echo conda", timeout=5
                )
                is_conda = exit_code == 0 and "conda" in stdout

                if is_venv or is_conda:
                    python_version = self._get_python_version(item_path)
                    packages = self._get_installed_packages(item_path, is_conda, item)

                    envs.append(
                        EnvironmentInfo(
                            id=str(uuid.uuid4()),
                            name=item,
                            python_version=python_version,
                            location=item_path,
                            env_type=self.executor.get_environment_type(),
                            packages=packages,
                            created_at="Unknown",
                            size_mb=0.0,
                            tool="conda" if is_conda else "venv",
                            metadata={"source": "directory_scan"},
                        )
                    )
        except CommandExecutionError:
            pass
        return envs

    def _get_installed_packages(self, env_path: str, use_conda: bool = False,
                                env_name: str = None) -> List[str]:
        try:
            if use_conda:
                conda_path = self._find_conda_path()
                if not env_name:
                    env_name = os.path.basename(env_path)
                conda_cmd = self._shell_path(conda_path)
                exit_code, stdout, _ = self.executor.execute(
                    f"{conda_cmd} list -n {self._quote_token(env_name)}", timeout=30
                )
                if exit_code != 0:
                    return []

                packages = []
                for line in stdout.splitlines():
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        packages.append(f"{parts[0]} {parts[1]}")
                return packages
            else:
                if self.executor.get_environment_type() == 'local':
                    if os.name == 'nt':
                        pip_path = os.path.join(env_path, "Scripts", "pip.exe")
                    else:
                        pip_path = os.path.join(env_path, "bin", "pip")
                else:
                    pip_path = f"{env_path}/bin/pip"

                exit_code, stdout, _ = self.executor.execute(
                    f"{self._shell_path(pip_path)} freeze", timeout=30
                )
                if exit_code != 0:
                    return []
                return stdout.splitlines()
        except CommandExecutionError:
            return []

    def list_environments(self, location: str = None) -> List[EnvironmentInfo]:
        envs = []
        conda_envs = self._list_conda_environments()
        envs.extend(conda_envs)

        if location:
            venv_envs = self._list_venv_environments(location)
            existing_paths = {env.location for env in envs}
            for venv_env in venv_envs:
                if venv_env.location not in existing_paths:
                    envs.append(venv_env)

        return envs

    def create_environment(self, name: str, python_version: str, location: str,
                           use_conda: bool = False, mirror_url: str = None) -> EnvironmentInfo:
        if use_conda:
            conda_path = self._find_conda_path()
            cmd = f"{self._shell_path(conda_path)} create -n {self._quote_token(name)} python={python_version} -y"
            if mirror_url:
                cmd += f" -c {self._quote_token(mirror_url)}"
            try:
                exit_code, stdout, stderr = self.executor.execute(cmd, timeout=300)
            except CommandExecutionError as e:
                raise EnvironmentCreationError(f"Failed to create conda environment: {e}")

            if exit_code != 0:
                raise EnvironmentCreationError(f"Failed to create conda environment: {stderr or stdout}")

            env_path = None
            list_cmd = f"{self._shell_path(conda_path)} env list"
            try:
                exit_code, stdout, _ = self.executor.execute(list_cmd, timeout=10)
                if exit_code == 0:
                    parsed = self._parse_conda_env_list(stdout)
                    for env_data in parsed:
                        if env_data["name"] == name:
                            env_path = env_data["path"]
                            break
            except CommandExecutionError:
                pass

            if not env_path:
                raise EnvironmentCreationError(
                    f"Failed to find conda environment path for: {name}"
                )

            actual_version = self._get_python_version(env_path)
            return EnvironmentInfo(
                id=str(uuid.uuid4()),
                name=name,
                python_version=actual_version or python_version,
                location=env_path,
                env_type=self.executor.get_environment_type(),
                packages=[],
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                size_mb=0.0,
                tool="conda",
                metadata={},
            )
        else:
            if self.executor.get_environment_type() == 'local':
                location = os.path.expanduser(location)
                if not os.path.exists(location):
                    os.makedirs(location)
                if os.name == 'nt':
                    cmd = f"py -{python_version} -m venv {self._shell_path(os.path.join(location, name))}"
                else:
                    cmd = f"python{python_version} -m venv {self._shell_path(os.path.join(location, name))}"
                try:
                    exit_code, stdout, stderr = self.executor.execute(cmd, timeout=120)
                except CommandExecutionError as e:
                    raise EnvironmentCreationError(f"Failed to create venv environment: {e}")
                if exit_code != 0:
                    raise EnvironmentCreationError(f"Failed to create venv: {stderr}")
                env_path = os.path.join(location, name)
            else:
                if location.startswith("~"):
                    try:
                        exit_code, stdout, _ = self.executor.execute(
                            f"printf '%s\\n' {self._shell_path(location)}", timeout=5
                        )
                        if exit_code == 0:
                            location = stdout.strip()
                    except CommandExecutionError:
                        pass

                env_path = f"{location}/{name}".replace("\\", "/")
                self.executor.execute(f"mkdir -p -- {self._shell_path(location)}", timeout=10)
                cmd = f"python{python_version} -m venv {self._shell_path(env_path)}"
                try:
                    exit_code, stdout, stderr = self.executor.execute(cmd, timeout=300)
                except CommandExecutionError as e:
                    raise EnvironmentCreationError(f"Failed to create venv environment: {e}")

                if exit_code != 0:
                    raise EnvironmentCreationError(f"Failed to create venv: {stderr or stdout}")

            actual_version = self._get_python_version(env_path)
            return EnvironmentInfo(
                id=str(uuid.uuid4()),
                name=name,
                python_version=actual_version or python_version,
                location=env_path,
                env_type=self.executor.get_environment_type(),
                packages=[],
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                size_mb=0.0,
                tool="venv",
                metadata={},
            )

    def delete_environment(self, env_path: str, use_conda: bool = False) -> bool:
        if use_conda:
            conda_path = self._find_conda_path()
            cmd = f"{self._shell_path(conda_path)} remove -p {self._shell_path(env_path)} --all -y"
            try:
                exit_code, stdout, stderr = self.executor.execute(cmd, timeout=120)
            except CommandExecutionError as e:
                raise EnvironmentDeleteError(f"Failed to delete conda environment: {e}")

            if exit_code != 0:
                try:
                    self.executor.execute(f"rm -rf -- {self._shell_path(env_path)}", timeout=60)
                except CommandExecutionError:
                    pass
        else:
            if self.executor.get_environment_type() == 'local':
                expanded = os.path.expanduser(env_path)
                if os.path.exists(expanded):
                    shutil.rmtree(expanded)
            else:
                try:
                    exit_code, stdout, stderr = self.executor.execute(
                        f"rm -rf -- {self._shell_path(env_path)}", timeout=60
                    )
                    if exit_code != 0:
                        raise EnvironmentDeleteError(f"Failed to delete environment: {stderr}")
                except CommandExecutionError as e:
                    raise EnvironmentDeleteError(f"Failed to delete environment: {e}")

        return True

    def install_package(self, env_name: str, env_path: str, package: str,
                        use_conda: bool = False, mirror_url: str = None) -> bool:
        if use_conda:
            conda_path = self._find_conda_path()
            cmd = f"{self._shell_path(conda_path)} install -n {self._quote_token(env_name)} {self._quote_token(package)} -y"
            if mirror_url:
                cmd += f" -c {self._quote_token(mirror_url)}"
            try:
                exit_code, stdout, stderr = self.executor.execute(cmd, timeout=120)
            except CommandExecutionError as e:
                raise EnvironmentCreationError(f"Install failed: {e}")
            if exit_code != 0:
                raise EnvironmentCreationError(f"Install failed: {stderr or stdout}")
        else:
            if self.executor.get_environment_type() == 'local':
                if os.name == 'nt':
                    pip_path = os.path.join(env_path, "Scripts", "pip.exe")
                else:
                    pip_path = os.path.join(env_path, "bin", "pip")
            else:
                pip_path = f"{env_path}/bin/pip"

            cmd = f"{self._shell_path(pip_path)} install {self._quote_token(package)}"
            if mirror_url:
                cmd += f" -i {self._quote_token(mirror_url)}"
            try:
                exit_code, stdout, stderr = self.executor.execute(cmd, timeout=120)
            except CommandExecutionError as e:
                raise EnvironmentCreationError(f"Install failed: {e}")
            if exit_code != 0:
                raise EnvironmentCreationError(f"Install failed: {stderr or stdout}")
        return True

    def uninstall_package(self, env_name: str, env_path: str, package: str,
                          use_conda: bool = False) -> bool:
        if use_conda:
            conda_path = self._find_conda_path()
            cmd = f"{self._shell_path(conda_path)} uninstall -n {self._quote_token(env_name)} {self._quote_token(package)} -y"
            try:
                exit_code, stdout, stderr = self.executor.execute(cmd, timeout=60)
            except CommandExecutionError as e:
                raise EnvironmentCreationError(f"Uninstall failed: {e}")
            if exit_code != 0:
                raise EnvironmentCreationError(f"Uninstall failed: {stderr or stdout}")
        else:
            if self.executor.get_environment_type() == 'local':
                if os.name == 'nt':
                    pip_path = os.path.join(env_path, "Scripts", "pip.exe")
                else:
                    pip_path = os.path.join(env_path, "bin", "pip")
            else:
                pip_path = f"{env_path}/bin/pip"

            cmd = f"{self._shell_path(pip_path)} uninstall {self._quote_token(package)} -y"
            try:
                exit_code, stdout, stderr = self.executor.execute(cmd, timeout=60)
            except CommandExecutionError as e:
                raise EnvironmentCreationError(f"Uninstall failed: {e}")
            if exit_code != 0:
                raise EnvironmentCreationError(f"Uninstall failed: {stderr or stdout}")
        return True

    def update_package(self, env_name: str, env_path: str, package: str,
                       use_conda: bool = False, mirror_url: str = None) -> bool:
        if use_conda:
            conda_path = self._find_conda_path()
            cmd = f"{self._shell_path(conda_path)} update -n {self._quote_token(env_name)} {self._quote_token(package)} -y"
            if mirror_url:
                cmd += f" -c {self._quote_token(mirror_url)}"
            try:
                exit_code, stdout, stderr = self.executor.execute(cmd, timeout=120)
            except CommandExecutionError as e:
                raise EnvironmentCreationError(f"Update failed: {e}")
            if exit_code != 0:
                raise EnvironmentCreationError(f"Update failed: {stderr or stdout}")
        else:
            if self.executor.get_environment_type() == 'local':
                if os.name == 'nt':
                    pip_path = os.path.join(env_path, "Scripts", "pip.exe")
                else:
                    pip_path = os.path.join(env_path, "bin", "pip")
            else:
                pip_path = f"{env_path}/bin/pip"

            cmd = f"{self._shell_path(pip_path)} install --upgrade {self._quote_token(package)}"
            if mirror_url:
                cmd += f" -i {self._quote_token(mirror_url)}"
            try:
                exit_code, stdout, stderr = self.executor.execute(cmd, timeout=120)
            except CommandExecutionError as e:
                raise EnvironmentCreationError(f"Update failed: {e}")
            if exit_code != 0:
                raise EnvironmentCreationError(f"Update failed: {stderr or stdout}")
        return True
