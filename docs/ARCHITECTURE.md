# PyManager 架构说明

PyManager 是一个基于 PySide6 的桌面管理工具，核心目标是统一管理本地、WSL 和远程服务器上的 Python 运行环境。程序按职责分为界面层、业务管理层、执行层、持久化层和远程能力层。

## 模块分层

| 层级 | 主要文件 | 职责 |
| --- | --- | --- |
| 应用入口 | `main.py` | 主窗口、导航、环境列表、异步任务调度、连接状态协调 |
| 界面面板 | `src/*_panel.py`, `src/*_dialog.py` | 环境部署、包管理、远程文件和配置弹窗 |
| 环境管理 | `src/base_environment_manager.py`, `src/environment_manager.py` | 扫描、创建、删除、包安装、导入导出本地/WSL/远程环境 |
| 命令执行 | `src/command_executor.py`, `src/command_launcher.py` | 本地、WSL、SSH 命令执行，以及终端/Python/Jupyter 启动命令生成 |
| 远程能力 | `src/ssh_client.py`, `src/remote_file_browser_panel.py` | SSH/SFTP 和远程目录操作 |
| 数据持久化 | `src/database.py`, `C:\PyManagerConfig\app.db` | 环境记录、远程连接配置和镜像配置 |
| 通用支持 | `src/models.py`, `src/worker.py`, `src/i18n.py`, `src/styles.py` | 数据结构、后台线程、国际化和主题 |

## 关键流程

1. 启动时初始化数据库、管理器和命令构建器。
2. 首屏先展示本地环境，远程自动连接在后台执行，避免启动卡顿。
3. 环境扫描由对应的 manager 调用 executor 执行，结果统一转换为 `EnvironmentInfo`。
4. 创建、删除、包管理、导入导出等耗时任务通过 `Worker` 放到后台线程。
5. 远程功能复用同一个 SSH 客户端，并在连接变化时同步到远程环境和文件浏览。

## 稳定性约定

- 远程路径、WSL 路径和 shell 参数应通过统一引用函数处理。
- 耗时操作不直接阻塞主界面线程。
- 自动连接失败不弹出干扰性错误，只更新状态；用户手动连接时再显示明确反馈。
- 打包配置保留最小必要 PySide6 模块，避免把无关 Qt 组件全部带入。
