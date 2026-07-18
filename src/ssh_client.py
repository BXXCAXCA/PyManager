import paramiko
import logging
import shlex
from typing import Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime
from stat import S_ISDIR, filemode


logger = logging.getLogger(__name__)


@dataclass
class SSHConnection:
    host: str
    port: int
    username: str
    password: Optional[str] = None
    key_path: Optional[str] = None


@dataclass
class RemoteFile:
    path: str
    name: str
    size: int
    is_directory: bool
    permissions: str
    modified_time: str


class SSHClient:
    def __init__(self):
        self.client: Optional[paramiko.SSHClient] = None
        self.sftp: Optional[paramiko.SFTPClient] = None
        self.connection: Optional[SSHConnection] = None

    def connect(
        self,
        connection: SSHConnection,
        timeout: int = 10,
        banner_timeout: int = 10,
        auth_timeout: int = 10,
    ) -> bool:
        """建立 SSH 连接"""
        self.disconnect()
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            has_explicit_auth = bool(connection.password or connection.key_path)
            self.client.connect(
                hostname=connection.host,
                port=connection.port,
                username=connection.username,
                password=connection.password,
                key_filename=connection.key_path,
                banner_timeout=banner_timeout,
                timeout=timeout,
                auth_timeout=auth_timeout,
                look_for_keys=not has_explicit_auth,
                allow_agent=not has_explicit_auth,
            )
            self.sftp = self.client.open_sftp()
            self.connection = connection
            return True
        except Exception as e:
            self.client = None
            self.sftp = None
            self.connection = None
            logger.debug("SSH connection failed to %s:%s as %s: %s", connection.host, connection.port, connection.username, e)
            return False

    def disconnect(self) -> None:
        """断开连接"""
        if self.sftp:
            self.sftp.close()
            self.sftp = None
        if self.client:
            self.client.close()
            self.client = None
        self.connection = None

    def execute_command(self, command: str, timeout: int = 30, input_data: Optional[str] = None) -> Tuple[str, str, int]:
        if not self.client:
            return "", "Not connected", 1

        escaped_command = command.replace("'", "'\"'\"'")
        wrapped_command = f"bash -l -c '{escaped_command}'"

        stdin, stdout, stderr = self.client.exec_command(wrapped_command, timeout=timeout)
        
        if input_data:
            if isinstance(input_data, str):
                stdin.write(input_data.encode('utf-8'))
            else:
                stdin.write(input_data)
            stdin.flush()
            stdin.channel.shutdown_write()

        stdout_text = stdout.read().decode('utf-8', errors='ignore')
        stderr_text = stderr.read().decode('utf-8', errors='ignore')
        exit_status = stdout.channel.recv_exit_status()

        return (stdout_text, stderr_text, exit_status)

    def _quote_remote_path(self, path: str) -> str:
        path = str(path or "").strip()
        if path == "~":
            return "~"
        if path.startswith("~/"):
            rest = path[2:]
            return f"~/{shlex.quote(rest)}" if rest else "~"
        return shlex.quote(path)

    def _expand_remote_path(self, path: str) -> str:
        if path.startswith("~"):
            stdout, _, exit_code = self.execute_command(
                f"printf '%s\\n' {self._quote_remote_path(path)}",
                timeout=5,
            )
            if exit_code == 0 and stdout.strip():
                return stdout.strip()
        return path

    def list_directory(self, path: str) -> List[RemoteFile]:
        if not self.sftp:
            return []
        try:
            path = self._expand_remote_path(path)
            files = []
            for attr in self.sftp.listdir_attr(path):
                mode = attr.st_mode or 0
                modified = ""
                if attr.st_mtime:
                    modified = datetime.fromtimestamp(attr.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                if path in ("", "."):
                    item_path = f"./{attr.filename}"
                elif path == "/":
                    item_path = f"/{attr.filename}"
                else:
                    item_path = f"{path.rstrip('/')}/{attr.filename}"
                files.append(
                    RemoteFile(
                        path=item_path,
                        name=attr.filename,
                        size=attr.st_size if attr.st_size is not None else 0,
                        is_directory=S_ISDIR(mode),
                        permissions=filemode(mode),
                        modified_time=modified,
                    )
                )
            return files
        except FileNotFoundError:
            return []
        except Exception as exc:
            logger.debug("Failed to list remote directory %s: %s", path, exc)
            return []

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """上传文件"""
        if not self.sftp:
            return False
        try:
            remote_path = self._expand_remote_path(remote_path)
            self.sftp.put(local_path, remote_path)
            return True
        except Exception as exc:
            logger.debug("Failed to upload %s to %s: %s", local_path, remote_path, exc)
            return False

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """下载文件"""
        if not self.sftp:
            return False
        try:
            remote_path = self._expand_remote_path(remote_path)
            self.sftp.get(remote_path, local_path)
            return True
        except Exception as exc:
            logger.debug("Failed to download %s to %s: %s", remote_path, local_path, exc)
            return False
