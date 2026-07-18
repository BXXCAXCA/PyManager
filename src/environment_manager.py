from typing import List
from src.command_executor import (
    LocalCommandExecutor,
    WSLCommandExecutor,
    RemoteCommandExecutor,
)
from src.base_environment_manager import BaseEnvironmentManager, EnvironmentInfo
from src.ssh_client import SSHClient
import subprocess
import os
import uuid


class LocalEnvironmentManager(BaseEnvironmentManager):
    def __init__(self):
        executor = LocalCommandExecutor()
        super().__init__(executor)

    def list_environments(self, location: str = None) -> List[EnvironmentInfo]:
        envs = []
        conda_envs = self._list_conda_environments()
        envs.extend(conda_envs)

        if location and os.path.exists(location):
            for item in os.listdir(location):
                item_path = os.path.join(location, item)
                if os.path.isdir(item_path):
                    existing_paths = {env.location for env in envs}
                    if item_path in existing_paths:
                        continue

                    is_env = False
                    is_conda = False
                    if os.path.exists(
                        os.path.join(item_path, "bin", "python")
                    ) or os.path.exists(
                        os.path.join(item_path, "Scripts", "python.exe")
                    ):
                        is_env = True
                    elif os.path.exists(os.path.join(item_path, "conda-meta")):
                        is_env = True
                        is_conda = True

                    if is_env:
                        packages = self._get_installed_packages(item_path, is_conda, item)
                        python_version = self._get_python_version(item_path)
                        envs.append(
                            EnvironmentInfo(
                                id=str(uuid.uuid4()),
                                name=item,
                                python_version=python_version,
                                location=item_path,
                                env_type="local",
                                packages=packages,
                                created_at="Unknown",
                                size_mb=0.0,
                                tool="conda" if is_conda else "venv",
                                metadata={},
                            )
                        )

        return envs


class WSLEnvironmentManager(BaseEnvironmentManager):
    def __init__(self, distro_name: str = None, username: str = None,
                 password: str = None):
        executor = WSLCommandExecutor(distro=distro_name, user=username,
                                      password=password)
        super().__init__(executor)
        self.distro_name = distro_name
        self.username = username
        self.password = password

    def _build_wsl_command(self, command: list, use_sudo: bool = False) -> list:
        if use_sudo and self.password:
            sudo_cmd = f"echo '{self.password}' | sudo -S"
            command = ["bash", "-c", f"{sudo_cmd} {' '.join(command)}"]

        if self.distro_name:
            if self.username:
                return ["wsl", "-d", self.distro_name, "-u", self.username, "--"] + command
            else:
                return ["wsl", "-d", self.distro_name, "--"] + command
        else:
            if self.username:
                return ["wsl", "-u", self.username, "--"] + command
            else:
                return ["wsl", "--"] + command

    @staticmethod
    def list_wsl_distributions() -> List[str]:
        try:
            check_result = subprocess.run(
                ["wsl", "--status"],
                capture_output=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if check_result.returncode != 0:
                return []

            result = subprocess.run(
                ["wsl", "--list", "--quiet"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                output = None
                for encoding in ['utf-16-le', 'utf-16', 'utf-8', 'gbk']:
                    try:
                        output = result.stdout.decode(encoding)
                        break
                    except Exception:
                        continue
                if output:
                    distros = [line.strip() for line in output.splitlines() if line.strip()]
                    distros = [d.replace('\x00', '').replace('\ufeff', '').replace('*', '').strip()
                               for d in distros]
                    return [d for d in distros if d and not d.startswith('Windows')]
            return []
        except subprocess.TimeoutExpired:
            return []
        except FileNotFoundError:
            return []
        except Exception:
            return []


class RemoteEnvironmentManager(BaseEnvironmentManager):
    def __init__(self, ssh_client: SSHClient):
        executor = RemoteCommandExecutor(ssh_client)
        super().__init__(executor)
        self.ssh_client = ssh_client
