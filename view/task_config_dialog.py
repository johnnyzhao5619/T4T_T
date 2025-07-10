import logging
import json
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QPushButton,
                             QLabel, QComboBox, QFormLayout, QLineEdit)
from core.module_manager import module_manager

logger = logging.getLogger(__name__)


class TaskConfigDialog(QDialog):
    """
    Dialog for creating a new task and editing its configuration.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Task")
        self.setGeometry(200, 200, 450, 350)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Form for basic task info
        form_layout = QFormLayout()

        # Module Type Selection
        self.module_combo = QComboBox()
        self.module_combo.addItems(["Select a module type..."] +
                                   module_manager.get_module_names())
        self.module_combo.currentTextChanged.connect(self.on_module_selected)
        form_layout.addRow(QLabel("Module Type:"), self.module_combo)

        # Task Name
        self.task_name_input = QLineEdit()
        form_layout.addRow(QLabel("Task Name:"), self.task_name_input)

        self.layout.addLayout(form_layout)

        # Dialog Buttons
        self.save_button = QPushButton("Create Task")
        self.save_button.clicked.connect(self.accept)
        self.save_button.setEnabled(False)  # Disabled until module is selected
        self.layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.layout.addWidget(self.cancel_button)

    def on_module_selected(self, module_name):
        """
        Enables the Create button when a valid module is selected.
        """
        if module_name and module_name != "Select a module type...":
            self.save_button.setEnabled(True)
        else:
            self.save_button.setEnabled(False)

    def get_task_details(self):
        """
        Get the details required to create a new task.

        Returns:
            dict: A dictionary with task name and module type, or None.
        """
        module_type = self.module_combo.currentText()
        task_name = self.task_name_input.text().strip()

        if not task_name or module_type == "Select a module type...":
            logger.warning("Task name and module type are required.")
            return None

        return {
            "task_name": task_name,
            "module_type": module_type,
        }
