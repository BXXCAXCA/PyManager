from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)


class RemoteTextInputDialog(QDialog):
    """Reusable single-line prompt for remote file and environment operations."""

    def __init__(self, title: str, label: str, default_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.label_widget = QLabel(label)
        self.label_widget.setWordWrap(True)
        self.input_edit = QLineEdit()
        self.input_edit.setText(default_text)

        form.addRow(self.label_widget, self.input_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self) -> str:
        return self.input_edit.text().strip()


class RemotePathInputDialog(RemoteTextInputDialog):
    """Prompt the user for a remote path."""

    def __init__(self, title: str, label: str, default_text: str = "", parent=None):
        super().__init__(title, label, default_text, parent)
        self.input_edit.setPlaceholderText("/home/user/project")


class RemoteCommandDialog(QDialog):
    """Prompt for a remote shell command and optional working directory."""

    def __init__(self, title: str, command_label: str, cwd_label: str = "Working directory", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.command_edit = QTextEdit()
        self.command_edit.setPlaceholderText("ls -la")
        self.command_edit.setMinimumHeight(120)

        self.cwd_edit = QLineEdit()
        self.cwd_edit.setPlaceholderText("/home/user")

        form.addRow(QLabel(command_label), self.command_edit)
        form.addRow(QLabel(cwd_label), self.cwd_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def command(self) -> str:
        return self.command_edit.toPlainText().strip()

    def working_directory(self) -> str:
        return self.cwd_edit.text().strip()


__all__ = [
    "RemoteTextInputDialog",
    "RemotePathInputDialog",
    "RemoteCommandDialog",
]
