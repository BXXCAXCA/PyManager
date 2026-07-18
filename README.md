# PyManager

PyManager 是一个基于 PySide6 的桌面应用，用于统一管理本地、WSL 和远程服务器上的 Python 运行环境。

## 主要功能

- **本地环境管理**：扫描和管理本地 Python venv 与 conda 环境
- **WSL 环境管理**：扫描和管理 WSL 发行版中的 Python 环境
- **远程环境管理**：通过 SSH 连接远程服务器，管理其上的 Python 环境
- **包管理**：安装、卸载、导入/导出 requirements
- **终端与交互**：打开环境终端、Python REPL、Jupyter Notebook
- **镜像源管理**：配置 pip/conda 镜像源
- **远程文件浏览**：通过 SFTP 浏览和操作远程目录
- **国际化**：支持中英文切换
- **主题切换**：支持深色/浅色主题

## 技术栈

| 类别 | 技术 |
|------|------|
| GUI | PySide6 (Qt 6) |
| 远程连接 | Paramiko (SSH/SFTP) |
| 数据存储 | SQLAlchemy |
| 数据模型 | dataclasses |
| 异步任务 | QThread (Worker) |
| 国际化 | 自定义 i18n 模块 |

## 快速开始

### 1. 安装依赖

```bash
pip install PySide6 paramiko sqlalchemy
```

### 2. 启动程序

```bash
python main.py
```

## 使用说明

### 环境视图

- **本地环境**：扫描常见目录中的 venv 和 conda 环境
- **WSL 环境**：基于所选发行版和用户扫描 Linux 路径
- **远程环境**：连接 SSH 后扫描远程目录中的 Python 环境

### 常用操作

- **创建环境**：支持 venv 与 conda
- **包管理**：安装、卸载、导入 requirements、导出 requirements
- **终端**：打开已激活环境的命令行
- **Python**：直接进入交互式解释器
- **Jupyter**：在目标环境中启动 Notebook
- **文件夹**：打开本地目录或使用远程文件浏览器

### 远程服务器

1. 在连接配置中添加 SSH 服务器信息
2. 连接后可浏览远程文件、管理远程 Python 环境
3. 支持通过环境列表操作远程环境

## 项目结构

```text
PyManager/
├─ main.py                          # 应用入口与主窗口
├─ src/
│  ├─ base_environment_manager.py   # 环境管理基类
│  ├─ environment_manager.py        # 本地/WSL/远程环境管理器
│  ├─ command_executor.py           # 命令执行器（本地/WSL/远程）
│  ├─ command_launcher.py           # 命令构建与启动
│  ├─ ssh_client.py                 # SSH 客户端封装
│  ├─ database.py                   # 数据库 ORM 模型与管理
│  ├─ models.py                     # 枚举与数据类定义
│  ├─ exceptions.py                 # 自定义异常
│  ├─ worker.py                     # 异步工作线程
│  ├─ i18n.py                       # 国际化翻译字典
│  ├─ styles.py                     # 浅色/深色主题样式
│  ├─ env_deploy_panel.py           # 环境部署面板
│  ├─ package_management_panel.py   # 包管理面板
│  ├─ mirror_manager.py             # 镜像源管理
│  ├─ connection_config_dialog.py   # 连接配置对话框
│  ├─ remote_file_browser_panel.py  # 远程文件浏览器面板
│  └─ remote_ops_dialogs.py         # 远程操作对话框
├─ C:\PyManagerConfig\
│  └─ app.db                        # 运行时 SQLite 配置数据库
└─ docs/
   ├─ ARCHITECTURE.md               # 架构与模块说明
   └─ REMOTE_FEATURES.md            # 远程功能说明
```

## 文档索引

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)：整体模块划分和职责
- [`docs/REMOTE_FEATURES.md`](docs/REMOTE_FEATURES.md)：远程连接、终端、目录和 Jupyter 相关能力

## 当前仓库约定

- 根目录不再保留一次性手工测试脚本
- 面向使用者和维护者的说明统一放入 `README.md` 与 `docs/`
- 打包后的便携版会自动复制 `docs/` 目录
