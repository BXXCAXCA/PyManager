from abc import ABC, abstractmethod
import subprocess
import os
import shlex
from typing import Tuple, Optional

from src.exceptions import CommandExecutionError


def _quote_posix_path(path: str) -> str:
    path = str(path).strip()
    if path == "~":
        return "~"
    if path.startswith("~/"):
        rest = path[2:]
        return f"~/{shlex.quote(rest)}" if rest else "~"
    return shlex.quote(path)


class CommandExecutor(ABC):
    @abstractmethod
    def execute(self, command: str, cwd: Optional[str] = None,
                env: Optional[dict] = None, timeout: int = 60) -> Tuple[int, str, str]:
        pass

    @abstractmethod
    def get_environment_type(self) -> str:
        pass

    def execute_check(self, command: str, cwd: Optional[str] = None,
                      env: Optional[dict] = None, timeout: int = 60) -> Tuple[int, str, str]:
        return self.execute(command, cwd, env, timeout)


class LocalCommandExecutor(CommandExecutor):
    def execute(self, command: str, cwd: Optional[str] = None,
                env: Optional[dict] = None, timeout: int = 60) -> Tuple[int, str, str]:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            raise CommandExecutionError(
                f"Command timed out after {timeout}s: {command}"
            )
        except Exception as e:
            raise CommandExecutionError(f"Command execution failed: {e}")

    def get_environment_type(self) -> str:
        return 'local'


class WSLCommandExecutor(CommandExecutor):
    def __init__(self, distro: Optional[str] = None, user: Optional[str] = None,
                 password: Optional[str] = None):
        self.distro = distro
        self.user = user
        self.password = password

    def _build_wsl_prefix(self) -> list:
        cmd = ["wsl"]
        if self.distro:
            cmd.extend(["-d", self.distro])
        if self.user:
            cmd.extend(["-u", self.user])
        cmd.append("--")
        return cmd

    def execute(self, command: str, cwd: Optional[str] = None,
                env: Optional[dict] = None, timeout: int = 60) -> Tuple[int, str, str]:
        try:
            wsl_prefix = self._build_wsl_prefix()
            shell_command = command
            if cwd:
                shell_command = f"cd -- {_quote_posix_path(cwd)} && {command}"
            full_cmd = wsl_prefix + ["bash", "-c", shell_command]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            result = subprocess.run(
                full_cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                timeout=timeout,
                creationflags=creationflags,
            )
            stdout = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
            stderr = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ""
            return result.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            raise CommandExecutionError(
                f"WSL command timed out after {timeout}s: {command}"
            )
        except Exception as e:
            raise CommandExecutionError(f"WSL command execution failed: {e}")

    def execute_sudo(self, command: str, timeout: int = 60) -> Tuple[int, str, str]:
        if self.password:
            sudo_cmd = (
                f"printf '%s\\n' {shlex.quote(self.password)} "
                f"| sudo -S -p '' bash -lc {shlex.quote(command)}"
            )
        else:
            sudo_cmd = f"sudo bash -lc {shlex.quote(command)}"
        return self.execute(sudo_cmd, timeout=timeout)

    def get_environment_type(self) -> str:
        return 'wsl'


class RemoteCommandExecutor(CommandExecutor):
    def __init__(self, ssh_client):
        self.ssh_client = ssh_client

    def execute(self, command: str, cwd: Optional[str] = None,
                env: Optional[dict] = None, timeout: int = 30,
                input_data: Optional[str] = None) -> Tuple[int, str, str]:
        if not self.ssh_client or not self.ssh_client.client:
            raise CommandExecutionError("SSH client not connected")

        full_command = command
        if cwd:
            full_command = f"cd -- {_quote_posix_path(cwd)} && {command}"

        try:
            stdout, stderr, exit_code = self.ssh_client.execute_command(
                full_command, timeout=timeout, input_data=input_data
            )
            return exit_code, stdout, stderr
        except CommandExecutionError:
            raise
        except Exception as e:
            raise CommandExecutionError(f"Remote command execution failed: {str(e)}")

    def get_environment_type(self) -> str:
        return 'remote'
