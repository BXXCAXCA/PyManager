from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QMessageBox,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QGridLayout,
)
from PySide6.QtCore import Qt
from src.worker import Worker
from src.i18n import i18n
from src.models import ToolType
from src.styles import DARK_COLORS


class PackageManagementPanel(QWidget):
    def __init__(
        self,
        manager,
        env_name,
        env_path,
        use_conda,
        parent_callback=None,
        mirror_manager=None,
        theme="light",
        packages_changed_callback=None,
    ):
        super().__init__()
        self.manager = manager
        self.env_name = env_name
        self.env_path = env_path
        self.use_conda = use_conda
        self.parent_callback = parent_callback  # 用于关闭面板
        self.mirror_manager = mirror_manager
        self.packages_changed_callback = packages_changed_callback
        self.workers = []
        self._package_load_seq = 0
        self.theme = theme  # 保存主题
        
        # 不自动填充背景，让样式表控制
        self.setAutoFillBackground(False)
        
        # 不在这里设置固定样式，让它继承父窗口的主题
        self.setObjectName("packagePanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(12)
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)
        
        # 标题栏（带关闭按钮）
        title_layout = QHBoxLayout()
        title_layout.setSpacing(0)
        
        title = QLabel(i18n.t("pkg_title"))
        title.setObjectName("section_title")
        title_layout.addWidget(title)
        title_layout.addStretch()
        
        close_btn = QPushButton("关闭" if i18n.current_lang == "zh" else "Close")
        close_btn.setMaximumWidth(50)
        close_btn.setMaximumHeight(28)
        close_btn.clicked.connect(self.close_panel)
        title_layout.addWidget(close_btn)
        
        layout.addLayout(title_layout)
        
        # 主内容区域 - 分为两栏
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)
        
        # 左栏：已安装的包（表格形式）- 占更多空间
        left_widget = QWidget()
        left_widget.setAutoFillBackground(False)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        
        # 已安装包的表格 - 增加高度
        self.package_table = QTableWidget()
        self.package_table.setColumnCount(2)  # 只要2列：包名和版本
        self.package_table.setHorizontalHeaderLabels([
            i18n.t("col_name") if i18n.current_lang == "zh" else "Package",
            i18n.t("col_version") if i18n.current_lang == "zh" else "Version"
        ])
        self.package_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.package_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 禁用表格焦点，移除虚线框
        self.package_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.package_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.package_table.setColumnWidth(1, 120)  # 版本列
        self.package_table.setMinimumHeight(200)   # 减小最小高度
        self.package_table.setAlternatingRowColors(True)
        self.package_table.verticalHeader().setVisible(True)  # 显示行号
        self.package_table.verticalHeader().setFixedWidth(60)  # 序号列宽度增加
        left_layout.addWidget(self.package_table)
        
        content_layout.addWidget(left_widget, 65)  # 左栏占 65%
        
        # 右栏：安装新包 - 占更少空间
        right_widget = QWidget()
        right_widget.setAutoFillBackground(False)
        right_widget.setMaximumWidth(280)  # 限制右栏最大宽度
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        
        # 镜像源选择（紧凑布局）
        mirror_layout = QVBoxLayout()
        mirror_layout.setSpacing(4)
        mirror_label = QLabel("🌐 " + (i18n.t("pkg_mirror") if i18n.current_lang == "zh" else "Mirror:"))
        mirror_layout.addWidget(mirror_label)
        
        self.mirror_combo = QComboBox()
        self.mirror_combo.setEnabled(True)  # 确保启用
        self.mirror_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 确保可以获得焦点
        self.mirror_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)  # 自动调整大小
        self.mirror_combo.setMinimumWidth(200)  # 设置最小宽度
        self.mirror_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)  # 不省略文本
        self.load_mirrors()  # 加载镜像列表
        
        mirror_layout.addWidget(self.mirror_combo)
        right_layout.addLayout(mirror_layout)
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        right_layout.addWidget(separator)
        
        # 安装包输入
        pkg_label = QLabel("📦 " + (i18n.t("pkg_input_label") if i18n.current_lang == "zh" else "Package:"))
        right_layout.addWidget(pkg_label)
        
        self.package_input = QLineEdit()
        self.package_input.setPlaceholderText("requests, numpy...")
        right_layout.addWidget(self.package_input)
        
        # 操作按钮（2x2 网格，紧凑布局）
        action_btn_layout = QGridLayout()
        action_btn_layout.setSpacing(6)
        
        self.search_btn = QPushButton("🔍 " + i18n.t("btn_search"))
        self.search_btn.setToolTip(
            "无输入时刷新列表，有输入时搜索已安装的软件包" if i18n.current_lang == "zh" 
            else "Refresh list when empty, search installed packages when text entered"
        )
        self.search_btn.clicked.connect(self.search_package)
        action_btn_layout.addWidget(self.search_btn, 0, 0)
        
        self.install_btn = QPushButton("➕ " + i18n.t("btn_install"))
        self.install_btn.setToolTip(
            "安装软件包" if i18n.current_lang == "zh" else "Install package"
        )
        self.install_btn.clicked.connect(self.install_package)
        action_btn_layout.addWidget(self.install_btn, 0, 1)
        
        self.delete_btn = QPushButton("🗑️ " + i18n.t("btn_uninstall"))
        self.delete_btn.setObjectName("danger")
        self.delete_btn.setToolTip(
            "卸载软件包" if i18n.current_lang == "zh" else "Uninstall package"
        )
        self.delete_btn.clicked.connect(self.uninstall_package)
        action_btn_layout.addWidget(self.delete_btn, 1, 0)
        
        self.update_btn = QPushButton("⬆️ " + i18n.t("btn_update"))
        self.update_btn.setToolTip(
            "更新软件包" if i18n.current_lang == "zh" else "Update package"
        )
        self.update_btn.clicked.connect(self.update_package)
        action_btn_layout.addWidget(self.update_btn, 1, 1)
        
        right_layout.addLayout(action_btn_layout)
        
        right_layout.addStretch()
        
        content_layout.addWidget(right_widget, 35)  # 右栏占 35%
        
        layout.addLayout(content_layout)

        # 自动加载包列表
        self.load_packages()
    
    def _show_message(self, title, message, icon=QMessageBox.Icon.Information):
        """显示带有主题样式的消息框"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(icon)
        
        # 根据主题应用样式
        if self.theme == "dark":
            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {DARK_COLORS['background']};
                    color: {DARK_COLORS['text_primary']};
                }}
                QMessageBox QLabel {{
                    color: {DARK_COLORS['text_primary']};
                    background-color: transparent;
                    font-size: 13px;
                }}
                QMessageBox QPushButton {{
                    background-color: {DARK_COLORS['primary']};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 60px;
                    min-height: 28px;
                }}
                QMessageBox QPushButton:hover {{
                    background-color: {DARK_COLORS['primary_hover']};
                }}
                QMessageBox QPushButton:pressed {{
                    background-color: #003D99;
                }}
            """)
        else:
            from src.styles import COLORS
            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {COLORS['card_bg']};
                }}
                QMessageBox QLabel {{
                    color: {COLORS['text_primary']};
                    background-color: transparent;
                    font-size: 13px;
                }}
                QMessageBox QPushButton {{
                    background-color: {COLORS['primary']};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 60px;
                    min-height: 28px;
                }}
                QMessageBox QPushButton:hover {{
                    background-color: {COLORS['primary_hover']};
                }}
            """)
        
        msg_box.exec()
    
    def _show_warning(self, title, message):
        """显示警告消息框"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        
        # 根据主题应用样式
        if self.theme == "dark":
            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {DARK_COLORS['background']};
                    color: {DARK_COLORS['text_primary']};
                }}
                QMessageBox QLabel {{
                    color: {DARK_COLORS['text_primary']};
                    background-color: transparent;
                    font-size: 13px;
                }}
                QMessageBox QPushButton {{
                    background-color: {DARK_COLORS['warning']};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 60px;
                    min-height: 28px;
                }}
                QMessageBox QPushButton:hover {{
                    background-color: #D97706;
                }}
                QMessageBox QPushButton:pressed {{
                    background-color: #B45309;
                }}
            """)
        else:
            from src.styles import COLORS
            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {COLORS['card_bg']};
                }}
                QMessageBox QLabel {{
                    color: {COLORS['text_primary']};
                    background-color: transparent;
                    font-size: 13px;
                }}
                QMessageBox QPushButton {{
                    background-color: {COLORS['warning']};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 60px;
                    min-height: 28px;
                }}
                QMessageBox QPushButton:hover {{
                    background-color: #D97706;
                }}
            """)
        
        msg_box.exec()
    
    def _show_error(self, title, message):
        """显示错误消息框"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Critical)
        
        # 根据主题应用样式
        if self.theme == "dark":
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #1E1E1E;
                    color: #E0E0E0;
                }
                QMessageBox QLabel {
                    color: #E0E0E0;
                    background-color: transparent;
                    font-size: 13px;
                }
                QMessageBox QPushButton {
                    background-color: #DC3545;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 60px;
                    min-height: 28px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #C82333;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #A71D2A;
                }
            """)
        else:
            from src.styles import COLORS
            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {COLORS['card_bg']};
                }}
                QMessageBox QLabel {{
                    color: {COLORS['text_primary']};
                    background-color: transparent;
                    font-size: 13px;
                }}
                QMessageBox QPushButton {{
                    background-color: {COLORS['danger']};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 60px;
                    min-height: 28px;
                }}
                QMessageBox QPushButton:hover {{
                    background-color: #C82333;
                }}
            """)
        
        msg_box.exec()
    
    def _show_question(self, title, message):
        """显示确认对话框"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(QMessageBox.Icon.Question)
        
        # 添加自定义按钮以支持中文
        yes_btn = msg_box.addButton(
            "是" if i18n.current_lang == "zh" else "Yes",
            QMessageBox.ButtonRole.YesRole
        )
        no_btn = msg_box.addButton(
            "否" if i18n.current_lang == "zh" else "No",
            QMessageBox.ButtonRole.NoRole
        )
        msg_box.setDefaultButton(no_btn)
        
        # 根据主题应用样式
        if self.theme == "dark":
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #1E1E1E;
                    color: #E0E0E0;
                }
                QMessageBox QLabel {
                    color: #E0E0E0;
                    background-color: transparent;
                    font-size: 13px;
                }
                QMessageBox QPushButton {
                    background-color: #3E3E42;
                    color: #E0E0E0;
                    border: 1px solid #555555;
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 60px;
                    min-height: 28px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #505050;
                    border-color: #0066FF;
                    color: #66B3FF;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #2A2A2A;
                }
                QMessageBox QPushButton:default {
                    background-color: #0066FF;
                    color: white;
                    border: none;
                }
                QMessageBox QPushButton:default:hover {
                    background-color: #0052CC;
                }
                QMessageBox QPushButton:default:pressed {
                    background-color: #003D99;
                }
            """)
        else:
            from src.styles import COLORS
            msg_box.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {COLORS['card_bg']};
                }}
                QMessageBox QLabel {{
                    color: {COLORS['text_primary']};
                    background-color: transparent;
                    font-size: 13px;
                }}
                QMessageBox QPushButton {{
                    background-color: {COLORS['card_bg']};
                    color: {COLORS['text_primary']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 6px;
                    padding: 6px 16px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 60px;
                    min-height: 28px;
                }}
                QMessageBox QPushButton:hover {{
                    background-color: {COLORS['primary_light']};
                    border-color: {COLORS['primary']};
                    color: {COLORS['primary']};
                }}
                QMessageBox QPushButton:default {{
                    background-color: {COLORS['primary']};
                    color: white;
                    border: none;
                }}
                QMessageBox QPushButton:default:hover {{
                    background-color: {COLORS['primary_hover']};
                }}
            """)
        
        msg_box.exec()
        return msg_box.clickedButton() == yes_btn
    
    def close_panel(self):
        """关闭面板"""
        if self.parent_callback:
            self.parent_callback()
        else:
            self.setVisible(False)

    def _set_status(self, message, timeout=0):
        """通过主窗口统一更新左下角状态栏。"""
        window = self.window()
        if window and hasattr(window, "set_status_message"):
            window.set_status_message(message, timeout)

    def _remove_worker(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)

    def _set_action_buttons_enabled(self, enabled: bool):
        for button in (self.search_btn, self.install_btn, self.delete_btn, self.update_btn):
            button.setEnabled(enabled)

    def _selected_package_name(self):
        row = self.package_table.currentRow()
        if row < 0:
            return None
        item = self.package_table.item(row, 0)
        if item is None or item.data(Qt.ItemDataRole.UserRole) != "package":
            return None
        return item.text().strip() or None

    def _current_mirror_url(self):
        mirror_id = self.mirror_combo.currentData()
        if not self.mirror_manager:
            return None
        if not mirror_id:
            if not hasattr(self.mirror_manager, "get_default_mirror"):
                return None
            default_mirror = self.mirror_manager.get_default_mirror(self._target_mirror_type())
            return default_mirror.url if default_mirror else None
        for mirror in self.mirror_manager.list_mirrors(self._target_mirror_type()):
            if mirror.id == mirror_id:
                return mirror.url
        return None

    def _target_mirror_type(self):
        return ToolType.CONDA if self.use_conda else ToolType.VENV
    
    def load_mirrors(self):
        """加载镜像列表 - 显示所有启用的镜像源"""
        self.mirror_combo.clear()
        self.mirror_combo.addItem(i18n.t("pkg_mirror_default"), None)
        
        # 加载所有启用的镜像（不再按工具类型过滤）
        if self.mirror_manager:
            mirrors = self.mirror_manager.list_mirrors(self._target_mirror_type())
            
            active_count = 0
            for mirror in mirrors:
                if mirror.is_active:
                    self.mirror_combo.addItem(mirror.name, mirror.id)
                    active_count += 1
            
            # 如果没有启用的镜像，添加提示
            if active_count == 0:
                mirror_name = "conda" if self.use_conda else "pip"
                hint_text = (
                    f"(请先在镜像管理中启用 {mirror_name} 镜像)"
                    if i18n.current_lang == "zh"
                    else f"(Enable {mirror_name} mirrors in Mirror Management)"
                )
                self.mirror_combo.addItem(hint_text, None)
        
        # 设置下拉列表的宽度以适应最长的文本
        max_width = 0
        for i in range(self.mirror_combo.count()):
            text = self.mirror_combo.itemText(i)
            width = self.mirror_combo.fontMetrics().horizontalAdvance(text)
            max_width = max(max_width, width)
        
        # 设置下拉列表视图的最小宽度（加上一些边距）
        self.mirror_combo.view().setMinimumWidth(max_width + 40)

    def search_package(self):
        """搜索或刷新：无输入内容时刷新列表，有输入内容时搜索已安装的库"""
        search_term = self.package_input.text().strip()
        
        if not search_term:
            # 没有输入内容时，刷新包列表
            self.load_packages()
            return
        
        # 有输入内容时，在表格中搜索匹配的包
        found_items = self.package_table.findItems(search_term, Qt.MatchFlag.MatchContains)
        
        if found_items:
            # 定位到第一个匹配项
            first_item = found_items[0]
            row = first_item.row()
            self.package_table.selectRow(row)
            self.package_table.scrollToItem(first_item, QTableWidget.ScrollHint.PositionAtCenter)
            
            # 显示搜索结果提示 - 使用主题样式
            self._show_message(
                i18n.t("btn_search"),
                i18n.t("pkg_search_found").format(len(found_items))
            )
        else:
            # 使用主题样式显示未找到的消息
            self._show_message(
                i18n.t("btn_search"),
                i18n.t("pkg_search_not_found").format(search_term)
            )
    
    def load_packages(self):
        self._package_load_seq += 1
        load_seq = self._package_load_seq
        self.package_table.setRowCount(0)
        self.package_table.setRowCount(1)
        self.package_table.setItem(0, 0, QTableWidgetItem(i18n.t("pkg_loading")))
        self.package_table.setItem(0, 1, QTableWidgetItem(""))
        self._set_status(i18n.t("status_pkg_loading").format(self.env_name))
        
        def fetch_packages():
            return load_seq, self.manager._get_installed_packages(self.env_path, self.use_conda, self.env_name)
        
        worker = Worker(fetch_packages)
        self.workers.append(worker)
        worker.result.connect(self.on_packages_loaded)
        worker.error.connect(
            lambda err: self._show_error(i18n.t("msg_error"), f"Failed to load packages: {err}")
        )
        worker.error.connect(
            lambda err: self._set_status(
                i18n.t("status_pkg_loading").format(self.env_name) + f" - {err}",
                5000,
            )
        )
        worker.finished.connect(lambda: self._remove_worker(worker))
        worker.start()
    
    def on_packages_loaded(self, result):
        """包列表加载完成"""
        if (
            isinstance(result, tuple)
            and len(result) == 2
            and isinstance(result[0], int)
        ):
            load_seq, packages = result
            if load_seq != self._package_load_seq:
                return
        else:
            packages = result

        self.package_table.setRowCount(0)
        
        if packages:
            for pkg_line in packages:
                # 解析包名和版本
                if "==" in pkg_line:
                    pkg_name, pkg_version = pkg_line.split("==", 1)
                elif " " in pkg_line:
                    parts = pkg_line.split()
                    pkg_name = parts[0]
                    pkg_version = parts[1] if len(parts) > 1 else ""
                else:
                    pkg_name = pkg_line
                    pkg_version = ""
                
                row = self.package_table.rowCount()
                self.package_table.insertRow(row)
                
                # 包名列
                name_item = QTableWidgetItem(pkg_name)
                name_item.setData(Qt.ItemDataRole.UserRole, "package")
                self.package_table.setItem(row, 0, name_item)
                
                # 版本列
                self.package_table.setItem(row, 1, QTableWidgetItem(pkg_version))
        else:
            self.package_table.setRowCount(1)
            self.package_table.setItem(0, 0, QTableWidgetItem(i18n.t("pkg_none")))
            self.package_table.setItem(0, 1, QTableWidgetItem(""))

    def install_package(self):
        package = self.package_input.text().strip()
        if not package:
            return

        # 获取选中的镜像源
        mirror_url = self._current_mirror_url()

        def do_install():
            return self.manager.install_package(self.env_name, self.env_path, package, self.use_conda, mirror_url)

        self._set_status(i18n.t("status_pkg_installing").format(package))
        worker = Worker(do_install)
        self.workers.append(worker)
        worker.result.connect(lambda _: self.on_install_finished(package))
        worker.error.connect(
            lambda err: self._show_error(i18n.t("msg_error"), f"Failed: {err}")
        )
        worker.error.connect(
            lambda err: self._set_status(
                i18n.t("status_pkg_install_failed").format(package, err),
                5000,
            )
        )
        worker.error.connect(lambda err: self.on_install_failed())
        worker.finished.connect(lambda: self._remove_worker(worker))
        worker.start()
        self._set_action_buttons_enabled(False)

    def on_install_finished(self, package):
        self.package_input.clear()
        self._set_action_buttons_enabled(True)
        self._set_status(i18n.t("status_pkg_install_done").format(package), 3000)
        # 自动刷新包列表，不显示消息框
        self.load_packages()
        self._notify_packages_changed()
    
    def on_install_failed(self):
        self._set_action_buttons_enabled(True)

    def uninstall_package(self):
        """卸载选中的包"""
        pkg_name = self._selected_package_name()
        if not pkg_name:
            self._show_warning(
                i18n.t("msg_warning"), 
                i18n.t("pkg_select_to_uninstall")
            )
            return
        
        # 确认卸载
        reply = self._show_question(
            i18n.t("msg_confirm"),
            i18n.t("pkg_confirm_uninstall").format(pkg_name)
        )
        
        if not reply:
            return
        
        def do_uninstall():
            return self.manager.uninstall_package(self.env_name, self.env_path, pkg_name, self.use_conda)
        
        self._set_status(i18n.t("status_pkg_uninstalling").format(pkg_name))
        worker = Worker(do_uninstall)
        self.workers.append(worker)
        worker.result.connect(lambda _: self.on_uninstall_finished(pkg_name))
        worker.error.connect(
            lambda err: self._show_error(i18n.t("msg_error"), f"Failed: {err}")
        )
        worker.error.connect(
            lambda err: self._set_status(
                i18n.t("status_pkg_uninstall_failed").format(pkg_name, err),
                5000,
            )
        )
        worker.error.connect(lambda err: self.on_uninstall_failed())
        worker.finished.connect(lambda: self._remove_worker(worker))
        worker.start()
        self._set_action_buttons_enabled(False)
    
    def on_uninstall_finished(self, package):
        self._set_action_buttons_enabled(True)
        self._set_status(i18n.t("status_pkg_uninstall_done").format(package), 3000)
        # 自动刷新包列表，不显示消息框
        self.load_packages()
        self._notify_packages_changed()
    
    def on_uninstall_failed(self):
        self._set_action_buttons_enabled(True)

    def update_package(self):
        """更新软件包 - 支持两种方式：点击选择或输入包名"""
        # 方式1：检查是否有输入的包名
        input_package = self.package_input.text().strip()
        
        # 方式2：检查是否有选中的包
        selected_package = self._selected_package_name()
        
        # 确定要更新的包
        package_to_update = None
        if input_package:
            # 优先使用输入的包名
            package_to_update = input_package
        elif selected_package:
            # 如果没有输入，使用选中的包
            package_to_update = selected_package
        else:
            # 两种方式都没有提供包名
            self._show_warning(
                i18n.t("msg_warning"),
                "请输入软件包名称或在列表中选择一个软件包" if i18n.current_lang == "zh" else "Please enter a package name or select a package from the list"
            )
            return
        
        # 确认更新
        reply = self._show_question(
            i18n.t("msg_confirm"),
            f"确定要更新 '{package_to_update}' 吗？" if i18n.current_lang == "zh" else f"Update '{package_to_update}'?"
        )
        
        if not reply:
            return
        
        # 获取选中的镜像源
        mirror_url = self._current_mirror_url()
        
        def do_update():
            return self.manager.update_package(self.env_name, self.env_path, package_to_update, self.use_conda, mirror_url)
        
        self._set_status(i18n.t("status_pkg_updating").format(package_to_update))
        worker = Worker(do_update)
        self.workers.append(worker)
        worker.result.connect(lambda _: self.on_update_finished(package_to_update))
        worker.error.connect(
            lambda err: self._show_error(i18n.t("msg_error"), f"更新失败: {err}" if i18n.current_lang == "zh" else f"Update failed: {err}")
        )
        worker.error.connect(
            lambda err: self._set_status(
                i18n.t("status_pkg_update_failed").format(package_to_update, err),
                5000,
            )
        )
        worker.error.connect(lambda err: self.on_update_failed())
        worker.finished.connect(lambda: self._remove_worker(worker))
        worker.start()
        self._set_action_buttons_enabled(False)
    
    def on_update_finished(self, package):
        """更新完成后的回调"""
        self.package_input.clear()
        self._set_action_buttons_enabled(True)
        self._set_status(i18n.t("status_pkg_update_done").format(package), 3000)
        # 自动刷新包列表
        self.load_packages()
        self._notify_packages_changed()
        self._show_message(
            i18n.t("msg_success") if hasattr(i18n, 't') else "成功",
            f"'{package}' 更新完成" if i18n.current_lang == "zh" else f"'{package}' updated successfully"
        )

    def on_update_failed(self):
        self._set_action_buttons_enabled(True)

    def _notify_packages_changed(self):
        if self.packages_changed_callback:
            self.packages_changed_callback()
