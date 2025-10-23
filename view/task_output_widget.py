import logging
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTextEdit, QComboBox, QLineEdit)
from utils.i18n import _
from utils.signals import global_signals

logger = logging.getLogger(__name__)


class TaskOutputWidget(QWidget):
    """
    A widget to display task output, including logs, with controls for
    filtering and debugging.
    """

    def __init__(self, task_name, parent=None):
        super().__init__(parent)
        self.task_name = task_name
        self.init_ui()
        global_signals.log_message.connect(self.append_log)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # --- Header Area ---
        header_layout = QHBoxLayout()

        title_label = QLabel(_("task_output_area"))
        title_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        # --- Filter Controls ---
        self.filter_level_combo = QComboBox()
        self.filter_level_combo.addItems(
            [_("all_levels"), "DEBUG", "INFO", "WARNING", "ERROR"])
        # self.filter_level_combo.currentTextChanged.connect(self.apply_filters)
        header_layout.addWidget(self.filter_level_combo)

        self.filter_text_input = QLineEdit()
        self.filter_text_input.setPlaceholderText(_("filter_logs_placeholder"))
        # self.filter_text_input.textChanged.connect(self.apply_filters)
        header_layout.addWidget(self.filter_text_input)

        layout.addLayout(header_layout)

        # --- Log Output Area ---
        self.log_output_area = QTextEdit()
        self.log_output_area.setReadOnly(True)
        self.log_output_area.setObjectName("LogOutputArea")
        layout.addWidget(self.log_output_area)

    def append_log(self, task_name, message):
        """Appends a message to the log area if it's for this task."""
        if task_name == self.task_name:
            # Here you would implement the filtering logic before appending
            self.log_output_area.append(message)

    def __del__(self):
        self._disconnect_signals()

    def _disconnect_signals(self):
        try:
            global_signals.log_message.disconnect(self.append_log)
        except TypeError:
            pass

    def closeEvent(self, event):
        self._disconnect_signals()
        super().closeEvent(event)
