import sys
import os
import uuid
import subprocess
import logging
from datetime import datetime
import shiboken6
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QLabel,
    QLineEdit,
    QFormLayout,
    QComboBox,
    QMessageBox,
    QListWidget,
    QInputDialog,
    QSplitter,
    QFrame,
    QFileDialog,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtCore import QLibraryInfo

from src.database import DatabaseManager
from src.environment_manager import (
    LocalEnvironmentManager,
    WSLEnvironmentManager,
    RemoteEnvironmentManager,
    EnvironmentInfo,
)
from src.models import ToolType
from src.mirror_manager import MirrorManager
from src.ssh_client import SSHClient, SSHConnection
from src.worker import Worker
from src.package_management_panel import PackageManagementPanel
from src.connection_config_dialog import ConnectionConfigDialog
from src.remote_file_browser_panel import RemoteFileBrowserPanel
from src.styles import GLOBAL_STYLE, COLORS, DARK_GLOBAL_STYLE
from src.i18n import i18n
from src.models import RemoteServerConfig
from src.command_launcher import CommandLauncher, LocalCommandBuilder, WSLCommandBuilder, RemoteCommandBuilder
from src.env_deploy_panel import EnvDeployPanel


logger = logging.getLogger(__name__)


def get_username():
    """获取当前用户名，兼容 Windows 和 Linux"""
    return os.getenv('USERNAME') or os.getenv('USER') or 'user'


class CreateEnvDialog(QDialog):
    def __init__(self, parent=None, mirror_manager=None):
        super().__init__(parent)
        self.mirror_manager = mirror_manager
        self.setWindowTitle(i18n.t("dialog_create_title"))
        self.setMinimumWidth(450)
        self._apply_dialog_theme(parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # 表单
        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(12)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(i18n.t("placeholder_name"))

        self.version_edit = QComboBox()
        self.version_edit.addItems(["3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14"])
        self.version_edit.setCurrentText("3.11")

        self.tool_combo = QComboBox()
        self.tool_combo.addItems(["conda", "venv"])
        self.tool_combo.setCurrentText("conda")
        
        self.mirror_combo = QComboBox()
        self.mirror_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)  # 自动调整大小
        self.mirror_combo.setMinimumWidth(300)  # 设置最小宽度
        self.mirror_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)  # 不省略文本
        self.tool_combo.currentTextChanged.connect(self.update_mirror_list)

        self.form_layout.addRow(self._create_form_label(i18n.t("dialog_create_name")), self.name_edit)
        self.form_layout.addRow(self._create_form_label(i18n.t("dialog_create_version")), self.version_edit)
        self.form_layout.addRow(self._create_form_label(i18n.t("dialog_create_tool")), self.tool_combo)
        self.form_layout.addRow(self._create_form_label(i18n.t("dialog_create_mirror")), self.mirror_combo)

        layout.addLayout(self.form_layout)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton(i18n.t("btn_cancel"))
        cancel_btn.clicked.connect(self.reject)

        self.create_btn = QPushButton(i18n.t("dialog_create_btn"))
        self.create_btn.setObjectName("primary")
        self.create_btn.clicked.connect(self._submit)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.create_btn)

        layout.addLayout(btn_layout)
        
        # 初始化镜像列表
        self.update_mirror_list()

    def _apply_dialog_theme(self, parent):
        """跟随主窗口当前主题，避免弹窗在暗色模式下出现样式错乱。"""
        parent_style = parent.styleSheet() if parent and hasattr(parent, "styleSheet") else ""
        is_dark_theme = bool(parent and getattr(parent, "current_theme", "light") == "dark")
        label_color = "#E0E0E0" if is_dark_theme else COLORS["text_primary"]
        dialog_style = parent_style or GLOBAL_STYLE
        dialog_style += (
            "\n"
            "QLabel#form_label {\n"
            "    background-color: transparent;\n"
            f"    color: {label_color};\n"
            "    font-size: 13px;\n"
            "}\n"
        )
        self.setStyleSheet(dialog_style)

    def _create_form_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("form_label")
        return label

    def _submit(self):
        """在关闭对话框前先做基础校验，给出明确反馈。"""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, i18n.t("msg_warning"), i18n.t("msg_name_empty"))
            self.name_edit.setFocus()
            return
        self.accept()

    def update_mirror_list(self):
        """根据选择的工具更新镜像列表"""
        self.mirror_combo.clear()
        self.mirror_combo.addItem(i18n.t("pkg_mirror_default"), None)
        
        if self.mirror_manager:
            # 强制从数据库重新加载镜像
            self.mirror_manager._load_from_db()
            
            selected_tool = self.tool_combo.currentText()
            target_type = ToolType.CONDA if selected_tool == "conda" else ToolType.VENV
            mirrors = self.mirror_manager.list_mirrors(target_type)
            
            # 只显示启用的镜像
            for mirror in mirrors:
                if mirror.is_active:
                    self.mirror_combo.addItem(mirror.name, mirror.id)
            
            if self.mirror_combo.count() == 1:
                mirror_name = "conda" if selected_tool == "conda" else "pip"
                hint_text = (
                    f"(请先在镜像管理中启用 {mirror_name} 镜像)"
                    if i18n.current_lang == "zh"
                    else f"(Enable {mirror_name} mirrors in Mirror Management)"
                )
                self.mirror_combo.addItem(hint_text, None)
            
            # 设置下拉列表的最大可见项数
            self.mirror_combo.setMaxVisibleItems(15)
        
        # 设置下拉列表的宽度以适应最长的文本
        max_width = 0
        for i in range(self.mirror_combo.count()):
            text = self.mirror_combo.itemText(i)
            width = self.mirror_combo.fontMetrics().horizontalAdvance(text)
            max_width = max(max_width, width)
        
        # 设置下拉列表视图的最小宽度（加上一些边距）
        self.mirror_combo.view().setMinimumWidth(max_width + 40)

    def get_data(self):
        mirror_id = self.mirror_combo.currentData()
        return {
            "name": self.name_edit.text(),
            "version": self.version_edit.currentText(),
            "location": "~/python_envs",  # 使用Linux路径格式，不在Windows端展开
            "tool": self.tool_combo.currentText(),
            "mirror_id": mirror_id,
        }




