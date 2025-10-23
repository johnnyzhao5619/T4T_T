from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLineEdit,
                             QComboBox, QPushButton, QMessageBox, QGroupBox)
from PyQt5.QtCore import pyqtSignal, Qt
from utils.i18n import _
from core.module_manager import module_manager
from utils.icon_manager import get_icon


class NewTaskWidget(QWidget):
    """
    A widget for creating a new task, designed to be embedded in a tab.
    """
    # Signal emitted when a task is successfully created,
    # requests to close this tab
    task_created = pyqtSignal(str)

    def __init__(self, task_manager, parent=None):
        super().__init__(parent)
        self.task_manager = task_manager
        self.init_ui()
        self.populate_modules()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setAlignment(Qt.AlignTop)

        group_box = QGroupBox(_("new_task_group_title"))
        form_layout = QFormLayout(group_box)
        form_layout.setSpacing(10)

        self.task_name_input = QLineEdit()
        self.task_name_input.setPlaceholderText(_("new_task_name_placeholder"))
        form_layout.addRow(_("new_task_name_label"), self.task_name_input)

        self.module_type_combo = QComboBox()
        form_layout.addRow(_("new_task_module_label"), self.module_type_combo)

        self.create_button = QPushButton(get_icon("fa5s.plus"),
                                         _("create_task_button"))
        self.create_button.clicked.connect(self.create_task)
        form_layout.addRow(self.create_button)

        main_layout.addWidget(group_box)

    def populate_modules(self):
        self.module_type_combo.clear()
        module_types = module_manager.get_module_names()
        self.module_type_combo.addItems(module_types)

    def create_task(self):
        task_name = self.task_name_input.text().strip()
        module_type = self.module_type_combo.currentText()

        is_valid, error_code = self.task_manager.validate_task_name(task_name)
        if not is_valid:
            error_messages = {
                'empty': _("task_name_required_error"),
                'separator': _("task_name_separator_error"),
                'outside': _("task_name_outside_dir_error"),
            }
            message = error_messages.get(error_code,
                                         _("task_created_fail_message")
                                         .format(task_name=task_name))
            QMessageBox.warning(self, _("validation_error_title"), message)
            return

        if not module_type:
            QMessageBox.warning(self, _("validation_error_title"),
                                _("module_type_required_error"))
            return

        success = self.task_manager.create_task(task_name, module_type)
        if success:
            QMessageBox.information(
                self, _("success_title"),
                _("task_created_success_message").format(task_name=task_name))
            self.task_created.emit(task_name)
        else:
            QMessageBox.critical(
                self, _("error_title"),
                _("task_created_fail_message").format(task_name=task_name))
