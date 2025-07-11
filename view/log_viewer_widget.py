import logging
import os
import platform
import subprocess
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox,
                             QPushButton, QTextEdit, QMessageBox, QLabel)
from utils.i18n import _
from utils.icon_manager import get_icon

logger = logging.getLogger(__name__)
LOGS_DIR = "logs"


class LogViewerWidget(QWidget):
    """A widget to view, manage, and delete log files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.load_log_files()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Top control bar
        control_layout = QHBoxLayout()

        self.log_selection_label = QLabel(_("log_selection_label"))
        control_layout.addWidget(self.log_selection_label)

        self.log_combo = QComboBox()
        self.log_combo.setMinimumWidth(250)
        self.log_combo.currentIndexChanged.connect(
            self.on_log_selection_changed)
        control_layout.addWidget(self.log_combo)

        self.open_folder_button = QPushButton(_("open_log_folder_button"))
        self.open_folder_button.setIcon(get_icon("fa5s.folder-open"))
        self.open_folder_button.clicked.connect(self.open_log_folder)
        control_layout.addWidget(self.open_folder_button)

        self.delete_log_button = QPushButton(_("delete_log_button"))
        self.delete_log_button.setIcon(
            get_icon("fa5s.trash-alt", color_key='danger'))
        self.delete_log_button.clicked.connect(self.delete_selected_log)
        control_layout.addWidget(self.delete_log_button)

        control_layout.addStretch()
        main_layout.addLayout(control_layout)

        # Log content display
        self.log_content_display = QTextEdit()
        self.log_content_display.setReadOnly(True)
        self.log_content_display.setStyleSheet(
            "font-family: Consolas, Courier New, monospace;")
        main_layout.addWidget(self.log_content_display)

    def load_log_files(self):
        self.log_combo.clear()
        if not os.path.exists(LOGS_DIR):
            self.log_content_display.setText(_("log_dir_not_found"))
            self.delete_log_button.setEnabled(False)
            self.open_folder_button.setEnabled(False)
            return

        log_files = sorted(
            [f for f in os.listdir(LOGS_DIR) if f.endswith(".txt")],
            key=lambda f: os.path.getmtime(os.path.join(LOGS_DIR, f)),
            reverse=True)

        if not log_files:
            self.log_content_display.setText(_("no_logs_found"))
            self.delete_log_button.setEnabled(False)
        else:
            self.log_combo.addItems(log_files)
            self.delete_log_button.setEnabled(True)

    def on_log_selection_changed(self, index):
        if index == -1:
            self.log_content_display.clear()
            return

        log_file_name = self.log_combo.itemText(index)
        log_file_path = os.path.join(LOGS_DIR, log_file_name)

        try:
            with open(log_file_path, 'r', encoding='utf-8') as f:
                self.log_content_display.setText(f.read())
        except Exception as e:
            error_message = f"Error reading log file: {e}"
            self.log_content_display.setText(error_message)
            logger.error(error_message)

    def open_log_folder(self):
        log_path = os.path.abspath(LOGS_DIR)
        try:
            if platform.system() == "Windows":
                os.startfile(log_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", log_path], check=True)
            else:  # Linux and other UNIX-like systems
                subprocess.run(["xdg-open", log_path], check=True)
        except Exception as e:
            QMessageBox.warning(self, _("error_title"),
                                f"{_('open_folder_failed')}: {e}")
            logger.error(f"Failed to open log folder '{log_path}': {e}")

    def delete_selected_log(self):
        current_log = self.log_combo.currentText()
        if not current_log:
            return

        reply = QMessageBox.question(
            self, _("confirm_delete_title"),
            _("confirm_delete_message").format(log_file=current_log),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            log_file_path = os.path.join(LOGS_DIR, current_log)
            try:
                os.remove(log_file_path)
                logger.info(f"Deleted log file: {current_log}")
                self.load_log_files()
            except OSError as e:
                QMessageBox.warning(self, _("error_title"),
                                    f"{_('delete_failed')}: {e}")
                logger.error(f"Failed to delete log file '{current_log}': {e}")

    def retranslate_ui(self):
        """Update UI strings for language changes."""
        self.log_selection_label.setText(_("log_selection_label"))
        self.open_folder_button.setText(_("open_log_folder_button"))
        self.delete_log_button.setText(_("delete_log_button"))
        # The content of the log display does not need translation.
        # The combo box items are filenames and should not be translated.