class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self._load_ui_preferences()
        self.setWindowTitle(i18n.t("app_title"))
        self.resize(1200, 800)
        
        # 应用全局样式
        self.setStyleSheet(DARK_GLOBAL_STYLE if self.current_theme == "dark" else GLOBAL_STYLE)

        self.local_manager = LocalEnvironmentManager()
        
        # 加载WSL配置
        wsl_config = self.db.load_wsl_config()
        if wsl_config:
            self.wsl_manager = WSLEnvironmentManager(
                distro_name=wsl_config['distro'],
                username=wsl_config['username'],
                password=wsl_config['password']
            )
        else:
            self.wsl_manager = WSLEnvironmentManager()
        
        self.ssh_client = SSHClient()
        self.remote_manager = None
        self.current_server_id = None
        self.mirror_manager = MirrorManager(self.db)  # 传递数据库
        self.mirror_statuses = {}
        self.workers = []

        # 初始化 CommandLauncher — 统一命令生成组件
        self.command_launcher = CommandLauncher()
        self.command_launcher.register_builder("local", LocalCommandBuilder())
        self._wsl_builder = WSLCommandBuilder(
            distro_name=self.wsl_manager.distro_name if hasattr(self.wsl_manager, 'distro_name') else None,
            username=self.wsl_manager.username if hasattr(self.wsl_manager, 'username') else None,
            conda_path_finder=self.wsl_manager._find_conda_path if hasattr(self.wsl_manager, '_find_conda_path') else None,
        )
        self.command_launcher.register_builder("wsl", self._wsl_builder)
        self._remote_builder = RemoteCommandBuilder(
            ssh_connected_checker=lambda: self.ssh_client is not None and self.ssh_client.client is not None,
            ssh_info_provider=self._get_ssh_info,
            conda_path_finder=lambda: self.remote_manager._find_conda_path() if self.remote_manager else "conda",
        )
        self.command_launcher.register_builder("remote", self._remote_builder)
        
        # 当前选中的环境类型
        self.current_env_type = "local"
        
        # 创建菜单栏
        menubar = self.menuBar()
        
        # 关于菜单
        self.about_menu = menubar.addMenu(i18n.t("menu_about"))
        self.about_action = self.about_menu.addAction(i18n.t("menu_about_app"))
        self.about_action.triggered.connect(self.show_about_dialog)
        
        # 主题菜单
        self.theme_menu = menubar.addMenu(i18n.t("menu_theme"))
        
        self.light_action = self.theme_menu.addAction(i18n.t("menu_theme_light"))
        self.light_action.triggered.connect(lambda: self.change_theme("light"))
        
        self.dark_action = self.theme_menu.addAction(i18n.t("menu_theme_dark"))
        self.dark_action.triggered.connect(lambda: self.change_theme("dark"))
        
        # 语言菜单
        self.lang_menu = menubar.addMenu(i18n.t("menu_language"))
        
        self.chinese_action = self.lang_menu.addAction(i18n.t("menu_chinese"))
        self.chinese_action.triggered.connect(lambda: self.change_language("zh"))
        
        self.english_action = self.lang_menu.addAction(i18n.t("menu_english"))
        self.english_action.triggered.connect(lambda: self.change_language("en"))

        # 创建主布局：侧边栏 + 内容区
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 创建侧边栏
        self.sidebar = self.create_sidebar()
        
        # 创建内容区
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(16)
        
        # 使用 Splitter 使侧边栏可调整大小
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.content_area)
        splitter.setStretchFactor(0, 0)  # 侧边栏固定
        splitter.setStretchFactor(1, 1)  # 内容区可伸缩
        splitter.setSizes([200, 1000])
        
        main_layout.addWidget(splitter)
        
        # 初始化显示本地环境（会自动刷新）
        self.show_environment_view("local")
        QTimer.singleShot(0, self._auto_connect_remote_server)

    def _load_ui_preferences(self):
        """启动时恢复主题和语言偏好。"""
        saved_language = self.db.load_app_setting("language", "zh")
        if saved_language not in i18n.translations:
            saved_language = "zh"
        i18n.set_language(saved_language)

        saved_theme = self.db.load_app_setting("theme", "light")
        self.current_theme = saved_theme if saved_theme in ("light", "dark") else "light"

    def _save_ui_preference(self, key: str, value: str):
        try:
            self.db.save_app_setting(key, value)
        except Exception as exc:
            logger.warning("Failed to save UI preference %s=%s: %s", key, value, exc)

    def change_language(self, lang: str, persist: bool = True):
        """切换语言"""
        if lang not in i18n.translations:
            return
        i18n.set_language(lang)
        if persist:
            self._save_ui_preference("language", lang)

        # 更新窗口标题
        self.setWindowTitle(i18n.t("app_title"))

        # 更新菜单栏
        self.about_menu.setTitle(i18n.t("menu_about"))
        self.about_action.setText(i18n.t("menu_about_app"))
        
        self.theme_menu.setTitle(i18n.t("menu_theme"))
        self.light_action.setText(i18n.t("menu_theme_light"))
        self.dark_action.setText(i18n.t("menu_theme_dark"))
        
        self.lang_menu.setTitle(i18n.t("menu_language"))
        self.chinese_action.setText(i18n.t("menu_chinese"))
        self.english_action.setText(i18n.t("menu_english"))

        # 更新侧边栏
        nav_items = [
            i18n.t("nav_local"),
            i18n.t("nav_wsl"),
            i18n.t("nav_remote"),
            i18n.t("nav_deploy"),
            i18n.t("nav_mirrors"),
            i18n.t("nav_files"),
        ]
        for i, text in enumerate(nav_items):
            self.sidebar.item(i).setText(text)

        # 重新显示当前视图
        current_row = self.sidebar.currentRow()
        self.on_sidebar_changed(current_row)

    def change_theme(self, theme: str, persist: bool = True):
        """切换主题模式"""
        if theme not in ("light", "dark"):
            return
        self.current_theme = theme
        if persist:
            self._save_ui_preference("theme", theme)
        
        if theme == "dark":
            self.setStyleSheet(DARK_GLOBAL_STYLE)
        else:
            self.setStyleSheet(GLOBAL_STYLE)

        current_row = self.sidebar.currentRow()
        self.on_sidebar_changed(current_row)

    def _show_info_box(self, title, message):
        """显示信息提示框（带中文确定按钮）"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Information)
        
        # 清除所有标准按钮
        msg_box.setStandardButtons(QMessageBox.StandardButton.NoButton)
        
        # 添加自定义按钮
        ok_btn = msg_box.addButton(
            "确定" if i18n.current_lang == "zh" else "OK",
            QMessageBox.ButtonRole.AcceptRole
        )
        msg_box.setDefaultButton(ok_btn)
        msg_box.exec()

    def show_about_dialog(self):
        """显示关于对话框"""
        about_dialog = QDialog(self)
        about_dialog.setWindowTitle(i18n.t("menu_about_app"))
        about_dialog.setMinimumWidth(500)
        about_dialog.setStyleSheet(self.styleSheet())
        
        layout = QVBoxLayout(about_dialog)
        layout.setSpacing(16)
        
        # 标题
        title = QLabel(i18n.t("about_title"))
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # 版本信息
        version_label = QLabel(f"{i18n.t('about_version')}: 1.0.0")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)
        
        # 描述
        desc_label = QLabel(i18n.t("about_description"))
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # 功能特性
        features_title = QLabel(i18n.t("about_features"))
        features_title.setObjectName("subtitle")
        layout.addWidget(features_title)
        
        for i in range(1, 6):
            feature_label = QLabel(i18n.t(f"about_feature_{i}"))
            layout.addWidget(feature_label)
        
        # 关闭按钮
        close_btn = QPushButton(i18n.t("btn_close"))
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(about_dialog.accept)
        layout.addWidget(close_btn)
        
        about_dialog.exec()


    def create_sidebar(self):
        """创建侧边栏导航"""
        sidebar = QListWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMaximumWidth(220)
        sidebar.setMinimumWidth(180)
        sidebar.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 禁用焦点，移除虚线框

        # 添加导航项
        nav_items = [
            i18n.t("nav_local"),
            i18n.t("nav_wsl"),
            i18n.t("nav_remote"),
            i18n.t("nav_deploy"),
            i18n.t("nav_mirrors"),
            i18n.t("nav_files"),
        ]

        for label in nav_items:
            sidebar.addItem(label)

        # 默认选中第一项
        sidebar.setCurrentRow(0)

        # 连接选择事件
        sidebar.currentRowChanged.connect(self.on_sidebar_changed)

        return sidebar


    def on_sidebar_changed(self, index):
        """侧边栏选择改变"""
        nav_map = ["local", "wsl", "remote", "deploy", "mirrors", "files"]
        if 0 <= index < len(nav_map):
            view_type = nav_map[index]
            if view_type in ["local", "wsl", "remote"]:
                self.show_environment_view(view_type)
            elif view_type == "deploy":
                self.show_deploy_view()
            elif view_type == "mirrors":
                self.show_mirror_view()
            elif view_type == "files":
                self.show_file_browser_view()

    def show_environment_view(self, env_type: str):
        """显示环境管理视图"""
        self.current_env_type = env_type

        # 清空内容区
        self.clear_content_area()

        # 创建操作按钮区域
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)

        # 主要操作按钮
        create_btn = QPushButton(i18n.t("btn_create"))
        create_btn.clicked.connect(lambda: self.handle_create(env_type))

        clone_btn = QPushButton(i18n.t("btn_clone"))
        clone_btn.clicked.connect(lambda: self.handle_clone(env_type))

        import_btn = QPushButton(i18n.t("btn_import"))
        import_btn.clicked.connect(lambda: self.handle_import(env_type))

        export_btn = QPushButton(i18n.t("btn_export"))
        export_btn.clicked.connect(lambda: self.handle_export(env_type))

        delete_btn = QPushButton(i18n.t("btn_delete"))
        delete_btn.setObjectName("danger")
        delete_btn.clicked.connect(lambda: self.handle_delete(env_type))

        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(clone_btn)
        btn_layout.addWidget(import_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(delete_btn)
        btn_layout.addStretch()

        # 辅助操作按钮
        scan_btn = QPushButton(i18n.t("btn_scan"))
        scan_btn.clicked.connect(lambda: self.scan_environments(env_type))

        btn_layout.addWidget(scan_btn)

        if env_type == "wsl":
            # 为WSL添加配置按钮
            config_btn = QPushButton("⚙️ " + ("配置WSL" if i18n.current_lang == "zh" else "Configure WSL"))
            config_btn.clicked.connect(self.handle_wsl_config)
            btn_layout.addWidget(config_btn)
        elif env_type == "remote":
            config_btn = QPushButton("⚙️ " + ("配置远程" if i18n.current_lang == "zh" else "Configure Remote"))
            config_btn.clicked.connect(self.handle_remote_config)
            btn_layout.addWidget(config_btn)

        self.content_layout.addWidget(btn_widget)

        # 创建环境列表表格
        table = QTableWidget()
        table.setColumnCount(6)  # 增加一列用于操作按钮
        table.setHorizontalHeaderLabels([
            i18n.t("col_name"),
            i18n.t("col_version"),
            i18n.t("col_location"),
            i18n.t("col_tool"),
            i18n.t("col_packages"),
            i18n.t("col_actions")
        ])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 禁用表格焦点，移除虚线框
        
        # 设置列宽度策略
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)        # 名称 - 固定
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)        # 版本 - 固定
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)      # 位置 - 自动伸缩
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)        # 工具 - 固定
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)        # 软件包 - 固定
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)        # 操作 - 固定
        
        # 设置具体列宽
        table.setColumnWidth(0, 140)   # 名称：140px
        table.setColumnWidth(1, 75)    # 版本：75px（压缩）
        # 位置列自动伸缩，占据剩余空间
        table.horizontalHeader().setStretchLastSection(False)
        table.setColumnWidth(3, 70)    # 工具：70px
        table.setColumnWidth(4, 80)    # 软件包：80px
        table.setColumnWidth(5, 242)   # 操作：终端、Python、Jupyter、目录
        
        # 设置行号列宽度
        table.verticalHeader().setFixedWidth(50)  # 序号列宽度
        
        # 设置表格样式 - 移除硬编码样式，让它继承主题
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        
        table.itemSelectionChanged.connect(lambda: self.show_package_panel(env_type))

        # 包管理面板容器
        package_container = QWidget()
        package_container.setObjectName("packageContainer")
        package_container.setAutoFillBackground(False)
        package_container.setLayout(QVBoxLayout())
        package_container.layout().setContentsMargins(0, 0, 0, 0)
        package_container.setVisible(False)  # 默认隐藏
        
        # 使用 Splitter 实现表格和包管理面板的 50/50 分割
        content_splitter = QSplitter(Qt.Orientation.Vertical)
        content_splitter.addWidget(table)
        content_splitter.addWidget(package_container)
        content_splitter.setStretchFactor(0, 1)
        content_splitter.setStretchFactor(1, 1)
        
        self.content_layout.addWidget(content_splitter)

        # 保存引用
        setattr(self, f"{env_type}_table", table)
        setattr(self, f"{env_type}_package_container", package_container)
        setattr(self, f"{env_type}_splitter", content_splitter)

        # 加载数据
        self.refresh_list(env_type)


    def show_deploy_view(self):
        """显示环境部署视图"""
        self.clear_content_area()

        wsl_config = {}
        if hasattr(self, 'wsl_manager'):
            wsl_config = {
                'distro': getattr(self.wsl_manager, 'distro_name', None),
                'username': getattr(self.wsl_manager, 'username', None),
            }

        deploy_panel = EnvDeployPanel(wsl_config=wsl_config, theme=self.current_theme)
        self.content_layout.addWidget(deploy_panel)


    def show_mirror_view(self):
        """显示镜像管理视图"""
        self.clear_content_area()

        # 操作按钮移到顶部
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton(i18n.t("mirror_add"))
        add_btn.clicked.connect(self.add_mirror)
        btn_layout.addWidget(add_btn)
        
        toggle_btn = QPushButton("✓ " + i18n.t("mirror_toggle"))
        toggle_btn.clicked.connect(self.toggle_mirror)
        btn_layout.addWidget(toggle_btn)
        
        set_default_btn = QPushButton("⭐ " + i18n.t("mirror_set_default"))
        set_default_btn.clicked.connect(self.set_default_mirror)
        btn_layout.addWidget(set_default_btn)

        check_btn = QPushButton("检查可用性" if i18n.current_lang == "zh" else "Check Availability")
        check_btn.clicked.connect(self.check_mirror_availability)
        btn_layout.addWidget(check_btn)
        
        delete_btn = QPushButton(i18n.t("btn_delete"))
        delete_btn.setObjectName("danger")
        delete_btn.clicked.connect(self.delete_mirror)
        btn_layout.addWidget(delete_btn)
        
        btn_layout.addStretch()
        
        self.content_layout.addLayout(btn_layout)

        # 创建表格显示镜像
        self.mirror_table = QTableWidget()
        self.mirror_table.setColumnCount(5)
        self.mirror_table.setHorizontalHeaderLabels([
            i18n.t("col_name"),
            "URL",
            i18n.t("mirror_type"),
            i18n.t("mirror_status"),
            "连通性" if i18n.current_lang == "zh" else "Availability"
        ])
        self.mirror_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.mirror_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 禁用表格焦点，移除虚线框
        
        header = self.mirror_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        
        self.mirror_table.setColumnWidth(0, 150)
        self.mirror_table.setColumnWidth(2, 80)
        self.mirror_table.setColumnWidth(3, 100)
        self.mirror_table.setColumnWidth(4, 110)
        self.mirror_table.setAlternatingRowColors(True)
        
        self.content_layout.addWidget(self.mirror_table)
        
        # 加载镜像列表
        self.refresh_mirrors()


    def show_file_browser_view(self):
        """显示文件浏览器视图"""
        self.clear_content_area()

        # 控制按钮区域
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        # 服务器选择
        server_label = QLabel("服务器:" if i18n.current_lang == "zh" else "Server:")
        controls_layout.addWidget(server_label)

        self.file_server_combo = QComboBox()
        self.file_server_combo.addItem(
            "请选择服务器" if i18n.current_lang == "zh" else "Select server",
            None,
        )
        saved_servers = self.db.list_servers()
        for server in saved_servers:
            self.file_server_combo.addItem(server.name, server.id)
        controls_layout.addWidget(self.file_server_combo, 1)

        # 连接按钮
        connect_btn = QPushButton(i18n.t("btn_connect"))
        connect_btn.setObjectName("primary")
        connect_btn.clicked.connect(self.handle_file_browser_connect)
        controls_layout.addWidget(connect_btn)

        new_connection_btn = QPushButton(i18n.t("btn_new_connection"))
        new_connection_btn.clicked.connect(self.handle_new_connection)
        controls_layout.addWidget(new_connection_btn)

        edit_selected_btn = QPushButton(i18n.t("btn_refresh_connections"))
        edit_selected_btn.clicked.connect(self.handle_edit_selected_connection)
        controls_layout.addWidget(edit_selected_btn)

        # 删除连接按钮
        delete_connection_btn = QPushButton(i18n.t("btn_delete_connection"))
        delete_connection_btn.setObjectName("danger")
        delete_connection_btn.clicked.connect(self.delete_file_browser_connection)
        controls_layout.addWidget(delete_connection_btn)

        controls_layout.addStretch()

        self.content_layout.addWidget(controls_widget)

        # 文件操作按钮区域
        file_controls_widget = QWidget()
        file_controls_layout = QHBoxLayout(file_controls_widget)
        file_controls_layout.setContentsMargins(0, 0, 0, 0)
        file_controls_layout.setSpacing(8)

        up_btn = QPushButton(i18n.t("btn_up"))
        refresh_btn = QPushButton("🔄 " + i18n.t("btn_refresh"))
        upload_btn = QPushButton(i18n.t("btn_upload"))
        download_btn = QPushButton(i18n.t("btn_download"))
        mkdir_btn = QPushButton("新建目录" if i18n.current_lang == "zh" else "New Dir")
        rename_btn = QPushButton("重命名" if i18n.current_lang == "zh" else "Rename")
        view_btn = QPushButton("查看" if i18n.current_lang == "zh" else "View")
        delete_file_btn = QPushButton("删除" if i18n.current_lang == "zh" else "Delete")
        delete_file_btn.setObjectName("danger")
        
        file_controls_layout.addWidget(up_btn)
        file_controls_layout.addWidget(refresh_btn)
        file_controls_layout.addWidget(upload_btn)
        file_controls_layout.addWidget(download_btn)
        file_controls_layout.addWidget(mkdir_btn)
        file_controls_layout.addWidget(rename_btn)
        file_controls_layout.addWidget(view_btn)
        file_controls_layout.addWidget(delete_file_btn)
        file_controls_layout.addStretch()

        self.content_layout.addWidget(file_controls_widget)

        # 当前路径显示
        path_widget = QWidget()
        path_layout = QHBoxLayout(path_widget)
        path_layout.setContentsMargins(0, 8, 0, 0)
        path_layout.setSpacing(8)
        
        self.file_path_label = QLabel(("当前路径: " if i18n.current_lang == "zh" else "Path: ") + ".")
        path_layout.addWidget(self.file_path_label)
        path_layout.addStretch()
        
        self.content_layout.addWidget(path_widget)

        # 文件浏览器面板
        self.file_browser_panel = RemoteFileBrowserPanel(self.ssh_client)
        self.content_layout.addWidget(self.file_browser_panel, 1)

        # 连接信号
        up_btn.clicked.connect(self.file_browser_panel.go_up)
        refresh_btn.clicked.connect(
            lambda checked=False: self.file_browser_panel.refresh_files()
        )
        upload_btn.clicked.connect(self.file_browser_panel.upload_file)
        download_btn.clicked.connect(self.file_browser_panel.download_file)
        mkdir_btn.clicked.connect(self.file_browser_panel.create_directory)
        rename_btn.clicked.connect(self.file_browser_panel.rename_selected)
        view_btn.clicked.connect(self.file_browser_panel.view_text_file)
        delete_file_btn.clicked.connect(self.file_browser_panel.delete_selected)
        self.file_browser_panel.path_changed.connect(self.on_file_browser_path_changed)

        # 初始状态：禁用文件操作按钮
        controls_enabled = bool(saved_servers)
        self.file_server_combo.setEnabled(controls_enabled)
        new_connection_btn.setEnabled(True)
        connect_btn.setEnabled(controls_enabled)
        edit_selected_btn.setEnabled(True)
        up_btn.setEnabled(False)
        refresh_btn.setEnabled(False)
        upload_btn.setEnabled(False)
        download_btn.setEnabled(False)
        mkdir_btn.setEnabled(False)
        rename_btn.setEnabled(False)
        view_btn.setEnabled(False)
        delete_file_btn.setEnabled(False)

        # 保存按钮引用以便后续启用/禁用
        self.file_up_btn = up_btn
        self.file_refresh_btn = refresh_btn
        self.file_upload_btn = upload_btn
        self.file_download_btn = download_btn
        self.file_mkdir_btn = mkdir_btn
        self.file_rename_btn = rename_btn
        self.file_view_btn = view_btn
        self.file_delete_file_btn = delete_file_btn
        self.file_connect_btn = connect_btn

        # 如果有已保存的服务器，尝试自动连接
        if saved_servers:
            target_server_id = self.current_server_id or saved_servers[0].id
            combo_index = self.file_server_combo.findData(target_server_id)
            if combo_index >= 0:
                self.file_server_combo.setCurrentIndex(combo_index)
            self.file_server_combo.currentIndexChanged.connect(self.on_file_browser_server_changed)
            if self.file_server_combo.currentData():
                if self._connect_to_saved_server(self.file_server_combo.currentData(), show_feedback=False):
                    up_btn.setEnabled(True)
                    refresh_btn.setEnabled(True)
                    upload_btn.setEnabled(True)
                    download_btn.setEnabled(True)
                    mkdir_btn.setEnabled(True)
                    rename_btn.setEnabled(True)
                    view_btn.setEnabled(True)
                    delete_file_btn.setEnabled(True)
                    self.file_browser_panel.refresh_files()
        else:
            self.content_layout.addStretch()

    def _is_remote_connected(self) -> bool:
        try:
            if not self.ssh_client or not self.ssh_client.client:
                return False
            transport = self.ssh_client.client.get_transport()
            return bool(transport and transport.is_active())
        except Exception:
            return False

    def _ensure_remote_connected(self, show_feedback: bool = True) -> bool:
        connect_timeout = 10 if show_feedback else 2
        if self._is_remote_connected():
            if self.remote_manager is None:
                self.remote_manager = RemoteEnvironmentManager(self.ssh_client)
            return True

        if self.current_server_id and self._connect_to_saved_server(
            self.current_server_id,
            show_feedback=show_feedback,
            timeout=connect_timeout,
        ):
            return True

        servers = self.db.list_servers()
        if servers and self._connect_to_server_config(servers[0], timeout=connect_timeout):
            if show_feedback:
                self.statusBar().showMessage(
                    f"{servers[0].name} 已连接" if i18n.current_lang == "zh" else f"Connected to {servers[0].name}",
                    3000,
                )
            return True

        if show_feedback:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "请先配置并连接远程服务器" if i18n.current_lang == "zh" else "Please configure and connect to a remote server first",
            )
        return False

    def handle_file_browser_connect(self):
        """处理文件浏览器的连接按钮"""
        server_id = self.file_server_combo.currentData()
        if not server_id:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "请先选择一个服务器" if i18n.current_lang == "zh" else "Please select a server first"
            )
            return
        
        if self._connect_to_saved_server(server_id, show_feedback=True):
            # 启用文件操作按钮
            self.file_up_btn.setEnabled(True)
            self.file_refresh_btn.setEnabled(True)
            self.file_upload_btn.setEnabled(True)
            self.file_download_btn.setEnabled(True)
            self.file_mkdir_btn.setEnabled(True)
            self.file_rename_btn.setEnabled(True)
            self.file_view_btn.setEnabled(True)
            self.file_delete_file_btn.setEnabled(True)
            self.file_browser_panel.refresh_files()

    def refresh_file_browser_connections(self):
        """刷新文件浏览器的连接列表"""
        if hasattr(self, 'file_server_combo'):
            current_data = self.file_server_combo.currentData()
            self.file_server_combo.blockSignals(True)
            self.file_server_combo.clear()
            self.file_server_combo.addItem(
                "请选择服务器" if i18n.current_lang == "zh" else "Select server",
                None,
            )
            saved_servers = self.db.list_servers()
            for server in saved_servers:
                self.file_server_combo.addItem(server.name, server.id)
            
            if current_data:
                index = self.file_server_combo.findData(current_data)
                if index >= 0:
                    self.file_server_combo.setCurrentIndex(index)
            
            self.file_server_combo.blockSignals(False)
            
            controls_enabled = bool(saved_servers)
            self.file_server_combo.setEnabled(controls_enabled)
            self.file_connect_btn.setEnabled(controls_enabled)

    def delete_file_browser_connection(self):
        """删除选中的服务器连接"""
        server_id = self.file_server_combo.currentData()
        if not server_id:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "请先选择要删除的服务器" if i18n.current_lang == "zh" else "Please select a server to delete"
            )
            return
        
        # 获取服务器名称用于确认对话框
        server_name = self.file_server_combo.currentText()
        
        # 确认删除
        reply = QMessageBox.question(
            self,
            i18n.t("confirm_delete_title"),
            f"确定要删除服务器连接 '{server_name}' 吗？" if i18n.current_lang == "zh" 
            else f"Are you sure you want to delete server connection '{server_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 如果当前连接的是要删除的服务器，先断开连接
            if self.current_server_id == server_id:
                self.ssh_client.disconnect()
                self.current_server_id = None
                self.remote_manager = None
                # 禁用文件操作按钮
                if hasattr(self, 'file_up_btn'):
                    self.file_up_btn.setEnabled(False)
                    self.file_refresh_btn.setEnabled(False)
                    self.file_upload_btn.setEnabled(False)
                    self.file_download_btn.setEnabled(False)
                    self.file_mkdir_btn.setEnabled(False)
                    self.file_rename_btn.setEnabled(False)
                    self.file_view_btn.setEnabled(False)
                    self.file_delete_file_btn.setEnabled(False)
            
            # 从数据库删除
            self.db.delete_server(server_id)
            
            # 刷新连接列表
            self.refresh_file_browser_connections()
            
            # 显示成功消息
            self._show_info_box(
                i18n.t("msg_success"),
                f"服务器连接 '{server_name}' 已删除" if i18n.current_lang == "zh"
                else f"Server connection '{server_name}' has been deleted"
            )




    def clear_content_area(self):
        """清空内容区域"""
        # 递归清理所有子部件
        def clear_layout(layout):
            if layout is not None:
                while layout.count():
                    item = layout.takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.setParent(None)
                        widget.deleteLater()
                    elif item.layout():
                        clear_layout(item.layout())
        
        clear_layout(self.content_layout)
        
        # 强制处理待删除的对象
        QApplication.processEvents()



    def handle_wsl_config(self):
        current_config = {
            'distro': self.wsl_manager.distro_name if hasattr(self.wsl_manager, 'distro_name') else None,
            'username': self.wsl_manager.username if hasattr(self.wsl_manager, 'username') else None,
            'password': self.wsl_manager.password if hasattr(self.wsl_manager, 'password') else None,
        }
        
        dialog = ConnectionConfigDialog('wsl', self, current_config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            
            self.wsl_manager = WSLEnvironmentManager(
                distro_name=config['distro'],
                username=config['username'],
                password=config['password']
            )
            
            # 同步更新 WSL Builder 配置
            if hasattr(self, '_wsl_builder'):
                self._wsl_builder.update_config(
                    distro_name=config['distro'],
                    username=config['username'],
                    conda_path_finder=self.wsl_manager._find_conda_path if hasattr(self.wsl_manager, '_find_conda_path') else None,
                )
            
            self.db.save_wsl_config(
                distro_name=config['distro'],
                username=config['username'],
                password=config['password']
            )
            
            distro_name = config['distro'] if config['distro'] else ("默认" if i18n.current_lang == "zh" else "Default")
            username_info = f" (用户: {config['username']})" if config['username'] else ""
            self._show_info_box(
                "成功" if i18n.current_lang == "zh" else "Success",
                f"已配置WSL: {distro_name}{username_info}" if i18n.current_lang == "zh" 
                else f"WSL configured: {distro_name}{username_info}"
            )
            
            if self.current_env_type == "wsl":
                self.refresh_list("wsl")

    def handle_new_connection(self):
        dialog = ConnectionConfigDialog('remote', self, db=self.db)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            conn = SSHConnection(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password if config.auth_type == "password" else None,
                key_path=config.key_path if config.auth_type != "password" else None,
            )
            if self.ssh_client.connect(conn):
                self.current_server_id = config.id
                self.remote_manager = RemoteEnvironmentManager(self.ssh_client)
                self.refresh_file_browser_connections()
                if hasattr(self, 'file_server_combo'):
                    idx = self.file_server_combo.findData(config.id)
                    if idx >= 0:
                        self.file_server_combo.setCurrentIndex(idx)
                if hasattr(self, 'file_browser_panel'):
                    self.file_up_btn.setEnabled(True)
                    self.file_refresh_btn.setEnabled(True)
                    self.file_upload_btn.setEnabled(True)
                    self.file_download_btn.setEnabled(True)
                    self.file_mkdir_btn.setEnabled(True)
                    self.file_rename_btn.setEnabled(True)
                    self.file_view_btn.setEnabled(True)
                    self.file_delete_file_btn.setEnabled(True)
                    self.file_browser_panel.refresh_files()
                self._show_info_box(
                    "成功" if i18n.current_lang == "zh" else "Success",
                    "已连接到远程服务器" if i18n.current_lang == "zh" else "Connected to remote server"
                )
            else:
                self.refresh_file_browser_connections()
                QMessageBox.critical(
                    self,
                    "错误" if i18n.current_lang == "zh" else "Error",
                    "连接失败，请检查配置" if i18n.current_lang == "zh" else "Connection failed, please check configuration"
                )

    def handle_edit_selected_connection(self):
        if not hasattr(self, 'file_server_combo'):
            return
        server_id = self.file_server_combo.currentData()
        if not server_id:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "请先选择一个服务器" if i18n.current_lang == "zh" else "Please select a server first"
            )
            return
        server_config = self.db.get_server(server_id)
        if not server_config:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "未找到服务器配置" if i18n.current_lang == "zh" else "Server config not found"
            )
            return
        dialog = ConnectionConfigDialog('remote', self, db=self.db, server_config=server_config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            conn = SSHConnection(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password if config.auth_type == "password" else None,
                key_path=config.key_path if config.auth_type != "password" else None,
            )
            if self.ssh_client.connect(conn):
                self.current_server_id = config.id
                self.remote_manager = RemoteEnvironmentManager(self.ssh_client)
                self.refresh_file_browser_connections()
                if hasattr(self, 'file_server_combo'):
                    idx = self.file_server_combo.findData(config.id)
                    if idx >= 0:
                        self.file_server_combo.setCurrentIndex(idx)
                if hasattr(self, 'file_browser_panel'):
                    self.file_up_btn.setEnabled(True)
                    self.file_refresh_btn.setEnabled(True)
                    self.file_upload_btn.setEnabled(True)
                    self.file_download_btn.setEnabled(True)
                    self.file_mkdir_btn.setEnabled(True)
                    self.file_rename_btn.setEnabled(True)
                    self.file_view_btn.setEnabled(True)
                    self.file_delete_file_btn.setEnabled(True)
                    self.file_browser_panel.refresh_files()
                self._show_info_box(
                    "成功" if i18n.current_lang == "zh" else "Success",
                    "连接已更新并重新连接" if i18n.current_lang == "zh" else "Connection updated and reconnected"
                )
            else:
                self.refresh_file_browser_connections()
                QMessageBox.critical(
                    self,
                    "错误" if i18n.current_lang == "zh" else "Error",
                    "连接失败，请检查配置" if i18n.current_lang == "zh" else "Connection failed, please check configuration"
                )
    
    def handle_remote_config(self):
        # 加载已保存的第一个服务器配置（如有），预填到对话框
        existing_servers = self.db.list_servers()
        existing_server = existing_servers[0] if existing_servers else None
        dialog = ConnectionConfigDialog('remote', self, db=self.db, server_config=existing_server)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            if self._connect_to_server_config(config):
                self._show_info_box(
                    "成功" if i18n.current_lang == "zh" else "Success",
                    "远程服务器配置已保存并连接成功" if i18n.current_lang == "zh" else "Remote server configured and connected successfully"
                )
                if self.current_env_type == "remote":
                    self.refresh_list("remote")
            else:
                QMessageBox.warning(
                    self,
                    "警告" if i18n.current_lang == "zh" else "Warning",
                    "配置已保存，但连接失败。请检查配置后重试。" if i18n.current_lang == "zh" else "Configuration saved, but connection failed. Please check and retry."
                )
    
    def _auto_connect_remote_server(self):
        """后台短超时连接已保存的远程服务器，避免启动阻塞。"""
        servers = self.db.list_servers()
        if not servers or self._is_remote_connected():
            return

        server = servers[0]

        def connect_saved_server():
            client = SSHClient()
            conn = SSHConnection(
                host=server.host,
                port=server.port,
                username=server.username,
                password=server.password if server.auth_type == "password" else None,
                key_path=server.key_path if server.auth_type != "password" else None,
            )
            if client.connect(conn, timeout=2, banner_timeout=2, auth_timeout=2):
                return server, client
            client.disconnect()
            return None

        self._execute_worker(connect_saved_server, self._on_auto_connect_finished)

    def _on_auto_connect_finished(self, result):
        if not result:
            return
        server, client = result
        self.ssh_client.disconnect()
        self.ssh_client = client
        self.current_server_id = server.id
        self.remote_manager = RemoteEnvironmentManager(self.ssh_client)
        file_browser = getattr(self, "file_browser_panel", None)
        if file_browser is not None and shiboken6.isValid(file_browser):
            file_browser.ssh_client = self.ssh_client
        self.statusBar().showMessage(
            f"{server.name} 已自动连接" if i18n.current_lang == "zh" else f"Auto-connected to {server.name}",
            3000,
        )
    
    def _connect_to_server_config(self, config: RemoteServerConfig, timeout: int = 10) -> bool:
        """连接到指定的服务器配置"""
        from src.ssh_client import SSHConnection
        
        conn = SSHConnection(
            host=config.host,
            port=config.port,
            username=config.username,
            password=config.password if config.auth_type == "password" else None,
            key_path=config.key_path if config.auth_type != "password" else None,
        )
        
        if self.ssh_client.connect(conn, timeout=timeout, banner_timeout=timeout, auth_timeout=timeout):
            self.current_server_id = config.id
            self.remote_manager = RemoteEnvironmentManager(self.ssh_client)
            return True
        return False

    def _connect_to_saved_server(self, server_id: str, show_feedback: bool = True, timeout: int = 10) -> bool:
        saved_servers = self.db.list_servers()
        server = next((item for item in saved_servers if item.id == server_id), None)
        if not server:
            return False

        conn = SSHConnection(
            host=server.host,
            port=server.port,
            username=server.username,
            password=server.password if server.auth_type == "password" else None,
            key_path=server.key_path if server.auth_type != "password" else None,
        )
        if self.ssh_client.connect(conn, timeout=timeout, banner_timeout=timeout, auth_timeout=timeout):
            self.current_server_id = server.id
            self.remote_manager = RemoteEnvironmentManager(self.ssh_client)
            if show_feedback:
                self.statusBar().showMessage(
                    f"{server.name} 已连接" if i18n.current_lang == "zh" else f"Connected to {server.name}",
                    3000,
                )
            return True
        return False

    def on_file_browser_server_changed(self, index):
        server_id = self.file_server_combo.itemData(index)
        if not server_id:
            return
        if self._connect_to_saved_server(server_id, show_feedback=False):
            self.file_up_btn.setEnabled(True)
            self.file_refresh_btn.setEnabled(True)
            self.file_upload_btn.setEnabled(True)
            self.file_download_btn.setEnabled(True)
            self.file_mkdir_btn.setEnabled(True)
            self.file_rename_btn.setEnabled(True)
            self.file_view_btn.setEnabled(True)
            self.file_delete_file_btn.setEnabled(True)
            self.file_browser_panel.refresh_files()
        else:
            QMessageBox.critical(
                self,
                "错误" if i18n.current_lang == "zh" else "Error",
                "连接服务器失败" if i18n.current_lang == "zh" else "Failed to connect to server",
            )

    def on_file_browser_path_changed(self, path: str):
        prefix = "当前路径: " if i18n.current_lang == "zh" else "Path: "
        self.file_path_label.setText(prefix + path)

    def show_package_panel(self, env_type: str):
        table = getattr(self, f"{env_type}_table", None)
        if table is None:
            return
        selected = table.selectedItems()
        if not selected:
            # 如果没有选中，隐藏面板
            package_container = getattr(self, f"{env_type}_package_container")
            package_container.setVisible(False)
            return

        # Get selected environment info
        row = table.currentRow()
        env_name = table.item(row, 0).text()
        env_path = table.item(row, 2).text()
        use_conda = table.item(row, 3).text() == "conda"
        # 获取对应标签页的容器
        package_container = getattr(self, f"{env_type}_package_container")
        
        # Clear container
        layout = package_container.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        # Create panel
        if env_type == "remote":
            if not self.remote_manager:
                QMessageBox.warning(self, i18n.t("msg_warning"), i18n.t("msg_connect_first"))
                return
            manager = self.remote_manager
        else:
            manager = self.local_manager if env_type == "local" else self.wsl_manager

        # 创建关闭回调
        def close_callback():
            self.hide_package_panel(env_type)
        
        # 确保镜像管理器数据是最新的
        if self.mirror_manager and self.db:
            self.mirror_manager._load_from_db()
        
        panel = PackageManagementPanel(
            manager,
            env_name,
            env_path,
            use_conda,
            close_callback,
            self.mirror_manager,
            self.current_theme,
            packages_changed_callback=lambda: self.refresh_environment_packages(
                env_type,
                env_name,
                env_path,
                use_conda,
            ),
        )
        
        container_layout = package_container.layout()
        if container_layout:
            container_layout.addWidget(panel)
        
        # 显示面板并设置 70/30 分割（表格70%，面板30%）
        package_container.setVisible(True)
        splitter = getattr(self, f"{env_type}_splitter")
        total_height = splitter.height()
        splitter.setSizes([int(total_height * 0.70), int(total_height * 0.30)])
    
    def hide_package_panel(self, env_type: str):
        """隐藏包管理面板"""
        package_container = getattr(self, f"{env_type}_package_container")
        layout = package_container.layout()
        if layout:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
        package_container.setVisible(False)

    def refresh_environment_packages(self, env_type: str, env_name: str, env_path: str, use_conda: bool):
        """Refresh only the environment whose packages changed."""
        self.set_status_message(
            i18n.t("status_pkg_loading").format(env_name)
            if hasattr(i18n, "t")
            else f"Loading packages for {env_name}..."
        )

        def scan_packages():
            return self._get_manager(env_type)._get_installed_packages(env_path, use_conda, env_name)

        self._execute_worker(
            scan_packages,
            lambda packages: self.on_environment_packages_refreshed(
                env_type,
                env_name,
                env_path,
                use_conda,
                packages,
            ),
            lambda err: QMessageBox.critical(self, i18n.t("msg_error"), f"Failed: {err}"),
            error_message=lambda err: (
                f"刷新 {env_name} 软件包失败: {err}"
                if i18n.current_lang == "zh"
                else f"Failed to refresh packages for {env_name}: {err}"
            ),
        )

    def on_environment_packages_refreshed(
        self,
        env_type: str,
        env_name: str,
        env_path: str,
        use_conda: bool,
        packages,
    ):
        packages = list(packages or [])
        table = self._get_live_widget_attr(f"{env_type}_table")
        visible_envs = list(table.property("visible_envs") or []) if table else []

        env_ref = next(
            (
                env for env in visible_envs
                if str(getattr(env, "location", "")) == str(env_path)
                or (
                    str(getattr(env, "name", "")) == str(env_name)
                    and str(getattr(env, "env_type", env_type)) == str(env_type)
                )
            ),
            None,
        )
        if env_ref is None and env_type != "remote":
            env_ref = self.db.get_environment_by_location(env_path)

        metadata = getattr(env_ref, "metadata_json", None)
        if metadata is None:
            metadata = getattr(env_ref, "metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}

        env_info = EnvironmentInfo(
            id=str(getattr(env_ref, "id", "") or uuid.uuid4()),
            name=str(getattr(env_ref, "name", env_name) or env_name),
            python_version=str(getattr(env_ref, "python_version", "Unknown") or "Unknown"),
            location=str(getattr(env_ref, "location", env_path) or env_path),
            env_type=env_type,
            packages=packages,
            created_at=str(getattr(env_ref, "created_at", "") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            size_mb=float(getattr(env_ref, "size_mb", 0.0) or 0.0),
            tool=str(getattr(env_ref, "tool", "conda" if use_conda else "venv") or ("conda" if use_conda else "venv")),
            metadata=metadata,
        )
        self.db.save_environment(env_info)

        if table:
            for row in range(table.rowCount()):
                location_item = table.item(row, 2)
                name_item = table.item(row, 0)
                if (
                    location_item
                    and str(location_item.text()) == str(env_path)
                ) or (
                    name_item
                    and str(name_item.text()) == str(env_name)
                ):
                    table.setItem(row, 4, self._create_table_item(len(packages), Qt.AlignmentFlag.AlignCenter))
                    break

            for env in visible_envs:
                if str(getattr(env, "location", "")) == str(env_path):
                    env.packages = packages
                    break
            table.setProperty("visible_envs", visible_envs)

        self.set_status_message(
            (
                f"{env_name} 软件包数量已更新: {len(packages)}"
                if i18n.current_lang == "zh"
                else f"{env_name} package count updated: {len(packages)}"
            ),
            3000,
        )




    def _get_manager(self, env_type: str):
        """获取对应类型的环境管理器"""
        if env_type == "local":
            return self.local_manager
        elif env_type == "wsl":
            return self.wsl_manager
        elif env_type == "remote":
            if not self.remote_manager:
                raise Exception("Not connected to remote server")
            return self.remote_manager
        raise ValueError(f"Unknown environment type: {env_type}")

    def _get_conda_path(self, env_type: str) -> str:
        """Resolve the best conda executable path for a given environment type."""
        try:
            if env_type == "local":
                return self.local_manager._find_conda_path()
            if env_type == "wsl":
                return self.wsl_manager._find_conda_path()
            if env_type == "remote" and self.remote_manager:
                return self.remote_manager._find_conda_path()
        except Exception:
            pass
        return "conda"

    def _find_environment_by_name(self, env_type: str, env_name: str):
        """Find a freshly created or cloned environment by name."""
        try:
            manager = self._get_manager(env_type)
            location = self._get_default_location(env_type)
            envs = manager.list_environments(location)
            for env in envs:
                if env.name == env_name:
                    return env
        except Exception:
            return None
        return None

    def _mirror_url_for_selection(self, mirror_id, use_conda: bool):
        target_type = ToolType.CONDA if use_conda else ToolType.VENV
        if self.mirror_manager:
            self.mirror_manager._load_from_db()
            if mirror_id:
                for mirror in self.mirror_manager.list_mirrors(target_type):
                    if mirror.id == mirror_id:
                        return mirror.url
            default_mirror = self.mirror_manager.get_default_mirror(target_type)
            if default_mirror:
                return default_mirror.url
        return None
    
    def handle_create(self, env_type: str):
        self.mirror_manager._load_from_db()

        if env_type == "remote" and not self.remote_manager:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "请先配置并连接远程服务器" if i18n.current_lang == "zh" else "Please configure and connect to a remote server first",
            )
            return
        
        dialog = CreateEnvDialog(self, self.mirror_manager)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        data = dialog.get_data()
        if not data["name"].strip():
            QMessageBox.warning(self, i18n.t("msg_warning"), i18n.t("msg_name_empty"))
            return
        data["location"] = self._get_default_location(env_type)
        use_conda = data["tool"] == "conda"
        mirror_url = self._mirror_url_for_selection(data.get("mirror_id"), use_conda)

        def create_env():
            manager = self._get_manager(env_type)
            return manager.create_environment(data["name"], data["version"], data["location"], use_conda, mirror_url)

        self._execute_worker(
            create_env,
            lambda env: self.on_create_finished(env, env_type),
            lambda err: QMessageBox.critical(self, i18n.t("msg_error"), f"Failed: {err}"),
            start_message=i18n.t("status_creating").format(data["name"]),
            error_message=lambda err: i18n.t("status_create_failed").format(data["name"], err),
        )


    def set_status_message(self, message: str, timeout: int = 0):
        """统一更新左下角状态栏文本。"""
        self.statusBar().showMessage(message, timeout)

    def _get_live_widget_attr(self, attr_name: str):
        """返回仍然有效的 Qt 控件引用，避免访问已销毁对象。"""
        widget = getattr(self, attr_name, None)
        if widget is None:
            return None
        if not shiboken6.isValid(widget):
            setattr(self, attr_name, None)
            return None
        return widget

    def _execute_worker(self, func, on_success=None, on_error=None, start_message=None,
                        error_message=None, error_timeout=5000):
        """执行后台任务的通用方法"""
        if start_message:
            self.set_status_message(start_message)

        worker = Worker(func)
        self.workers.append(worker)
        
        if on_success:
            worker.result.connect(on_success)
        if on_error:
            worker.error.connect(on_error)
        if error_message:
            worker.error.connect(
                lambda err: self.set_status_message(
                    error_message(err) if callable(error_message) else error_message,
                    error_timeout,
                )
            )
        
        worker.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()
        return worker
    
    def closeEvent(self, event):
        # Stop all running workers
        for worker in self.workers:
            if worker.isRunning():
                worker.quit()
                worker.wait()
        if hasattr(self, "db") and hasattr(self.db, "close"):
            try:
                self.db.close()
            except Exception:
                pass
        event.accept()

    def on_create_finished(self, env_info, env_type):
        env_info.env_type = env_type
        self.db.save_environment(env_info)
        self.set_status_message(i18n.t("status_create_done").format(env_info.name), 3000)
        self._show_info_box(
            "成功" if i18n.current_lang == "zh" else "Success",
            f"环境 {env_info.name} 创建成功！" if i18n.current_lang == "zh" else f"Environment {env_info.name} created successfully!"
        )
        self.scan_all_environments()

    def _scan_conda_envs(self, env_type: str):
        """扫描 conda 环境"""
        try:
            manager = self._get_manager(env_type)
            envs = manager._list_conda_environments()
            for env in envs:
                env.env_type = env_type
            return envs
        except Exception as exc:
            logger.warning("Failed to query %s conda environments: %s", env_type, exc)
            return []

    def _scan_local_directory_envs(self, locations):
        """扫描本地目录下的 venv/conda 环境，避免重复执行 conda env list。"""
        envs = []
        scanned_locations = set()
        for location in locations:
            location = os.path.normpath(os.path.expanduser(location))
            location_key = os.path.normcase(location)
            if location_key in scanned_locations or not os.path.isdir(location):
                continue
            scanned_locations.add(location_key)

            try:
                entries = os.listdir(location)
            except OSError as exc:
                logger.debug("Failed to list local env location %s: %s", location, exc)
                continue

            for name in entries:
                item_path = os.path.join(location, name)
                if not os.path.isdir(item_path):
                    continue

                is_conda = os.path.isdir(os.path.join(item_path, "conda-meta"))
                has_python = (
                    os.path.exists(os.path.join(item_path, "Scripts", "python.exe"))
                    or os.path.exists(os.path.join(item_path, "bin", "python"))
                )
                if not (is_conda or has_python):
                    continue

                packages = self.local_manager._get_installed_packages(item_path, is_conda, name)
                envs.append(EnvironmentInfo(
                    id=str(uuid.uuid4()),
                    name=name,
                    python_version=self.local_manager._get_python_version(item_path),
                    location=item_path,
                    env_type="local",
                    packages=packages,
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    size_mb=0.0,
                    tool="conda" if is_conda else "venv",
                    metadata={"source": "directory_scan"},
                ))
        return envs
    
    def _scan_venv_envs(self, env_type: str):
        """扫描 venv 环境"""
        envs = []
        
        if env_type == "local":
            common_locations = [
                os.path.expanduser("~/python_envs"),
                os.path.expanduser("~/.virtualenvs"),
                os.path.expanduser("~/venvs"),
                os.path.join(os.getcwd(), "venv"),
                os.path.join(os.getcwd(), ".venv"),
            ]
            envs.extend(self._scan_local_directory_envs(common_locations))
        
        elif env_type == "wsl":
            # WSL环境扫描常见路径
            wsl_locations = [
                "~/python_envs",
                "~/.virtualenvs",
                "~/venvs",
                "/opt/python_envs",
                "/home/*/python_envs",
                "/home/*/.virtualenvs",
                "/home/*/venvs",
            ]
            
            scanned_paths = set()  # 避免重复扫描
            
            for location in wsl_locations:
                try:
                    # 展开通配符路径
                    if '*' in location:
                        # 使用bash展开通配符
                        expand_cmd = self.wsl_manager._build_wsl_command([
                            "bash", "-c", f"compgen -G '{location}' 2>/dev/null || echo ''"
                        ])
                        result = subprocess.run(
                            expand_cmd,
                            capture_output=True,
                            timeout=5,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                        if result.returncode == 0:
                            stdout = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
                            expanded_paths = [p.strip() for p in stdout.splitlines() if p.strip()]
                            for path in expanded_paths:
                                if path and path not in scanned_paths:
                                    scanned_paths.add(path)
                                    found = self.wsl_manager.list_environments(path)
                                    envs.extend(found)
                    else:
                        # 展开~符号
                        if location.startswith('~'):
                            expand_cmd = self.wsl_manager._build_wsl_command([
                                "bash", "-c", f"echo {location}"
                            ])
                            result = subprocess.run(
                                expand_cmd,
                                capture_output=True,
                                timeout=5,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                            )
                            if result.returncode == 0:
                                stdout = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
                                location = stdout.strip()
                        
                        if location and location not in scanned_paths:
                            scanned_paths.add(location)
                            found = self.wsl_manager.list_environments(location)
                            envs.extend(found)
                except Exception as exc:
                    logger.debug("Error scanning WSL location %s: %s", location, exc)
        
        elif env_type == "remote":
            # Remote环境扫描常见路径（与WSL相同的路径列表）
            remote_locations = [
                "~/python_envs",
                "~/.virtualenvs",
                "~/venvs",
                "~/envs",
                "/opt/python_envs",
            ]
            
            # 如果配置了默认位置，添加到扫描列表
            server = self.db.get_server(self.current_server_id) if self.current_server_id else None
            if not server:
                servers = self.db.list_servers()
                server = servers[0] if servers else None
            if server and server.default_env_location:
                default_loc = server.default_env_location
                if default_loc not in remote_locations:
                    remote_locations.insert(0, default_loc)
            
            scanned_paths = set()  # 避免重复扫描
            
            for location in remote_locations:
                try:
                    # 展开~符号
                    if location.startswith('~'):
                        stdout, stderr, exit_code = self.ssh_client.execute_command(
                            f"echo {location}",
                            timeout=5
                        )
                        if exit_code == 0:
                            location = stdout.strip()
                    
                    if location and location not in scanned_paths:
                        scanned_paths.add(location)
                        found = self.remote_manager._list_venv_environments(location)
                        envs.extend(found)
                except Exception as exc:
                    logger.debug("Error scanning remote location %s: %s", location, exc)
        
        return envs
    
    def _get_python_version(self, env_path: str, env_type: str):
        """获取 Python 版本"""
        if env_type != "local":
            return "Unknown"
        
        try:
            python_exe = os.path.join(env_path, "python.exe") if os.name == 'nt' else os.path.join(env_path, "bin", "python")
            if os.path.exists(python_exe):
                result = subprocess.run([python_exe, "--version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    version_output = result.stdout.strip() or result.stderr.strip()
                    return version_output.replace("Python ", "")
        except Exception as exc:
            logger.debug("Failed to read Python version from %s: %s", env_path, exc)
        return "Unknown"

    def _dedupe_environment_list(self, envs):
        """按路径优先去重，避免 conda 与目录扫描重复显示同一环境。"""
        deduped = []
        seen = set()
        for env in envs:
            location = str(getattr(env, "location", "") or "").rstrip("\\/")
            name = getattr(env, "name", "")
            key = location.lower() if os.name == "nt" else location
            if not key:
                key = f"{getattr(env, 'env_type', '')}:{name}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(env)
        return deduped

    def _collect_scanned_environments(self, env_type: str):
        envs = []
        envs.extend(self._scan_conda_envs(env_type))
        envs.extend(self._scan_venv_envs(env_type))
        if not envs:
            manager = self._get_manager(env_type)
            envs = manager.list_environments(self._get_default_location(env_type))
        return self._dedupe_environment_list(envs)

    def _environment_scan_key(self, env, env_type: str):
        location = str(getattr(env, "location", "") or "").rstrip("\\/")
        if location:
            if env_type == "local":
                return os.path.normcase(os.path.normpath(os.path.expanduser(location)))
            return location
        return f"{env_type}:{getattr(env, 'name', '')}"

    def _save_scanned_environments(self, envs, env_type: str, prune_missing: bool = False):
        existing_envs = self.db.list_environments(env_type)
        existing_keys = {
            self._environment_scan_key(env, env_type): env
            for env in existing_envs
        }

        new_envs = []
        updated_envs = []
        scanned_keys = set()
        for env in envs:
            env.env_type = env_type
            key = self._environment_scan_key(env, env_type)
            scanned_keys.add(key)
            if key in existing_keys:
                updated_envs.append(env)
            else:
                new_envs.append(env)
            self.db.save_environment(env)

        removed_envs = []
        if prune_missing:
            for key, existing_env in existing_keys.items():
                if key not in scanned_keys:
                    self.db.delete_environment(existing_env.id)
                    removed_envs.append(existing_env)

        return new_envs, updated_envs, removed_envs

    def _scan_complete_message(self, new_count: int, updated_count: int, removed_count: int):
        if i18n.current_lang == "zh":
            return f"扫描完成: {new_count} 个新增, {updated_count} 个更新, {removed_count} 个移除"
        return f"Scan complete: {new_count} new, {updated_count} updated, {removed_count} removed"
    
    def scan_environments(self, env_type: str):
        if env_type == "remote":
            if not self.remote_manager or not self.ssh_client.client:
                self._show_info_box(
                    "错误" if i18n.current_lang == "zh" else "Error",
                    "请先配置并连接远程服务器" if i18n.current_lang == "zh" else "Please configure and connect to remote server first"
                )
                return
        
        self.statusBar().showMessage(i18n.t("status_scanning").format(env_type))

        self._execute_worker(
            lambda: self._collect_scanned_environments(env_type),
            lambda envs: self.on_scan_finished(envs, env_type),
            lambda err: QMessageBox.critical(
                self,
                "错误" if i18n.current_lang == "zh" else "Error",
                f"扫描失败: {err}" if i18n.current_lang == "zh" else f"Scan failed: {err}"
            )
        )

    def scan_all_environments(self):
        self.set_status_message(
            "正在扫描所有环境..." if i18n.current_lang == "zh" else "Scanning all environments..."
        )

        def scan_all():
            results = []
            for env_type in ("local", "wsl", "remote"):
                if env_type == "remote" and (not self.remote_manager or not self.ssh_client.client):
                    results.append((env_type, [], False))
                    continue
                try:
                    results.append((env_type, self._collect_scanned_environments(env_type), True))
                except Exception as exc:
                    logger.warning("Failed to scan %s environments: %s", env_type, exc)
                    results.append((env_type, [], False))
            return results

        self._execute_worker(
            scan_all,
            self.on_scan_all_finished,
            lambda err: QMessageBox.critical(
                self,
                "错误" if i18n.current_lang == "zh" else "Error",
                f"扫描失败: {err}" if i18n.current_lang == "zh" else f"Scan failed: {err}",
            ),
        )

    def _get_default_location(self, env_type: str) -> str:
        if env_type == "wsl":
            return "~/python_envs"
        elif env_type == "remote":
            if self.current_server_id:
                server = self.db.get_server(self.current_server_id)
                if server and server.default_env_location:
                    return server.default_env_location

            servers = self.db.list_servers()
            if servers and servers[0].default_env_location:
                return servers[0].default_env_location
            return "~/python_envs"
        return os.path.expanduser("~/python_envs")
    
    def on_scan_finished(self, envs, env_type: str):
        new_envs, updated_envs, removed_envs = self._save_scanned_environments(
            envs,
            env_type,
            prune_missing=True,
        )
        
        self.statusBar().showMessage(
            self._scan_complete_message(len(new_envs), len(updated_envs), len(removed_envs)),
            5000
        )
        
        # 用已扫描的数据直接刷新表格，避免再次远程请求
        self.on_refresh_finished(envs, env_type)

    def on_scan_all_finished(self, results):
        total_new = 0
        total_updated = 0
        total_removed = 0
        current_envs = None
        for env_type, envs, prune_missing in results:
            if prune_missing:
                new_envs, updated_envs, removed_envs = self._save_scanned_environments(
                    envs,
                    env_type,
                    prune_missing=True,
                )
                total_new += len(new_envs)
                total_updated += len(updated_envs)
                total_removed += len(removed_envs)
            if env_type == self.current_env_type:
                current_envs = envs

        if current_envs is not None:
            self.on_refresh_finished(current_envs, self.current_env_type)
        else:
            self.refresh_list(self.current_env_type)

        self.set_status_message(
            self._scan_complete_message(total_new, total_updated, total_removed),
            5000,
        )

    def refresh_list(self, env_type: str):
        table = self._get_live_widget_attr(f"{env_type}_table")
        if table is None:
            return
        table.setRowCount(0)
        table.setProperty("visible_envs", [])

        def fetch_envs():
            if env_type == "remote":
                # 远程环境：直接从 remote_manager 获取
                if not self.remote_manager:
                    return []
                return self.remote_manager.list_environments(location=self._get_default_location("remote"))
            else:
                # 本地/WSL：从数据库获取
                self.db.deduplicate_environments(env_type)
                return self.db.list_environments(env_type)

        self.statusBar().showMessage(i18n.t("status_loading").format(env_type))
        self._execute_worker(fetch_envs, lambda envs: self.on_refresh_finished(envs, env_type),
            lambda err: QMessageBox.critical(self, "Error", f"Failed to load environments: {err}"))

    def _create_table_item(self, text: str, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter):
        """创建表格项"""
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(alignment)
        return item
    
    def on_refresh_finished(self, envs, env_type: str):
        table = self._get_live_widget_attr(f"{env_type}_table")
        if table is None:
            return
        table.setRowCount(0)
        table.setProperty("visible_envs", list(envs) if envs else [])
        
        for env in envs:
            row = table.rowCount()
            table.insertRow(row)
            
            table.setItem(row, 0, self._create_table_item(env.name))
            table.setItem(row, 1, self._create_table_item(env.python_version, Qt.AlignmentFlag.AlignCenter))
            
            location_item = self._create_table_item(env.location)
            location_item.setToolTip(str(env.location))
            table.setItem(row, 2, location_item)
            
            table.setItem(row, 3, self._create_table_item(env.tool, Qt.AlignmentFlag.AlignCenter))
            table.setItem(row, 4, self._create_table_item(len(env.packages) if env.packages else 0, Qt.AlignmentFlag.AlignCenter))
            
            table.setCellWidget(row, 5, self.create_action_buttons(env, env_type))
            table.setRowHeight(row, 44)
        
        self.statusBar().showMessage(i18n.t("status_loaded").format(len(envs), env_type), 3000)

    def add_mirror(self):
        """添加新镜像"""
        name, ok = QInputDialog.getText(self, i18n.t("mirror_add"), i18n.t("mirror_name_prompt"))
        if ok and name:
            url, ok = QInputDialog.getText(self, i18n.t("mirror_add"), i18n.t("mirror_url_prompt"))
            if ok and url:
                mirror_type, ok = QInputDialog.getItem(
                    self,
                    i18n.t("mirror_add"),
                    i18n.t("mirror_type_prompt"),
                    ["pip", "conda"],
                    0,
                    False
                )
                if ok:
                    tool_type = ToolType.VENV if mirror_type == "pip" else ToolType.CONDA
                    self.mirror_manager.add_mirror(name, url, tool_type)
                    self.refresh_mirrors()
    
    def refresh_mirrors(self):
        """刷新镜像列表"""
        self.mirror_table.setRowCount(0)
        mirrors = self.mirror_manager.list_mirrors()
        
        for mirror in mirrors:
            row = self.mirror_table.rowCount()
            self.mirror_table.insertRow(row)
            
            self.mirror_table.setItem(row, 0, QTableWidgetItem(mirror.name))
            self.mirror_table.setItem(row, 1, QTableWidgetItem(mirror.url))
            
            type_text = "pip" if mirror.mirror_type == ToolType.VENV else "conda"
            self.mirror_table.setItem(row, 2, QTableWidgetItem(type_text))
            
            # 状态显示：默认 > 已启用 > 未启用
            if hasattr(mirror, 'is_default') and mirror.is_default:
                status_text = i18n.t("mirror_default_status")
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(Qt.GlobalColor.darkBlue)
            elif mirror.is_active:
                status_text = i18n.t("mirror_enabled")
                status_item = QTableWidgetItem(status_text)
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                status_text = i18n.t("mirror_disabled")
                status_item = QTableWidgetItem(status_text)
            
            self.mirror_table.setItem(row, 3, status_item)

            availability = self.mirror_statuses.get(mirror.id)
            if availability is None:
                availability_text = "未检测" if i18n.current_lang == "zh" else "Unchecked"
                availability_item = QTableWidgetItem(availability_text)
                availability_item.setForeground(Qt.GlobalColor.gray)
            else:
                ok, message = availability
                availability_text = "可用" if (ok and i18n.current_lang == "zh") else "Available" if ok else "不可用" if i18n.current_lang == "zh" else "Unavailable"
                availability_item = QTableWidgetItem(availability_text)
                availability_item.setToolTip(message)
                availability_item.setForeground(Qt.GlobalColor.darkGreen if ok else Qt.GlobalColor.red)
            self.mirror_table.setItem(row, 4, availability_item)
    
    def _get_selected_mirror(self):
        """获取选中的镜像"""
        selected = self.mirror_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, i18n.t("msg_warning"), i18n.t("mirror_select_first"))
            return None
        
        row = self.mirror_table.currentRow()
        mirrors = self.mirror_manager.list_mirrors()
        return mirrors[row] if row < len(mirrors) else None
    
    def toggle_mirror(self):
        """切换镜像启用状态"""
        mirror = self._get_selected_mirror()
        if mirror:
            self.mirror_manager.toggle_mirror(mirror.id)
            self.refresh_mirrors()
    
    def set_default_mirror(self):
        """设置为默认镜像"""
        mirror = self._get_selected_mirror()
        if mirror:
            self.mirror_manager.set_default_mirror(mirror.id)
            self.mirror_manager._load_from_db()
            self.refresh_mirrors()
            self._show_info_box(i18n.t("msg_success"), i18n.t("mirror_default_set"))

    def check_mirror_availability(self):
        """Run mirror network checks without blocking the UI."""
        mirrors = list(self.mirror_manager.list_mirrors())
        if not mirrors:
            return

        self.set_status_message(
            "正在检查镜像可用性..." if i18n.current_lang == "zh" else "Checking mirror availability..."
        )

        def check_all():
            return {
                mirror.id: self.mirror_manager.check_mirror(mirror)
                for mirror in mirrors
            }

        def on_checked(statuses):
            self.mirror_statuses = statuses
            self.refresh_mirrors()
            failed = sum(1 for ok, _ in statuses.values() if not ok)
            if failed:
                message = (
                    f"镜像检查完成，{failed} 个不可用"
                    if i18n.current_lang == "zh"
                    else f"Mirror check complete, {failed} unavailable"
                )
            else:
                message = (
                    "镜像检查完成，全部可用"
                    if i18n.current_lang == "zh"
                    else "Mirror check complete, all available"
                )
            self.set_status_message(message, 5000)

        self._execute_worker(
            check_all,
            on_checked,
            lambda err: QMessageBox.critical(self, i18n.t("msg_error"), f"Failed: {err}"),
            error_message=lambda err: (
                f"镜像检查失败: {err}" if i18n.current_lang == "zh" else f"Mirror check failed: {err}"
            ),
        )
    
    def delete_mirror(self):
        """删除镜像"""
        mirror = self._get_selected_mirror()
        if not mirror:
            return
        
        mirror_name = self.mirror_table.item(self.mirror_table.currentRow(), 0).text()
        
        # 创建自定义消息框以支持中文按钮
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(i18n.t("msg_confirm"))
        msg_box.setText(i18n.t("mirror_confirm_delete").format(mirror_name))
        msg_box.setIcon(QMessageBox.Icon.Question)
        
        yes_btn = msg_box.addButton(
            "是" if i18n.current_lang == "zh" else "Yes",
            QMessageBox.ButtonRole.YesRole
        )
        no_btn = msg_box.addButton(
            "否" if i18n.current_lang == "zh" else "No",
            QMessageBox.ButtonRole.NoRole
        )
        msg_box.setDefaultButton(no_btn)
        
        msg_box.exec()
        
        if msg_box.clickedButton() == yes_btn:
            self.mirror_manager.delete_mirror(mirror.id)
            self.refresh_mirrors()

    def refresh_all(self):
        """刷新当前显示的环境列表"""
        if hasattr(self, 'current_env_type'):
            self.refresh_list(self.current_env_type)
    
    def _create_action_button(self, text: str, tooltip: str, width: int, callback):
        """创建操作按钮"""
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setFixedWidth(width)
        btn.clicked.connect(callback)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 禁用焦点，移除虚线框
        return btn
    
    def create_action_buttons(self, env, env_type: str):
        """创建操作按钮组件（类似 Anaconda 的快捷操作）"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)  # 统一设置按钮间距为 8px

        is_zh = i18n.current_lang == "zh"
        
        buttons = [
            ("终端" if is_zh else "CMD", "打开终端" if is_zh else "Open Terminal", 60, lambda: self.open_terminal(env, env_type)),
            ("Python", "打开 Python" if is_zh else "Open Python", 75, lambda: self.open_python(env, env_type)),
            ("Jupyter", "打开 Jupyter Notebook" if is_zh else "Open Jupyter Notebook", 75, lambda: self.open_jupyter(env, env_type)),
            ("目录" if is_zh else "Dir", "打开文件夹" if is_zh else "Open Folder", 60, lambda: self.open_folder(env, env_type)),
        ]
        
        for text, tooltip, width, callback in buttons:
            layout.addWidget(self._create_action_button(text, tooltip, width, callback))
        
        layout.addStretch()
        return widget
    
    def _get_ssh_info(self):
        """获取当前 SSH 连接信息 (host, port, username)"""
        # 优先从已保存的服务器配置获取（更可靠）
        if self.current_server_id:
            try:
                servers = self.db.list_servers()
                for s in servers:
                    if s.id == self.current_server_id:
                        return (s.host, s.port, s.username)
            except Exception as e:
                logger.debug("Failed to get SSH info from saved servers: %s", e)
        # 回退：从当前 SSH transport 获取连接信息
        try:
            if self.ssh_client and self.ssh_client.client:
                if hasattr(self.ssh_client, "connection") and self.ssh_client.connection:
                    conn = self.ssh_client.connection
                    return (conn.host, conn.port, conn.username)

                transport = self.ssh_client.client.get_transport()
                if transport and transport.is_active():
                    peername = transport.getpeername()
                    if peername:
                        host = peername[0]
                        port = peername[1] if len(peername) > 1 else 22
                        username = transport.get_username() if hasattr(transport, "get_username") else "user"
                        return (host, port, username)
        except Exception as e:
            logger.debug("Failed to get SSH info from transport: %s", e)
        return None
    
    def _get_activation_command(self, env, env_type: str, command_type: str = "terminal"):
        """生成环境激活命令（代理至 CommandLauncher）"""
        return self.command_launcher.generate_command(env, env_type, command_type)

    def _launch_environment_command(self, env, env_type: str, command_type: str):
        """通过本地 cmd.exe 启动环境相关命令。"""
        if env_type == "remote" and (not self.ssh_client or not self.ssh_client.client):
            QMessageBox.warning(self, i18n.t("msg_warning"),
                "请先连接远程服务器" if i18n.current_lang == "zh" else "Please connect to a remote server first")
            return False

        process = self.command_launcher.launch(env, env_type, command_type)
        if process is None:
            QMessageBox.warning(self, i18n.t("msg_warning"),
                "无法生成启动命令，请检查环境配置" if i18n.current_lang == "zh" else "Unable to generate launch command. Please check the environment configuration.")
            return False
        return True
    
    def open_terminal(self, env, env_type: str):
        """打开终端并激活环境"""
        try:
            if not self._launch_environment_command(env, env_type, "terminal"):
                return

            self.statusBar().showMessage(
                f"已打开终端: {env.name}" if i18n.current_lang == "zh" else f"Terminal opened: {env.name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, i18n.t("msg_error"),
                f"打开终端失败: {e}" if i18n.current_lang == "zh" else f"Failed to open terminal: {e}")
    
    def open_python(self, env, env_type: str):
        """打开 Python 交互式解释器"""
        try:
            if not self._launch_environment_command(env, env_type, "python"):
                return

            self.statusBar().showMessage(
                f"已打开 Python: {env.name}" if i18n.current_lang == "zh" else f"Python opened: {env.name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, i18n.t("msg_error"),
                f"打开 Python 失败: {e}" if i18n.current_lang == "zh" else f"Failed to open Python: {e}")
    
    def _check_jupyter_installed(self, env, env_type: str):
        """检查 Jupyter 是否已安装"""
        if env.tool == "conda" or env_type in ("wsl", "remote"):
            return True
        
        jupyter_exe = os.path.join(env.location, "Scripts", "jupyter.exe") if os.name == 'nt' else os.path.join(env.location, "bin", "jupyter")
        return os.path.exists(jupyter_exe)
    
    def open_jupyter(self, env, env_type: str):
        """打开 Jupyter Notebook"""
        try:
            if not self._check_jupyter_installed(env, env_type):
                QMessageBox.warning(self, i18n.t("msg_warning"),
                    "Jupyter 未安装。请先安装: pip install jupyter" if i18n.current_lang == "zh" 
                    else "Jupyter not installed. Please install: pip install jupyter")
                return

            if not self._launch_environment_command(env, env_type, "jupyter"):
                return

            self.statusBar().showMessage(
                f"已启动 Jupyter Notebook: {env.name}" if i18n.current_lang == "zh" else f"Jupyter Notebook started: {env.name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, i18n.t("msg_error"),
                f"打开 Jupyter 失败: {e}" if i18n.current_lang == "zh" else f"Failed to open Jupyter: {e}")
    
    def open_folder(self, env, env_type: str):
        """打开环境所在文件夹"""
        try:
            if env_type == "wsl":
                # WSL 路径转换为 Windows 可访问的 UNC 路径
                distro_name = self.wsl_manager.distro_name or "Ubuntu"
                path = f"\\\\wsl$\\{distro_name}{env.location}" if os.name == 'nt' else env.location
            elif env_type == "remote":
                # 远程环境：通过文件浏览器面板展示，或直接提示路径
                self._show_info_box(i18n.t("msg_info"),
                    f"远程路径: {env.location}\n请使用左侧「文件浏览器」查看" if i18n.current_lang == "zh"
                    else f"Remote path: {env.location}\nUse the 'File Browser' panel on the left to browse.")
                return
            else:
                path = env.location

            if os.name == 'nt':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])

            self.statusBar().showMessage(
                f"已打开文件夹: {env.location}" if i18n.current_lang == "zh" else f"Folder opened: {env.location}", 3000)
        except Exception as e:
            QMessageBox.critical(self, i18n.t("msg_error"),
                f"打开文件夹失败: {e}" if i18n.current_lang == "zh" else f"Failed to open folder: {e}")


    def handle_delete(self, env_type: str):
        """删除选中的环境"""
        table = getattr(self, f"{env_type}_table", None)
        if table is None:
            return
        selected = table.selectedItems()
        if not selected:
            QMessageBox.warning(self, i18n.t("msg_warning"), i18n.t("msg_select_env"))
            return
        
        row = table.currentRow()
        env_name = table.item(row, 0).text()
        env_path = table.item(row, 2).text()
        use_conda = table.item(row, 3).text() == "conda"
        
        # 创建自定义消息框以支持中文按钮
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(i18n.t("confirm_delete_title"))
        msg_box.setText(i18n.t("confirm_delete_msg").format(env_name, env_path))
        msg_box.setIcon(QMessageBox.Icon.Question)
        
        yes_btn = msg_box.addButton(
            "是" if i18n.current_lang == "zh" else "Yes",
            QMessageBox.ButtonRole.YesRole
        )
        no_btn = msg_box.addButton(
            "否" if i18n.current_lang == "zh" else "No",
            QMessageBox.ButtonRole.NoRole
        )
        msg_box.setDefaultButton(no_btn)
        
        msg_box.exec()
        
        if msg_box.clickedButton() != yes_btn:
            return
        
        self.set_status_message(i18n.t("status_deleting").format(env_name))
        
        def delete_env():
            manager = self._get_manager(env_type)
            return manager.delete_environment(env_path, use_conda)
        
        self._execute_worker(
            delete_env,
            lambda: self.on_delete_finished(env_name, env_path, env_type),
            lambda err: QMessageBox.critical(self, i18n.t("msg_error"), f"Failed: {err}"),
            error_message=lambda err: i18n.t("status_delete_failed").format(env_name, err),
        )

    
    def on_delete_finished(self, env_name, env_path, env_type):
        """删除完成后的处理"""
        # 从数据库中删除
        envs = self.db.list_environments(env_type)
        for env in envs:
            if env.location == env_path:
                self.db.delete_environment(env.id)
                break
        
        self.set_status_message(i18n.t("status_delete_done").format(env_name), 3000)
        self._show_info_box(
            "成功" if i18n.current_lang == "zh" else "Success",
            f"环境 '{env_name}' 已被删除" if i18n.current_lang == "zh" else f"Environment '{env_name}' has been deleted"
        )
        self.scan_all_environments()

    def _to_wsl_path(self, path: str) -> str:
        """Convert a Windows path into a WSL-accessible path when needed."""
        if not path:
            return path
        normalized = os.path.abspath(path)
        drive, tail = os.path.splitdrive(normalized)
        if drive:
            drive_letter = drive[0].lower()
            tail = tail.replace("\\", "/")
            return f"/mnt/{drive_letter}{tail}"
        return normalized.replace("\\", "/")

    def handle_export(self, env_type: str):
        """导出环境配置"""
        table = getattr(self, f"{env_type}_table", None)
        if table is None:
            return
        selected = table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Please select an environment to export")
            return
        
        row = table.currentRow()
        env_name = table.item(row, 0).text()
        env_path = table.item(row, 2).text()
        use_conda = table.item(row, 3).text() == "conda"
        
        # 选择保存位置
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Export Environment",
            f"{env_name}_requirements.txt",
            "Text Files (*.txt);;YAML Files (*.yml *.yaml);;All Files (*.*)"
        )
        
        if not file_name:
            return
        is_yaml_export = file_name.lower().endswith((".yml", ".yaml"))
        
        export_status = i18n.t("status_exporting").format(env_name)
        
        def export_env():
            if use_conda:
                conda_args = ["env", "export", "-n", env_name] if is_yaml_export else ["list", "-n", env_name, "--export"]
                if env_type == "local":
                    conda_path = self._get_conda_path("local")
                    result = subprocess.run(
                        [conda_path] + conda_args,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode != 0:
                        raise Exception(f"Export failed: {result.stderr}")
                    return result.stdout
                elif env_type == "wsl":
                    conda_path = self._get_conda_path("wsl")
                    wsl_cmd = self.wsl_manager._build_wsl_command([conda_path] + conda_args)
                    result = subprocess.run(
                        wsl_cmd,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode != 0:
                        raise Exception(f"Export failed: {result.stderr}")
                    return result.stdout
                else:
                    conda_path = self._get_conda_path("remote")
                    remote_args = (
                        f"env export -n {self.remote_manager._quote_token(env_name)}"
                        if is_yaml_export
                        else f"list -n {self.remote_manager._quote_token(env_name)} --export"
                    )
                    exit_code, stdout, stderr = self.remote_manager.executor.execute(
                        f"{self.remote_manager._shell_path(conda_path)} {remote_args}",
                        timeout=30
                    )
                    if exit_code != 0:
                        raise Exception(f"Export failed: {stderr or stdout}")
                    return stdout
            else:
                # 使用 pip freeze
                if env_type == "local":
                    pip_exe = os.path.join(env_path, "Scripts", "pip.exe") if os.name == 'nt' else os.path.join(env_path, "bin", "pip")
                    result = subprocess.run(
                        [pip_exe, "freeze"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode != 0:
                        raise Exception(f"Export failed: {result.stderr}")
                    return result.stdout
                elif env_type == "wsl":
                    pip_exe = f"{env_path}/bin/pip"
                    wsl_cmd = self.wsl_manager._build_wsl_command([pip_exe, "freeze"])
                    result = subprocess.run(
                        wsl_cmd,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode != 0:
                        raise Exception(f"Export failed: {result.stderr}")
                    return result.stdout
                else:
                    pip_exe = f"{env_path}/bin/pip"
                    exit_code, stdout, stderr = self.remote_manager.executor.execute(
                        f"{self.remote_manager._shell_path(pip_exe)} freeze", timeout=30
                    )
                    if exit_code != 0:
                        raise Exception(f"Export failed: {stderr or stdout}")
                    return stdout
        
        self._execute_worker(
            export_env,
            lambda content: self.on_export_finished(content, file_name, env_name, env_type),
            lambda err: QMessageBox.critical(self, "Error", f"Failed to export: {err}"),
            start_message=export_status,
            error_message=lambda err: i18n.t("status_export_failed").format(env_name, err),
        )
    
    def on_export_finished(self, content, file_name, env_name, env_type):
        """导出完成后保存文件"""
        try:
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(content)
            self.set_status_message(i18n.t("status_export_done").format(env_name), 3000)
            self._show_info_box(
                "成功" if i18n.current_lang == "zh" else "Success",
                f"环境已导出到:\n{file_name}" if i18n.current_lang == "zh" else f"Environment exported to:\n{file_name}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file: {e}")
    
    def handle_import(self, env_type: str):
        """从 requirements 文件导入软件包到现有环境"""

        table = getattr(self, f"{env_type}_table", None)
        if table is None:
            return
        existing_envs = table.property("visible_envs") or self.db.list_environments(env_type)
        if not existing_envs:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                i18n.t("import_no_env") if i18n.current_lang == "zh"
                else "No existing environments found. Please create or scan an environment first."
            )
            return

        env_items = [f"{env.name}  ({env.tool}, {env.python_version}, {env.location})" for env in existing_envs]
        selected_item, ok = QInputDialog.getItem(
            self,
            i18n.t("import_title"),
            i18n.t("import_select_env") if i18n.current_lang == "zh" else "Select an existing environment:",
            env_items,
            0,
            False
        )

        if not ok or not selected_item:
            return

        selected_index = env_items.index(selected_item)
        selected_env = existing_envs[selected_index]

        env_name = selected_env.name
        env_path = selected_env.location
        use_conda = (selected_env.tool == "conda")

        file_name, _ = QFileDialog.getOpenFileName(
            self,
            i18n.t("import_title"),
            "",
            "Text Files (*.txt);;YAML Files (*.yml *.yaml);;All Files (*.*)"
        )

        if not file_name:
            return

        wsl_file_name = self._to_wsl_path(file_name) if env_type == "wsl" else file_name
        is_yaml_import = file_name.lower().endswith((".yml", ".yaml"))

        import_status = i18n.t("status_importing").format(env_name)
        self.set_status_message(
            i18n.t("status_importing").format(env_name)
        )

        def import_env():
            if use_conda:
                if env_type == "local":
                    conda_path = self._get_conda_path("local")
                    conda_args = (
                        ["env", "update", "-n", env_name, "-f", file_name, "--prune"]
                        if is_yaml_import
                        else ["install", "-n", env_name, "--file", file_name, "-y"]
                    )
                    result = subprocess.run(
                        [conda_path] + conda_args,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if result.returncode != 0:
                        raise Exception(f"Failed to install packages: {result.stderr}")
                elif env_type == "wsl":
                    conda_path = self._get_conda_path("wsl")
                    conda_args = (
                        ["env", "update", "-n", env_name, "-f", wsl_file_name, "--prune"]
                        if is_yaml_import
                        else ["install", "-n", env_name, "--file", wsl_file_name, "-y"]
                    )
                    wsl_cmd = self.wsl_manager._build_wsl_command([conda_path] + conda_args)
                    result = subprocess.run(
                        wsl_cmd,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if result.returncode != 0:
                        raise Exception(f"Failed to install packages: {result.stderr}")
                else:
                    with open(file_name, 'r', encoding='utf-8') as f:
                        requirements_content = f.read()

                    suffix = "yml" if is_yaml_import else "txt"
                    remote_temp_file = f"/tmp/pymanager_req_{uuid.uuid4().hex}.{suffix}"
                    self.remote_manager.executor.execute(
                        f"cat > {self.remote_manager._shell_path(remote_temp_file)}",
                        input_data=requirements_content,
                        timeout=10
                    )

                    conda_path = self._get_conda_path("remote")
                    remote_args = (
                        f"env update -n {self.remote_manager._quote_token(env_name)} -f {self.remote_manager._shell_path(remote_temp_file)} --prune"
                        if is_yaml_import
                        else f"install -n {self.remote_manager._quote_token(env_name)} --file {self.remote_manager._shell_path(remote_temp_file)} -y"
                    )
                    exit_code, stdout, stderr = self.remote_manager.executor.execute(
                        f"{self.remote_manager._shell_path(conda_path)} {remote_args}",
                        timeout=300
                    )
                    if exit_code != 0:
                        raise Exception(stderr or stdout)

                    self.remote_manager.executor.execute(
                        f"rm -f {self.remote_manager._shell_path(remote_temp_file)}",
                        timeout=5,
                    )
            else:
                if env_type == "local":
                    pip_exe = os.path.join(env_path, "Scripts", "pip.exe") if os.name == 'nt' else os.path.join(env_path, "bin", "pip")
                    result = subprocess.run(
                        [pip_exe, "install", "-r", file_name],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if result.returncode != 0:
                        raise Exception(f"Failed to install packages: {result.stderr}")
                elif env_type == "wsl":
                    pip_exe = f"{env_path}/bin/pip"
                    wsl_cmd = self.wsl_manager._build_wsl_command([
                        pip_exe, "install", "-r", wsl_file_name
                    ])
                    result = subprocess.run(
                        wsl_cmd,
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if result.returncode != 0:
                        raise Exception(f"Failed to install packages: {result.stderr}")
                else:
                    with open(file_name, 'r', encoding='utf-8') as f:
                        requirements_content = f.read()

                    remote_temp_file = f"/tmp/pymanager_req_{uuid.uuid4().hex}.txt"
                    self.remote_manager.executor.execute(
                        f"cat > {self.remote_manager._shell_path(remote_temp_file)}",
                        input_data=requirements_content,
                        timeout=10
                    )

                    pip_exe = f"{env_path}/bin/pip"
                    exit_code, stdout, stderr = self.remote_manager.executor.execute(
                        f"{self.remote_manager._shell_path(pip_exe)} install -r {self.remote_manager._shell_path(remote_temp_file)}",
                        timeout=300
                    )
                    if exit_code != 0:
                        raise Exception(stderr or stdout)

                    self.remote_manager.executor.execute(
                        f"rm -f {self.remote_manager._shell_path(remote_temp_file)}",
                        timeout=5,
                    )

            try:
                packages = self._get_manager(env_type)._get_installed_packages(env_path, use_conda, env_name)
            except Exception:
                packages = []

            return EnvironmentInfo(
                id=selected_env.id,
                name=env_name,
                python_version=selected_env.python_version,
                location=env_path,
                env_type=env_type,
                packages=packages,
                created_at=str(selected_env.created_at) if selected_env.created_at else "",
                size_mb=0.0,
                tool=selected_env.tool,
                metadata=selected_env.metadata_json if hasattr(selected_env, 'metadata_json') else {},
            )

        self._execute_worker(
            import_env,
            lambda env: self.on_import_finished(env, env_type),
            lambda err: QMessageBox.critical(self, "Error", f"Failed to import: {err}"),
            start_message=import_status,
            error_message=lambda err: i18n.t("status_import_failed").format(env_name, err),
        )
    
    def on_import_finished(self, env_info, env_type):
        """导入完成后的处理"""
        env_info.env_type = env_type
        self.db.save_environment(env_info)
        self.on_environment_packages_refreshed(
            env_type,
            env_info.name,
            env_info.location,
            env_info.tool == "conda",
            env_info.packages,
        )
        self.set_status_message(
            i18n.t("status_import_done").format(env_info.name) if i18n.current_lang == "zh"
            else f"Packages installed into environment '{env_info.name}'",
            3000
        )
        self._show_info_box(
            "成功" if i18n.current_lang == "zh" else "Success",
            f"软件包已安装到环境 '{env_info.name}'" if i18n.current_lang == "zh"
            else f"Packages have been installed into environment '{env_info.name}'"
        )
    
    def handle_clone(self, env_type: str):
        """克隆选中的环境"""
        table = getattr(self, f"{env_type}_table", None)
        if table is None:
            return
        selected = table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "Please select an environment to clone")
            return
        
        row = table.currentRow()
        source_name = table.item(row, 0).text()
        source_path = table.item(row, 2).text()
        use_conda = table.item(row, 3).text() == "conda"
        
        # 询问新环境名称
        new_name, ok = QInputDialog.getText(
            self,
            "Clone Environment",
            f"Enter name for the cloned environment:\n(Source: {source_name})",
            text=f"{source_name}_clone"
        )
        
        if not ok or not new_name:
            return
        
        # 检查名称是否已存在
        existing_envs = self.db.list_environments(env_type)
        if any(env.name == new_name for env in existing_envs):
            QMessageBox.warning(self, "Warning", f"Environment '{new_name}' already exists")
            return
        
        location = self._get_default_location(env_type)
        
        clone_status = i18n.t("status_cloning").format(source_name, new_name)
        
        def clone_env():
            if use_conda:
                # 使用 conda create --clone
                if env_type == "local":
                    conda_path = self._get_conda_path("local")
                    result = subprocess.run(
                        [conda_path, "create", "-n", new_name, "--clone", source_name, "-y"],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                elif env_type == "wsl":
                    # 使用WSL管理器的方法，确保使用正确的发行版、用户和conda路径
                    conda_path = self._get_conda_path("wsl")
                    wsl_cmd = self.wsl_manager._build_wsl_command([
                        conda_path, "create", "-n", new_name, "--clone", source_name, "-y"
                    ])
                    result = subprocess.run(
                        wsl_cmd,
                        capture_output=True,
                        timeout=300,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    # 手动解码输出
                    result.stdout = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
                    result.stderr = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ""
                else:
                    if not self.remote_manager:
                        raise Exception("Not connected to remote server")
                    conda_path = self._get_conda_path("remote")
                    full_command = (
                        f"{self.remote_manager._shell_path(conda_path)} create -n {self.remote_manager._quote_token(new_name)} "
                        f"--clone {self.remote_manager._quote_token(source_name)} -y"
                    )
                    stdout, stderr, exit_code = self.ssh_client.execute_command(full_command)
                    if exit_code != 0:
                        raise Exception(stderr or stdout)
                    result = type('obj', (object,), {'returncode': 0, 'stdout': stdout, 'stderr': stderr})()
                
                if result.returncode != 0:
                    raise Exception(f"Clone failed: {result.stderr}")
                
                # 获取新环境的路径
                new_path = None
                if env_type == "local":
                    conda_path = self._get_conda_path("local")
                    list_result = subprocess.run(
                        [conda_path, "env", "list"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    for line in list_result.stdout.splitlines():
                        if line.strip() and not line.startswith('#'):
                            parts = line.split()
                            if len(parts) >= 2 and parts[0] == new_name:
                                for part in parts[1:]:
                                    if os.path.sep in part or '/' in part:
                                        new_path = part
                                        break
                                break
                    cloned_env = self._find_environment_by_name(env_type, new_name)
                    if cloned_env:
                        new_path = cloned_env.location
                        if cloned_env.python_version:
                            python_version = cloned_env.python_version
                elif env_type == "wsl":
                    # 使用WSL管理器查询conda环境路径
                    conda_path = self._get_conda_path("wsl")
                    list_cmd = self.wsl_manager._build_wsl_command([conda_path, "env", "list"])
                    list_result = subprocess.run(
                        list_cmd,
                        capture_output=True,
                        timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    
                    if list_result.returncode == 0:
                        output = list_result.stdout.decode('utf-8', errors='ignore')
                        for line in output.splitlines():
                            if line.strip() and not line.startswith('#'):
                                parts = line.split()
                                if len(parts) >= 2 and parts[0] == new_name:
                                    new_path = parts[-1]  # 最后一列是路径
                                    break
                    
                    if not new_path:
                        cloned_env = self._find_environment_by_name(env_type, new_name)
                        if cloned_env:
                            new_path = cloned_env.location
                            if cloned_env.python_version:
                                python_version = cloned_env.python_version
                        else:
                            raise Exception(f"Failed to find cloned environment path for: {new_name}")
                else:
                    new_path = f"~/anaconda3/envs/{new_name}"

                if env_type == "remote":
                    cloned_env = self._find_environment_by_name(env_type, new_name)
                    if cloned_env:
                        new_path = cloned_env.location
                        if cloned_env.python_version:
                            python_version = cloned_env.python_version

                if not new_path:
                    cloned_env = self._find_environment_by_name(env_type, new_name)
                    if cloned_env:
                        new_path = cloned_env.location
                        if cloned_env.python_version:
                            python_version = cloned_env.python_version
                    else:
                        raise Exception(f"Failed to find cloned environment path for: {new_name}")
                
                # 获取 Python 版本
                python_version = "Unknown"
                try:
                    if env_type == "local":
                        python_exe = os.path.join(new_path, "python.exe") if os.name == 'nt' else os.path.join(new_path, "bin", "python")
                        if os.path.exists(python_exe):
                            ver_result = subprocess.run(
                                [python_exe, "--version"],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            if ver_result.returncode == 0:
                                python_version = ver_result.stdout.strip().replace("Python ", "")
                except Exception as exc:
                    logger.debug("Failed to read cloned environment Python version from %s: %s", new_path, exc)
                
                # 获取包列表
                if env_type == "local":
                    packages = self.local_manager._get_installed_packages(new_path, False)
                elif env_type == "wsl":
                    packages = self.wsl_manager._get_installed_packages(new_path, False)
                else:
                    packages = self.remote_manager._get_installed_packages(new_path, False)
                
                return EnvironmentInfo(
                    id=str(uuid.uuid4()),
                    name=new_name,
                    python_version=python_version,
                    location=new_path,
                    env_type=env_type,
                    packages=packages,
                    created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    size_mb=0.0,
                    tool="conda",
                    metadata={"cloned_from": source_name},
                )
            else:
                # venv 环境：导出 requirements 然后创建新环境
                # 1. 导出 requirements
                if env_type == "local":
                    pip_exe = os.path.join(source_path, "Scripts", "pip.exe") if os.name == 'nt' else os.path.join(source_path, "bin", "pip")
                    result = subprocess.run(
                        [pip_exe, "freeze"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                elif env_type == "wsl":
                    pip_exe = f"{source_path}/bin/pip"
                    freeze_cmd = self.wsl_manager._build_wsl_command([pip_exe, "freeze"])
                    result = subprocess.run(
                        freeze_cmd,
                        capture_output=True,
                        timeout=30,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    # 手动解码输出
                    result.stdout = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
                    result.stderr = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ""
                else:
                    if not self.remote_manager:
                        raise Exception("Not connected to remote server")
                    pip_exe = f"{source_path}/bin/pip"
                    full_command = f"{self.remote_manager._shell_path(pip_exe)} freeze"
                    stdout, stderr, exit_code = self.ssh_client.execute_command(full_command)
                    result = type('obj', (object,), {'returncode': exit_code, 'stdout': stdout, 'stderr': stderr})()
                
                if result.returncode != 0:
                    raise Exception(f"Failed to export packages: {result.stderr}")
                
                requirements = result.stdout
                
                # 2. 获取源环境的 Python 版本
                if env_type == "local":
                    python_exe = os.path.join(source_path, "Scripts", "python.exe") if os.name == 'nt' else os.path.join(source_path, "bin", "python")
                    ver_result = subprocess.run(
                        [python_exe, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    python_version = ver_result.stdout.strip().replace("Python ", "").split('.')[0:2]
                    python_version = '.'.join(python_version)
                elif env_type == "wsl":
                    python_exe = f"{source_path}/bin/python3"
                    ver_cmd = self.wsl_manager._build_wsl_command([python_exe, "--version"])
                    ver_result = subprocess.run(
                        ver_cmd,
                        capture_output=True,
                        timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    if ver_result.returncode == 0:
                        version_output = ver_result.stdout.decode('utf-8', errors='ignore').strip()
                        python_version = version_output.replace("Python ", "").split('.')[0:2]
                        python_version = '.'.join(python_version)
                    else:
                        python_version = "3.10"  # 默认版本
                else:
                    python_version = "3.10"  # 默认版本
                
                # 3. 创建新环境
                if env_type == "local":
                    env_info = self.local_manager.create_environment(
                        new_name, python_version, location, False
                    )
                elif env_type == "wsl":
                    env_info = self.wsl_manager.create_environment(
                        new_name, python_version, location, False
                    )
                else:
                    env_info = self.remote_manager.create_environment(
                        new_name, python_version, location, False
                    )
                
                # 4. 安装依赖
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                    f.write(requirements)
                    temp_file = f.name
                
                try:
                    new_path = env_info.location
                    if env_type == "local":
                        pip_exe = os.path.join(new_path, "Scripts", "pip.exe") if os.name == 'nt' else os.path.join(new_path, "bin", "pip")
                        result = subprocess.run(
                            [pip_exe, "install", "-r", temp_file],
                            capture_output=True,
                            text=True,
                            timeout=300
                        )
                    elif env_type == "wsl":
                        # 对于WSL，需要将Windows临时文件路径转换为WSL路径
                        # 或者直接在WSL中创建临时文件
                        pip_exe = f"{new_path}/bin/pip"
                        
                        # 在WSL中创建临时文件
                        temp_wsl_file = f"/tmp/pymanager_req_{uuid.uuid4().hex}.txt"
                        
                        # 写入requirements到WSL临时文件
                        write_cmd = self.wsl_manager._build_wsl_command([
                            "bash", "-c", f"cat > {self.wsl_manager._shell_path(temp_wsl_file)}"
                        ])
                        write_result = subprocess.run(
                            write_cmd,
                            input=requirements.encode('utf-8'),
                            capture_output=True,
                            timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                        
                        if write_result.returncode != 0:
                            raise Exception("Failed to create requirements file in WSL")
                        
                        # 安装依赖
                        install_cmd = self.wsl_manager._build_wsl_command([
                            self.wsl_manager._shell_path(pip_exe), "install", "-r", self.wsl_manager._shell_path(temp_wsl_file)
                        ])
                        result = subprocess.run(
                            install_cmd,
                            capture_output=True,
                            timeout=300,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                        
                        # 清理临时文件
                        cleanup_cmd = self.wsl_manager._build_wsl_command(["rm", "-f", self.wsl_manager._shell_path(temp_wsl_file)])
                        subprocess.run(
                            cleanup_cmd,
                            capture_output=True,
                            timeout=5,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                        )
                        
                        # 手动解码输出
                        result.stdout = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
                        result.stderr = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ""
                    else:
                        # 对于远程，使用executor上传文件并安装
                        pip_exe = f"{new_path}/bin/pip"
                        
                        remote_temp_file = f"/tmp/pymanager_req_{uuid.uuid4().hex}.txt"
                        self.remote_manager.executor.execute(
                            f"cat > {self.remote_manager._shell_path(remote_temp_file)}",
                            input_data=requirements,
                            timeout=10
                        )
                        
                        self.remote_manager.executor.execute(
                            f"{self.remote_manager._shell_path(pip_exe)} install -r {self.remote_manager._shell_path(remote_temp_file)}",
                            timeout=300
                        )
                        
                        self.remote_manager.executor.execute(
                            f"rm -f {self.remote_manager._shell_path(remote_temp_file)}",
                            timeout=5,
                        )
                
                finally:
                    os.unlink(temp_file)
                
                env_info.metadata = {"cloned_from": source_name}
                return env_info
        
        self._execute_worker(
            clone_env,
            lambda env: self.on_clone_finished(env, env_type, source_name),
            lambda err: QMessageBox.critical(self, "Error", f"Failed to clone: {err}"),
            start_message=clone_status,
            error_message=lambda err: i18n.t("status_clone_failed").format(new_name, err),
        )
    
    def on_clone_finished(self, env_info, env_type, source_name):
        """克隆完成后的处理"""
        env_info.env_type = env_type
        self.db.save_environment(env_info)
        self.set_status_message(i18n.t("status_clone_done").format(env_info.name), 3000)
        self._show_info_box(
            "成功" if i18n.current_lang == "zh" else "Success",
            f"环境 '{env_info.name}' 已从 '{source_name}' 克隆\n\n位置: {env_info.location}" if i18n.current_lang == "zh" 
            else f"Environment '{env_info.name}' has been cloned from '{source_name}'\n\nLocation: {env_info.location}"
        )
        self.scan_all_environments()
    
    
    
    
    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 加载 Qt 中文翻译
    from PySide6.QtCore import QTranslator, QLocale
    translator = QTranslator()
    if translator.load(QLocale.system(), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
