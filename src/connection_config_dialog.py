from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QGroupBox,
    QInputDialog,
    QSpinBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from src.environment_manager import WSLEnvironmentManager
from src.styles import GLOBAL_STYLE
from src.i18n import i18n
from src.models import RemoteServerConfig
from src.database import DatabaseManager
import uuid


class ConnectionConfigDialog(QDialog):
    def __init__(self, connection_type: str = 'wsl', parent=None,
                 current_config=None, db: DatabaseManager = None,
                 server_config: 'RemoteServerConfig' = None):
        super().__init__(parent)
        self.connection_type = connection_type
        self.current_config = current_config or {}
        self.db = db
        self.server_config = server_config
        self._scanner = None

        if connection_type == 'wsl':
            self.setWindowTitle("WSL " + ("配置" if i18n.current_lang == "zh" else "Configuration"))
        else:
            if server_config:
                self.setWindowTitle("编辑连接" if i18n.current_lang == "zh" else "Edit Connection")
            else:
                self.setWindowTitle("新建连接" if i18n.current_lang == "zh" else "New Connection")

        self.setMinimumWidth(500)
        self.setStyleSheet(parent.styleSheet() if parent else GLOBAL_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        if connection_type == 'wsl':
            self._setup_wsl_ui(layout)
        else:
            self._setup_remote_ui(layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton(i18n.t("btn_cancel"))
        cancel_btn.clicked.connect(self.reject)

        self.ok_btn = QPushButton(
            "确定" if i18n.current_lang == "zh" else "OK"
        )
        self.ok_btn.setObjectName("primary")
        self.ok_btn.clicked.connect(self._on_accept)

        if connection_type == 'remote':
            test_btn = QPushButton(
                "测试连接" if i18n.current_lang == "zh" else "Test Connection"
            )
            test_btn.clicked.connect(self._test_connection)
            btn_layout.addWidget(test_btn)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

        if connection_type == 'wsl':
            self._load_distributions()

    def _setup_wsl_ui(self, layout):
        title = QLabel("WSL " + ("配置" if i18n.current_lang == "zh" else "Configuration"))
        title.setObjectName("title")
        layout.addWidget(title)

        subtitle = QLabel(
            "选择WSL发行版并配置登录信息" if i18n.current_lang == "zh"
            else "Select WSL distribution and configure login credentials"
        )
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.distro_combo = QComboBox()
        self.distro_combo.setMinimumWidth(250)
        form_layout.addRow(
            QLabel("WSL发行版:" if i18n.current_lang == "zh" else "Distribution:"),
            self.distro_combo
        )

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(
            "例如: ubuntu, root" if i18n.current_lang == "zh" else "e.g., ubuntu, root"
        )
        if self.current_config.get('username'):
            self.username_edit.setText(self.current_config['username'])
        form_layout.addRow(
            QLabel("用户名:" if i18n.current_lang == "zh" else "Username:"),
            self.username_edit
        )

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(
            "可选，用于sudo操作" if i18n.current_lang == "zh"
            else "Optional, for sudo operations"
        )
        if self.current_config.get('password'):
            self.password_edit.setText(self.current_config['password'])
        form_layout.addRow(
            QLabel("密码:" if i18n.current_lang == "zh" else "Password:"),
            self.password_edit
        )

        layout.addLayout(form_layout)

        hint_label = QLabel(
            "💡 提示：如果WSL无响应，可以选择'手动输入'选项直接输入发行版名称"
            if i18n.current_lang == "zh"
            else "💡 Hint: If WSL is not responding, you can select 'Enter manually'"
        )
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #666; font-size: 12px; padding: 8px;")
        layout.addWidget(hint_label)

        refresh_btn = QPushButton("🔄 " + i18n.t("btn_refresh"))
        refresh_btn.clicked.connect(self._load_distributions)
        layout.addWidget(refresh_btn)

    def _setup_remote_ui(self, layout):
        if self.server_config:
            desc_text = ("编辑远程服务器连接信息，保存后将自动连接"
                         if i18n.current_lang == "zh"
                         else "Edit remote server connection, will auto-connect after saving")
        else:
            desc_text = ("配置远程服务器连接信息，保存后将自动连接"
                         if i18n.current_lang == "zh"
                         else "Configure remote server connection, will auto-connect after saving")
        desc_label = QLabel(desc_text)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        server_group = QGroupBox(
            "服务器信息" if i18n.current_lang == "zh" else "Server Information"
        )
        server_layout = QFormLayout(server_group)
        server_layout.setSpacing(12)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(
            "例如: 生产服务器" if i18n.current_lang == "zh" else "e.g., Production Server"
        )

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText(
            "例如: 192.168.1.100" if i18n.current_lang == "zh" else "e.g., 192.168.1.100"
        )

        self.port_edit = QSpinBox()
        self.port_edit.setRange(1, 65535)
        self.port_edit.setValue(22)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText(
            "SSH用户名" if i18n.current_lang == "zh" else "SSH username"
        )

        server_layout.addRow(
            "名称:" if i18n.current_lang == "zh" else "Name:", self.name_edit
        )
        server_layout.addRow(
            "主机:" if i18n.current_lang == "zh" else "Host:", self.host_edit
        )
        server_layout.addRow(
            "端口:" if i18n.current_lang == "zh" else "Port:", self.port_edit
        )
        server_layout.addRow(
            "用户名:" if i18n.current_lang == "zh" else "Username:", self.username_edit
        )

        layout.addWidget(server_group)

        auth_group = QGroupBox(
            "认证方式" if i18n.current_lang == "zh" else "Authentication"
        )
        auth_layout = QFormLayout(auth_group)
        auth_layout.setSpacing(12)

        self.auth_type_combo = QComboBox()
        self.auth_type_combo.addItems([
            "密码" if i18n.current_lang == "zh" else "Password",
            "密钥" if i18n.current_lang == "zh" else "Key"
        ])
        self.auth_type_combo.currentIndexChanged.connect(self._on_auth_type_changed)

        self.secret_edit = QLineEdit()
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret_edit.setPlaceholderText(
            "SSH密码" if i18n.current_lang == "zh" else "SSH password"
        )

        self.key_path_edit = QLineEdit()
        self.key_path_edit.setPlaceholderText(
            "私钥文件路径" if i18n.current_lang == "zh" else "Private key file path"
        )
        browse_btn = QPushButton(
            "浏览..." if i18n.current_lang == "zh" else "Browse..."
        )
        browse_btn.clicked.connect(self._browse_key_file)

        key_layout = QHBoxLayout()
        key_layout.addWidget(self.key_path_edit)
        key_layout.addWidget(browse_btn)

        auth_layout.addRow(
            "认证类型:" if i18n.current_lang == "zh" else "Auth Type:",
            self.auth_type_combo
        )
        auth_layout.addRow(
            "密码:" if i18n.current_lang == "zh" else "Password:",
            self.secret_edit
        )
        auth_layout.addRow(
            "密钥文件:" if i18n.current_lang == "zh" else "Key File:",
            key_layout
        )

        layout.addWidget(auth_group)



        self._on_auth_type_changed(0)
        self._load_saved_remote_config()

    def _on_auth_type_changed(self, index):
        is_password = (index == 0)
        self.secret_edit.setVisible(is_password)
        self.key_path_edit.setVisible(not is_password)
        if is_password:
            self.secret_edit.setPlaceholderText(
                "SSH密码" if i18n.current_lang == "zh" else "SSH password"
            )
            self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        else:
            self.secret_edit.setPlaceholderText(
                "私钥文件路径" if i18n.current_lang == "zh" else "Private key file path"
            )
            self.secret_edit.setEchoMode(QLineEdit.EchoMode.Normal)

    def _browse_key_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择私钥文件" if i18n.current_lang == "zh" else "Select Private Key",
            "",
            "所有文件 (*)" if i18n.current_lang == "zh" else "All Files (*)"
        )
        if file_path:
            self.key_path_edit.setText(file_path)

    def _load_saved_remote_config(self):
        if self.server_config:
            server = self.server_config
            self.name_edit.setText(server.name)
            self.host_edit.setText(server.host)
            self.port_edit.setValue(server.port)
            self.username_edit.setText(server.username)
            if server.auth_type == "password":
                self.auth_type_combo.setCurrentIndex(0)
                if server.password:
                    self.secret_edit.setText(server.password)
            else:
                self.auth_type_combo.setCurrentIndex(1)
                if server.key_path:
                    self.key_path_edit.setText(server.key_path)
                    self.secret_edit.setText(server.key_path)
            return


    def _test_connection(self):
        from src.ssh_client import SSHClient, SSHConnection

        if not self.host_edit.text() or not self.username_edit.text():
            QMessageBox.warning(
                self,
                "警告" if i18n.current_lang == "zh" else "Warning",
                "请填写主机和用户名" if i18n.current_lang == "zh"
                else "Please fill in host and username"
            )
            return

        is_password = (self.auth_type_combo.currentIndex() == 0)
        conn = SSHConnection(
            host=self.host_edit.text(),
            port=self.port_edit.value(),
            username=self.username_edit.text(),
            password=self.secret_edit.text() if is_password else None,
            key_path=self.key_path_edit.text() if not is_password else None
        )

        ssh_client = SSHClient()
        if ssh_client.connect(conn):
            ssh_client.disconnect()
            QMessageBox.information(
                self,
                "成功" if i18n.current_lang == "zh" else "Success",
                "连接测试成功！" if i18n.current_lang == "zh"
                else "Connection test successful!"
            )
        else:
            QMessageBox.critical(
                self,
                "错误" if i18n.current_lang == "zh" else "Error",
                "连接失败，请检查配置" if i18n.current_lang == "zh"
                else "Connection failed, please check configuration"
            )

    def _on_accept(self):
        if self.connection_type == 'remote':
            if not self.name_edit.text() or not self.host_edit.text() or not self.username_edit.text():
                QMessageBox.warning(
                    self,
                    "警告" if i18n.current_lang == "zh" else "Warning",
                    "请填写所有必填字段" if i18n.current_lang == "zh"
                    else "Please fill in all required fields"
                )
                return
            if self.db:
                config = self.get_config()
                self.db.save_server(config)
        self.accept()

    def _load_distributions(self):
        self.distro_combo.clear()
        self.distro_combo.addItem(
            "默认WSL" if i18n.current_lang == "zh" else "Default WSL",
            None
        )
        self.distro_combo.addItem(
            "正在扫描..." if i18n.current_lang == "zh" else "Scanning...",
            None
        )
        self.distro_combo.setEnabled(False)
        self.ok_btn.setEnabled(False)

        class WSLScanner(QThread):
            finished = Signal(list)

            def run(self):
                distros = WSLEnvironmentManager.list_wsl_distributions()
                self.finished.emit(distros)

        def on_scan_finished(distros):
            self.distro_combo.clear()
            self.distro_combo.addItem(
                "默认WSL" if i18n.current_lang == "zh" else "Default WSL",
                None
            )
            if not distros:
                self.distro_combo.addItem(
                    "--- WSL未安装或无响应 ---" if i18n.current_lang == "zh"
                    else "--- WSL not installed or not responding ---",
                    None
                )
                self.distro_combo.addItem(
                    "手动输入发行版名称..." if i18n.current_lang == "zh"
                    else "Enter distribution name manually...",
                    "manual"
                )
            else:
                for distro in distros:
                    self.distro_combo.addItem(distro, distro)
                self.distro_combo.addItem(
                    "--- 其他 ---" if i18n.current_lang == "zh" else "--- Other ---",
                    None
                )
                self.distro_combo.addItem(
                    "手动输入..." if i18n.current_lang == "zh" else "Enter manually...",
                    "manual"
                )

            current_distro = self.current_config.get('distro')
            if current_distro:
                index = self.distro_combo.findData(current_distro)
                if index >= 0:
                    self.distro_combo.setCurrentIndex(index)
                else:
                    self.distro_combo.insertItem(1, current_distro, current_distro)
                    self.distro_combo.setCurrentIndex(1)

            self.distro_combo.setEnabled(True)
            self.ok_btn.setEnabled(True)
            self.distro_combo.currentIndexChanged.connect(self._on_distro_changed)

        scanner = WSLScanner()
        scanner.finished.connect(on_scan_finished)
        scanner.start()
        self._scanner = scanner

    def _on_distro_changed(self, index):
        data = self.distro_combo.itemData(index)
        if data == "manual":
            distro_name, ok = QInputDialog.getText(
                self,
                "手动输入" if i18n.current_lang == "zh" else "Manual Input",
                "请输入WSL发行版名称:" if i18n.current_lang == "zh"
                else "Enter WSL distribution name:",
                QLineEdit.EchoMode.Normal,
                self.current_config.get('distro', '')
            )
            if ok and distro_name.strip():
                distro_name = distro_name.strip()
                existing_index = self.distro_combo.findData(distro_name)
                if existing_index < 0:
                    insert_pos = self.distro_combo.count() - 2
                    self.distro_combo.insertItem(insert_pos, distro_name, distro_name)
                    self.distro_combo.setCurrentIndex(insert_pos)
                else:
                    self.distro_combo.setCurrentIndex(existing_index)
            else:
                self.distro_combo.setCurrentIndex(0)

    def get_config(self):
        if self.connection_type == 'wsl':
            distro_data = self.distro_combo.currentData()
            if distro_data == "manual" or distro_data is None:
                current_text = self.distro_combo.currentText()
                if (current_text and not current_text.startswith('---')
                        and not current_text.startswith('手动')
                        and not current_text.startswith('Enter')):
                    distro_data = current_text
                else:
                    distro_data = None
            return {
                'distro': distro_data,
                'username': self.username_edit.text().strip(),
                'password': self.password_edit.text()
            }
        else:
            is_password = (self.auth_type_combo.currentIndex() == 0)
            if self.server_config:
                server_id = self.server_config.id
            else:
                server_id = str(uuid.uuid4())
            return RemoteServerConfig(
                id=server_id,
                name=self.name_edit.text(),
                host=self.host_edit.text(),
                port=self.port_edit.value(),
                username=self.username_edit.text(),
                auth_type="password" if is_password else "key",
                password=self.secret_edit.text() if is_password else None,
                key_path=self.key_path_edit.text() if not is_password else None
            )

    def get_selected_distro(self):
        config = self.get_config()
        return config['distro']
