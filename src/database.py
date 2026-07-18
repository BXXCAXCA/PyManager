from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    JSON,
    Boolean,
    func,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from contextlib import contextmanager
import os
import shutil
import sys
from pathlib import Path
from src.models import RemoteServerConfig

Base = declarative_base()


CONFIG_DIR_ENV = "PYMANAGER_CONFIG_DIR"
DEFAULT_CONFIG_DIR = Path(r"C:\PyManagerConfig")
APP_DB_NAME = "app.db"


def get_config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return DEFAULT_CONFIG_DIR


def get_default_db_path() -> Path:
    return get_config_dir() / APP_DB_NAME


def get_default_db_uri() -> str:
    return "sqlite:///" + get_default_db_path().as_posix()


def _legacy_db_candidates() -> list[Path]:
    candidates = [
        Path.cwd() / "config" / APP_DB_NAME,
        Path(__file__).resolve().parent.parent / "config" / APP_DB_NAME,
    ]
    executable = getattr(sys, "executable", None)
    if executable:
        candidates.append(Path(executable).resolve().parent / "config" / APP_DB_NAME)

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            unique_candidates.append(resolved)
    return unique_candidates


def _sqlite_uri_to_path(db_uri: str) -> Path | None:
    prefix = "sqlite:///"
    if not db_uri.startswith(prefix) or db_uri == "sqlite:///:memory:":
        return None
    return Path(db_uri[len(prefix):])


def _migrate_legacy_default_db(target_path: Path):
    if target_path.exists():
        return

    for legacy_path in _legacy_db_candidates():
        if legacy_path == target_path or not legacy_path.exists():
            continue
        shutil.copy2(legacy_path, target_path)
        return


class EnvironmentModel(Base):
    __tablename__ = "environments"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, index=True)
    python_version = Column(String, nullable=False)
    location = Column(String, nullable=False)
    env_type = Column(String, nullable=False, index=True)
    tool = Column(String, nullable=False)
    packages = Column(JSON, default=list)
    pip_mirror = Column(String, nullable=True)
    conda_mirror = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    last_modified = Column(DateTime, default=func.now(), onupdate=func.now())
    metadata_json = Column(JSON, default=dict)


class RemoteServerModel(Base):
    __tablename__ = "servers"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    host = Column(String, nullable=False)
    port = Column(Integer, default=22)
    username = Column(String, nullable=False)
    auth_type = Column(String, nullable=False)
    password = Column(String, nullable=True)
    key_path = Column(String, nullable=True)
    default_python_path = Column(String, default="/usr/bin/python3")
    default_env_location = Column(String, default="~/python_envs")


class MirrorModel(Base):
    __tablename__ = "mirrors"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=False)
    mirror_type = Column(String, nullable=False)
    is_default = Column(Boolean, default=False)


