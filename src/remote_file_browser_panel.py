from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QMessageBox,
    QHeaderView,
    QInputDialog,
    QDialog,
    QTextEdit,
)
from PySide6.QtCore import Qt, Signal
import os
import shlex
from src.ssh_client import SSHClient
from src.i18n import i18n
from src.worker import Worker


class RemoteFileBrowserPanel(QWidget):
    path_changed = Signal(str)
    connection_requested = Signal()  # 新增信号，用于请求连接

    def __init__(self, ssh_client: SSHClient):
        super().__init__()
        self.ssh_client = ssh_client
        self.current_path = "."
        self.workers = []
        self._refresh_seq = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 文件表格
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels([
            i18n.t("files_col_name"),
            i18n.t("files_col_size"),
            i18n.t("files_col_permissions"),
            "修改时间" if i18n.current_lang == "zh" else "Modified"
        ])
        self.file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        # 设置列宽度策略
        header = self.file_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)      # 名称
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)        # 大小
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)        # 权限
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)        # 修改时间
        
        self.file_table.setColumnWidth(1, 110)   # 大小
        self.file_table.setColumnWidth(2, 140)   # 权限
        self.file_table.setColumnWidth(3, 190)   # 修改时间
        
        # 设置行号列宽度
        self.file_table.verticalHeader().setFixedWidth(50)
        
        # 设置表格样式
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setShowGrid(True)
        
        self.file_table.itemDoubleClicked.connect(self.on_item_activated)
        layout.addWidget(self.file_table)

    def _set_busy(self):
        self.file_table.setEnabled(not self.workers)

    def _start_worker(self, func, on_success):
        worker = Worker(func)
        self.workers.append(worker)
        self._set_busy()
        worker.result.connect(on_success)
        worker.error.connect(self._show_worker_error)
        worker.finished.connect(lambda: self._finish_worker(worker))
        worker.start()
        return worker

    def _finish_worker(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        self._set_busy()

    def _show_worker_error(self, message):
        QMessageBox.critical(
            self,
            "错误" if i18n.current_lang == "zh" else "Error",
            str(message),
        )

    def _show_success(self, zh_text: str, en_text: str):
        QMessageBox.information(
            self,
            "成功" if i18n.current_lang == "zh" else "Success",
            zh_text if i18n.current_lang == "zh" else en_text,
        )

    def _ensure_connected(self) -> bool:
        if self.ssh_client and getattr(self.ssh_client, "sftp", None):
            return True
        QMessageBox.warning(self, i18n.t("msg_warning"), i18n.t("msg_connect_first"))
        return False

    @staticmethod
    def _format_size(size: int) -> str:
        try:
            value = float(size or 0)
        except (TypeError, ValueError):
            value = 0.0
        units = ["B", "KB", "MB", "GB", "TB"]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024

    def refresh_files(self, path=None):
        """刷新文件列表"""
        if not self._ensure_connected():
            return
        # QPushButton.clicked may pass a bool, which should not replace the path.
        target_path = path if isinstance(path, str) else self.current_path
        self._refresh_seq += 1
        refresh_seq = self._refresh_seq
        self.file_table.setRowCount(0)

        def do_refresh():
            return refresh_seq, target_path, self.ssh_client.list_directory(target_path)

        self._start_worker(do_refresh, self._on_files_loaded)

    def _on_files_loaded(self, result):
        refresh_seq, path, files = result
        if refresh_seq != self._refresh_seq:
            return

        self.current_path = path
        self.path_changed.emit(self.current_path)
        self.file_table.setRowCount(0)

        for f in files:
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)
            
            # 名称
            name_item = QTableWidgetItem(f.name)
            name_item.setData(Qt.ItemDataRole.UserRole, f.path)
            name_item.setData(Qt.ItemDataRole.UserRole + 1, f.is_directory)
            self.file_table.setItem(row, 0, name_item)
            
            # 大小
            size_text = "" if f.is_directory else self._format_size(f.size)
            self.file_table.setItem(row, 1, QTableWidgetItem(size_text))
            
            # 权限
            self.file_table.setItem(row, 2, QTableWidgetItem(f.permissions))
            
            # 修改时间（如果有的话）
            modified = getattr(f, 'modified_time', '') or getattr(f, 'modified', '')
            self.file_table.setItem(row, 3, QTableWidgetItem(str(modified)))

    def on_item_activated(self, item):
        """双击项目时的处理"""
        is_directory = bool(item.data(Qt.ItemDataRole.UserRole + 1))
        if is_directory:
            next_path = item.data(Qt.ItemDataRole.UserRole) or item.text()
            self.refresh_files(next_path)

    def go_up(self):
        """返回上级目录"""
        if self.current_path in (".", "/"):
            self.refresh_files(".")
            return

        normalized = self.current_path.rstrip("/")
        if "/" not in normalized:
            parent = "."
        else:
            parent = normalized.rsplit("/", 1)[0] or "/"
        self.refresh_files(parent)

    def _join_remote_path(self, directory: str, name: str) -> str:
        if directory in (".", ""):
            return f"./{name}"
        if directory == "/":
            return f"/{name}"
        return f"{directory.rstrip('/')}/{name}"

    def _quote_remote_path(self, path: str) -> str:
        path = str(path or "").strip()
        if path == "~":
            return "~"
        if path.startswith("~/"):
            rest = path[2:]
            return f"~/{shlex.quote(rest)}" if rest else "~"
        return shlex.quote(path)

    def _validate_child_name(self, name: str):
        name = str(name or "").strip()
        if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "名称不能包含路径分隔符" if i18n.current_lang == "zh" else "Name cannot contain path separators",
            )
            return None
        return name

    def _selected_entry(self):
        row = self.file_table.currentRow()
        if row < 0:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "请先选择一个文件或目录" if i18n.current_lang == "zh" else "Please select a file or directory first",
            )
            return None
        item = self.file_table.item(row, 0)
        if item is None:
            return None
        return {
            "name": item.text(),
            "path": item.data(Qt.ItemDataRole.UserRole) or item.text(),
            "is_directory": bool(item.data(Qt.ItemDataRole.UserRole + 1)),
        }

    def upload_file(self):
        if not self._ensure_connected():
            return
        local_path, _ = QFileDialog.getOpenFileName(self, "Select File to Upload")
        if local_path:
            remote_path = self._join_remote_path(
                self.current_path, os.path.basename(local_path)
            )
            self._start_worker(
                lambda: self.ssh_client.upload_file(local_path, remote_path),
                self._on_upload_finished,
            )

    def _on_upload_finished(self, ok):
        if ok:
            self._show_success("文件已上传", "File uploaded")
            self.refresh_files()
        else:
            QMessageBox.critical(
                self,
                i18n.t("msg_error"),
                "上传失败" if i18n.current_lang == "zh" else "Upload failed",
            )

    def create_directory(self):
        if not self._ensure_connected():
            return
        name, ok = QInputDialog.getText(
            self,
            "新建目录" if i18n.current_lang == "zh" else "New Directory",
            "目录名称:" if i18n.current_lang == "zh" else "Directory name:",
        )
        if not ok:
            return
        name = self._validate_child_name(name)
        if not name:
            return
        remote_path = self._join_remote_path(self.current_path, name)
        self._run_remote_command(
            f"mkdir -p -- {self._quote_remote_path(remote_path)}",
            timeout=10,
        )

    def rename_selected(self):
        if not self._ensure_connected():
            return
        entry = self._selected_entry()
        if not entry:
            return
        new_name, ok = QInputDialog.getText(
            self,
            "重命名" if i18n.current_lang == "zh" else "Rename",
            "新名称:" if i18n.current_lang == "zh" else "New name:",
            text=entry["name"],
        )
        if not ok:
            return
        new_name = self._validate_child_name(new_name)
        if not new_name or new_name == entry["name"]:
            return
        target_path = self._join_remote_path(self.current_path, new_name)
        self._run_remote_command(
            f"mv -- {self._quote_remote_path(entry['path'])} {self._quote_remote_path(target_path)}",
            timeout=20,
        )

    def delete_selected(self):
        if not self._ensure_connected():
            return
        entry = self._selected_entry()
        if not entry:
            return
        reply = QMessageBox.question(
            self,
            i18n.t("msg_confirm"),
            (
                f"确定删除 {entry['path']}？"
                if i18n.current_lang == "zh"
                else f"Delete {entry['path']}?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        command = "rm -rf" if entry["is_directory"] else "rm -f"
        self._run_remote_command(
            f"{command} -- {self._quote_remote_path(entry['path'])}",
            timeout=30,
        )

    def _run_remote_command(self, command: str, timeout: int):
        self._start_worker(
            lambda: self.ssh_client.execute_command(command, timeout=timeout),
            self._on_remote_command_finished,
        )

    def _on_remote_command_finished(self, result):
        stdout, stderr, exit_code = result
        if exit_code == 0:
            self.refresh_files()
        else:
            QMessageBox.critical(self, i18n.t("msg_error"), stderr or stdout)

    def view_text_file(self):
        if not self._ensure_connected():
            return
        entry = self._selected_entry()
        if not entry:
            return
        if entry["is_directory"]:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "目录不能作为文本查看" if i18n.current_lang == "zh" else "Directories cannot be viewed as text",
            )
            return
        command = f"head -c 200000 -- {self._quote_remote_path(entry['path'])}"
        self._start_worker(
            lambda: (entry["path"], self.ssh_client.execute_command(command, timeout=20)),
            self._on_text_loaded,
        )

    def _on_text_loaded(self, result):
        path, command_result = result
        stdout, stderr, exit_code = command_result
        if exit_code != 0:
            QMessageBox.critical(self, i18n.t("msg_error"), stderr or stdout)
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(path)
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(stdout)
        layout.addWidget(text)
        dialog.exec()

    def download_file(self):
        """下载文件"""
        if not self._ensure_connected():
            return
        entry = self._selected_entry()
        if not entry:
            return
        if entry["is_directory"]:
            QMessageBox.warning(
                self,
                i18n.t("msg_warning"),
                "目录不能作为文件下载" if i18n.current_lang == "zh" else "Directories cannot be downloaded as files",
            )
            return
        remote_path = entry["path"]
        
        local_path, _ = QFileDialog.getSaveFileName(
            self, 
            "保存文件" if i18n.current_lang == "zh" else "Save File As",
            entry["name"]
        )
        if local_path:
            self._start_worker(
                lambda: self.ssh_client.download_file(remote_path, local_path),
                self._on_download_finished,
            )

    def _on_download_finished(self, ok):
        if ok:
            self._show_success("文件已下载", "File downloaded")
        else:
            QMessageBox.critical(
                self,
                i18n.t("msg_error"),
                "下载失败" if i18n.current_lang == "zh" else "Download failed",
            )
