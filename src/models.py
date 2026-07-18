from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum


class EnvType(str, Enum):
    LOCAL = "local"
    WSL = "wsl"
    REMOTE = "remote"


class ToolType(str, Enum):
    VENV = "venv"
    CONDA = "conda"


@dataclass
class EnvironmentConfig:
    id: str
    name: str
    python_version: str
    location: str
    env_type: EnvType  # 'local', 'wsl', 'remote'
    tool: ToolType  # 'venv', 'conda'
    packages: List[str] = field(default_factory=list)
    pip_mirror: Optional[str] = None
    conda_mirror: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_modified: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "python_version": self.python_version,
            "location": self.location,
            "env_type": self.env_type.value,
            "tool": self.tool.value,
            "packages": self.packages,
            "pip_mirror": self.pip_mirror,
            "conda_mirror": self.conda_mirror,
            "created_at": self.created_at.isoformat(),
            "last_modified": self.last_modified.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "EnvironmentConfig":
        """从字典创建"""
        data["env_type"] = EnvType(data["env_type"])
        data["tool"] = ToolType(data["tool"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["last_modified"] = datetime.fromisoformat(data["last_modified"])
        return cls(**data)


@dataclass
class RemoteServerConfig:
    id: str
    name: str
    host: str
    username: str
    auth_type: str  # 'password', 'key'
    port: int = 22
    password: Optional[str] = None
    key_path: Optional[str] = None
    default_python_path: str = "/usr/bin/python3"
    default_env_location: str = "~/python_envs"

    def to_dict(self) -> Dict:
        """转换为字典"""
        return self.__dict__

    @classmethod
    def from_dict(cls, data: Dict) -> "RemoteServerConfig":
        """从字典创建"""
        return cls(**data)

@dataclass
class WSLConfig:
    """WSL配置"""
    distro_name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "distro_name": self.distro_name,
            "username": self.username,
            "password": self.password,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WSLConfig":
        """从字典创建"""
        return cls(**data)