class WSLConfigModel(Base):
    __tablename__ = "wsl_config"
    id = Column(Integer, primary_key=True, autoincrement=True)
    distro_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class AppSettingModel(Base):
    __tablename__ = "app_settings"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class DatabaseManager:
    def __init__(self, db_path=None):
        db_path = db_path or get_default_db_uri()
        sqlite_path = _sqlite_uri_to_path(db_path)
        db_dir = sqlite_path.parent if sqlite_path else Path(db_path.replace("sqlite:///", "")).parent
        if db_dir and str(db_dir) != "." and not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)

        if db_path == get_default_db_uri() and sqlite_path is not None:
            _migrate_legacy_default_db(sqlite_path)

        self.engine = create_engine(db_path)
        Base.metadata.create_all(self.engine)
        self._ensure_sqlite_schema()
        self.Session = sessionmaker(bind=self.engine)

    def _ensure_sqlite_schema(self):
        """Backfill columns for users upgrading from older SQLite databases."""
        if self.engine.url.get_backend_name() != "sqlite":
            return

        schema_columns = {
            "environments": {
                "pip_mirror": '"pip_mirror" VARCHAR',
                "conda_mirror": '"conda_mirror" VARCHAR',
                "created_at": '"created_at" DATETIME',
                "last_modified": '"last_modified" DATETIME',
                "metadata_json": '"metadata_json" JSON DEFAULT \'{}\'',
            },
            "servers": {
                "default_python_path": '"default_python_path" VARCHAR DEFAULT \'/usr/bin/python3\'',
                "default_env_location": '"default_env_location" VARCHAR DEFAULT \'~/python_envs\'',
            },
            "mirrors": {
                "priority": '"priority" INTEGER DEFAULT 0',
                "is_active": '"is_active" BOOLEAN DEFAULT 0',
                "mirror_type": '"mirror_type" VARCHAR DEFAULT \'venv\'',
                "is_default": '"is_default" BOOLEAN DEFAULT 0',
            },
            "wsl_config": {
                "created_at": '"created_at" DATETIME',
                "updated_at": '"updated_at" DATETIME',
            },
        }

        with self.engine.begin() as conn:
            existing_tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            }
            for table, columns in schema_columns.items():
                if table not in existing_tables:
                    continue
                existing_columns = {
                    row._mapping["name"]
                    for row in conn.execute(text(f'PRAGMA table_info("{table}")'))
                }
                for column_name, column_ddl in columns.items():
                    if column_name not in existing_columns:
                        conn.execute(
                            text(f'ALTER TABLE "{table}" ADD COLUMN {column_ddl}')
                        )

    def get_session(self):
        return self.Session()

    @contextmanager
    def session_scope(self):
        session = self.get_session()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self):
        """释放数据库引擎和连接池。"""
        try:
            self.engine.dispose()
        except Exception:
            pass

    def save_environment(self, env_config):
        with self.session_scope() as session:
            env_type = env_config.env_type if isinstance(env_config.env_type, str) else env_config.env_type.value
            tool = env_config.tool if isinstance(env_config.tool, str) else env_config.tool.value
            metadata = env_config.metadata if hasattr(env_config, "metadata") else {}

            existing = session.query(EnvironmentModel).filter_by(
                location=env_config.location
            ).first()
            if not existing:
                existing = session.query(EnvironmentModel).filter_by(
                    name=env_config.name,
                    env_type=env_type,
                ).first()
            if not existing:
                existing = session.query(EnvironmentModel).filter_by(id=env_config.id).first()

            if existing:
                existing.name = env_config.name
                existing.python_version = env_config.python_version
                existing.location = env_config.location
                existing.env_type = env_type
                existing.tool = tool
                existing.packages = env_config.packages
                existing.metadata_json = metadata
            else:
                session.add(
                    EnvironmentModel(
                        id=env_config.id,
                        name=env_config.name,
                        python_version=env_config.python_version,
                        location=env_config.location,
                        env_type=env_type,
                        tool=tool,
                        packages=env_config.packages,
                        metadata_json=metadata,
                    )
                )
            session.commit()
    
    def get_environment_by_location(self, location: str):
        """根据路径查找环境"""
        with self.session_scope() as session:
            return session.query(EnvironmentModel).filter_by(location=location).first()
    
    def get_environment_by_name(self, name: str, env_type: str = None):
        """根据名称查找环境"""
        with self.session_scope() as session:
            query = session.query(EnvironmentModel).filter_by(name=name)
            if env_type:
                query = query.filter_by(env_type=env_type)
            return query.first()
    
    def deduplicate_environments(self, env_type: str = None):
        """去重数据库中的环境
        
        去重策略：
        1. 按路径去重：相同路径只保留一个（最新的）
        2. 按名称+类型去重：相同名称和类型只保留一个（最新的）
        
        返回：
        {
            'removed': 删除的数量,
            'kept': 保留的数量,
            'details': 删除的环境详情列表
        }
        """
        with self.session_scope() as session:
            query = session.query(EnvironmentModel)
            if env_type:
                query = query.filter_by(env_type=env_type)
            all_envs = query.all()

            removed_count = 0
            removed_details = []

            location_map = {}
            for env in all_envs:
                location_map.setdefault(env.location, []).append(env)

            for location, envs in location_map.items():
                if len(envs) > 1:
                    envs.sort(key=lambda e: e.last_modified if e.last_modified else e.created_at, reverse=True)
                    for env in envs[1:]:
                        removed_details.append(f"{env.name} (ID: {env.id[:8]}..., Path: {env.location})")
                        session.delete(env)
                        removed_count += 1

            session.commit()

            query = session.query(EnvironmentModel)
            if env_type:
                query = query.filter_by(env_type=env_type)
            remaining_envs = query.all()

            name_type_map = {}
            for env in remaining_envs:
                name_type_map.setdefault((env.name, env.env_type), []).append(env)

            for envs in name_type_map.values():
                if len(envs) > 1:
                    envs.sort(key=lambda e: e.last_modified if e.last_modified else e.created_at, reverse=True)
                    for env in envs[1:]:
                        removed_details.append(f"{env.name} (ID: {env.id[:8]}..., Duplicate name)")
                        session.delete(env)
                        removed_count += 1

            session.commit()

            query = session.query(EnvironmentModel)
            if env_type:
                query = query.filter_by(env_type=env_type)
            kept_count = query.count()

            return {
                "removed": removed_count,
                "kept": kept_count,
                "details": removed_details,
            }

    def get_environment(self, env_id):
        with self.session_scope() as session:
            return session.query(EnvironmentModel).filter_by(id=env_id).first()

    def list_environments(self, env_type: str = None):
        with self.session_scope() as session:
            query = session.query(EnvironmentModel)
            if env_type:
                query = query.filter_by(env_type=env_type)
            return query.all()

    def delete_environment(self, env_id):
        with self.session_scope() as session:
            env = session.query(EnvironmentModel).filter_by(id=env_id).first()
            if env:
                session.delete(env)
                session.commit()

    def save_server(self, server_config: RemoteServerConfig):
        with self.session_scope() as session:
            existing = session.query(RemoteServerModel).filter_by(id=server_config.id).first()
            if existing:
                existing.name = server_config.name
                existing.host = server_config.host
                existing.port = server_config.port
                existing.username = server_config.username
                existing.auth_type = server_config.auth_type
                existing.password = server_config.password
                existing.key_path = server_config.key_path
                existing.default_python_path = server_config.default_python_path
                existing.default_env_location = server_config.default_env_location
            else:
                session.add(
                    RemoteServerModel(
                        id=server_config.id,
                        name=server_config.name,
                        host=server_config.host,
                        port=server_config.port,
                        username=server_config.username,
                        auth_type=server_config.auth_type,
                        password=server_config.password,
                        key_path=server_config.key_path,
                        default_python_path=server_config.default_python_path,
                        default_env_location=server_config.default_env_location,
                    )
                )
            session.commit()

    def list_servers(self):
        with self.session_scope() as session:
            servers = session.query(RemoteServerModel).order_by(RemoteServerModel.name.asc()).all()
            return [
                RemoteServerConfig(
                    id=server.id,
                    name=server.name,
                    host=server.host,
                    username=server.username,
                    auth_type=server.auth_type,
                    port=server.port,
                    password=server.password,
                    key_path=server.key_path,
                    default_python_path=server.default_python_path,
                    default_env_location=server.default_env_location,
                )
                for server in servers
            ]

    def delete_server(self, server_id: str):
        """删除服务器配置"""
        with self.session_scope() as session:
            server = session.query(RemoteServerModel).filter_by(id=server_id).first()
            if server:
                session.delete(server)
                session.commit()

    def get_server(self, server_id: str):
        with self.session_scope() as session:
            server = session.query(RemoteServerModel).filter_by(id=server_id).first()
            if not server:
                return None
            return RemoteServerConfig(
                id=server.id,
                name=server.name,
                host=server.host,
                username=server.username,
                auth_type=server.auth_type,
                port=server.port,
                password=server.password,
                key_path=server.key_path,
                default_python_path=server.default_python_path,
                default_env_location=server.default_env_location,
            )

    # 镜像管理方法
    def save_mirror(self, mirror):
        """保存或更新镜像"""
        with self.session_scope() as session:
            mirror_type = mirror.mirror_type if isinstance(mirror.mirror_type, str) else mirror.mirror_type.value
            is_default = mirror.is_default if hasattr(mirror, "is_default") else False
            existing = session.query(MirrorModel).filter_by(id=mirror.id).first()
            if existing:
                existing.name = mirror.name
                existing.url = mirror.url
                existing.priority = mirror.priority
                existing.is_active = mirror.is_active
                existing.is_default = is_default
                existing.mirror_type = mirror_type
            else:
                session.add(
                    MirrorModel(
                        id=mirror.id,
                        name=mirror.name,
                        url=mirror.url,
                        priority=mirror.priority,
                        is_active=mirror.is_active,
                        is_default=is_default,
                        mirror_type=mirror_type,
                    )
                )
            session.commit()
    
    def list_mirrors(self, mirror_type: str = None):
        """列出所有镜像"""
        with self.session_scope() as session:
            query = session.query(MirrorModel)
            if mirror_type:
                query = query.filter_by(mirror_type=mirror_type)
            return query.order_by(MirrorModel.priority.desc()).all()
    
    def delete_mirror(self, mirror_id: str):
        """删除镜像"""
        with self.session_scope() as session:
            mirror = session.query(MirrorModel).filter_by(id=mirror_id).first()
            if mirror:
                session.delete(mirror)
                session.commit()
    
    def get_active_mirror(self, mirror_type: str):
        """获取激活的镜像"""
        with self.session_scope() as session:
            return session.query(MirrorModel).filter_by(
                mirror_type=mirror_type,
                is_active=True,
            ).first()
    
    def set_default_mirror(self, mirror_id: str):
        """Set the default mirror for the selected mirror type."""
        with self.session_scope() as session:
            mirror = session.query(MirrorModel).filter_by(id=mirror_id).first()
            if not mirror:
                return False
            session.query(MirrorModel).filter_by(mirror_type=mirror.mirror_type).update({"is_default": False})
            mirror.is_default = True
            mirror.is_active = True
            session.commit()
            return True

    # WSL 配置管理方法
    def save_wsl_config(self, distro_name: str = None, username: str = None, password: str = None):
        """保存WSL配置（只保存最新的一条配置）"""
        with self.session_scope() as session:
            session.query(WSLConfigModel).delete()
            session.add(
                WSLConfigModel(
                    distro_name=distro_name,
                    username=username,
                    password=password,
                )
            )
            session.commit()
    
    def load_wsl_config(self):
        """加载WSL配置"""
        with self.session_scope() as session:
            config = session.query(WSLConfigModel).first()
            if config:
                return {
                    "distro": config.distro_name,
                    "username": config.username,
                    "password": config.password,
                }
            return None

    def save_app_setting(self, key: str, value: str):
        """保存应用级设置。"""
        with self.session_scope() as session:
            setting = session.query(AppSettingModel).filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                session.add(AppSettingModel(key=key, value=value))
            session.commit()

    def load_app_setting(self, key: str, default=None):
        """读取应用级设置。"""
        with self.session_scope() as session:
            setting = session.query(AppSettingModel).filter_by(key=key).first()
            if setting is None or setting.value is None:
                return default
            return setting.value
