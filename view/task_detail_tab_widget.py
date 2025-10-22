import logging
import json
import yaml
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QSplitter, QTabWidget,
                             QPushButton, QHBoxLayout, QMessageBox,
                             QFileDialog, QLabel)
from PyQt5.QtCore import Qt, QSettings
from view.task_config_widget import TaskConfigWidget
from view.json_config_editor_widget import JsonConfigEditorWidget
from view.task_output_widget import TaskOutputWidget
from utils.i18n import _
from utils.icon_manager import get_icon

logger = logging.getLogger(__name__)


class TaskDetailTabWidget(QWidget):
    """
    A widget for an individual task tab, containing enhanced configuration
    editors, action buttons, and a logging area.
    """

    def __init__(self, task_name, task_manager, parent=None):
        super().__init__(parent)
        self.task_name = task_name
        self.task_manager = task_manager
        self.settings = QSettings()

        self.init_ui()
        self.load_config()
        self.load_splitter_state()

        # Connect signals
        self.task_config_widget.config_changed.connect(self.on_config_changed)
        self.task_config_widget.config_reloaded.connect(self.on_task_renamed)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        self.splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(self.splitter)

        # --- Top Part: Config Area ---
        config_area_container = QWidget()
        config_area_layout = QVBoxLayout(config_area_container)
        config_area_layout.setContentsMargins(0, 5, 0, 0)
        config_area_layout.setSpacing(5)

        # --- Area Title ---
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(5, 0, 5, 0)
        title_label = QLabel(_("parameters_editing_area"))
        title_label.setStyleSheet("font-weight: bold;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        config_area_layout.addLayout(title_layout)

        # --- Config Tabs ---
        self.config_tabs = QTabWidget()
        self.task_config_widget = TaskConfigWidget(self.task_name,
                                                   self.task_manager)
        self.json_editor_widget = JsonConfigEditorWidget(
            self.task_name, self.task_manager)

        self.config_tabs.addTab(self.task_config_widget,
                                get_icon('fa5.list-alt'), _("form_editor_tab"))
        self.config_tabs.addTab(self.json_editor_widget, get_icon('fa5s.code'),
                                _("json_editor_tab"))
        self.config_tabs.currentChanged.connect(self.on_config_tab_changed)
        config_area_layout.addWidget(self.config_tabs)

        # --- Action Buttons ---
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(5, 5, 5, 5)
        self.save_button = QPushButton(
            get_icon("fa5s.save", color_key="primary"),
            _("save_config_button"))
        self.save_button.clicked.connect(self.save_config)
        self.save_button.setEnabled(False)  # Disabled by default
        button_layout.addWidget(self.save_button)
        self.import_button = QPushButton(get_icon("fa5s.upload"),
                                         _("import_config_button"))
        self.import_button.clicked.connect(self.import_config)
        button_layout.addWidget(self.import_button)
        self.export_button = QPushButton(get_icon("fa5s.download"),
                                         _("export_config_button"))
        self.export_button.clicked.connect(self.export_config)
        button_layout.addWidget(self.export_button)
        button_layout.addStretch()
        config_area_layout.addLayout(button_layout)

        self.splitter.addWidget(config_area_container)

        # --- Bottom Part: Log Area ---
        self.output_widget = TaskOutputWidget(self.task_name)
        self.splitter.addWidget(self.output_widget)

    def load_config(self):
        self.task_config_widget.load_config()
        self.json_editor_widget.load_config()
        self.save_button.setEnabled(False)
        self.task_config_widget.mark_as_saved()

    def save_config(self):
        config_data = None

        try:
            # Determine active editor and get config data
            if self.config_tabs.currentWidget() == self.json_editor_widget:
                config_data = self.json_editor_widget.get_config()
            else:
                if not self.task_config_widget.validate_config():
                    errors = self.task_config_widget.get_errors()
                    error_msg = "\n".join(f"- {k}: {v}"
                                          for k, v in errors.items())
                    QMessageBox.warning(
                        self, _("validation_error_title"),
                        f"{_('validation_error_message')}\n{error_msg}")
                    return
                config_data = self.task_config_widget.get_config()
        except Exception as e:
            QMessageBox.critical(self, _("error_title"),
                                 f"{_('config_save_failed_message')}:\n{e}")
            logger.error(
                f"Error saving config for task '{self.task_name}': {e}")
            return

        if config_data is None:
            return

        try:
            # Save the configuration
            success, final_task_name = self.task_manager.save_task_config(
                self.task_name, config_data)

            if success:
                QMessageBox.information(self, _("success_title"),
                                        _("config_saved_message"))
                # The task name might have changed, update it
                self.task_name = final_task_name
                # Reload config in both editors to ensure they are in sync
                # with the saved state. This is the single source of truth.
                self.load_config()
            else:
                QMessageBox.critical(self, _("error_title"),
                                     _("config_save_failed_message"))

        except Exception as e:
            QMessageBox.critical(self, _("error_title"),
                                 f"{_('config_save_failed_message')}:\n{e}")
            logger.error(
                f"Error saving config for task '{self.task_name}': {e}")

    def on_config_tab_changed(self, index, force_sync=False):
        # Don't sync if there are unsaved changes, unless forced
        if self.save_button.isEnabled() and not force_sync:
            return

        try:
            if self.config_tabs.widget(index) == self.json_editor_widget:
                config_data = self.task_config_widget.get_config()
                self.json_editor_widget.set_config(config_data)
            else:
                config_data = self.json_editor_widget.get_config()
                if config_data is None:
                    return
                self.task_config_widget.set_config(config_data)
        except Exception as e:
            logger.warning(
                f"Could not sync config editors for task '{self.task_name}':"
                f" {e}")

    def on_config_changed(self):
        self.save_button.setEnabled(True)

    def on_task_renamed(self, new_name):
        """
        Handles the UI updates when a task is renamed.
        """
        self.task_name = new_name
        self.json_editor_widget.task_name = new_name
        # The DetailAreaWidget will handle the tab title change via a signal

    def import_config(self):
        file_path, _unused = QFileDialog.getOpenFileName(
            self, _("import_config_dialog_title"), "",
            "JSON/YAML Files (*.json *.yml *.yaml)")
        if not file_path:
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.endswith(('.yml', '.yaml')):
                    config_data = yaml.safe_load(f)
                else:
                    config_data = json.load(f)

            # Update the form and JSON editor
            self.task_config_widget.set_config(config_data)
            self.json_editor_widget.set_config(config_data)
            self.save_button.setEnabled(True)  # Enable save after import
            QMessageBox.information(self, _("success_title"),
                                    _("config_imported_message"))

        except Exception as e:
            QMessageBox.critical(self, _("error_title"),
                                 f"{_('config_import_failed_message')}:\n{e}")
            logger.error(
                f"Failed to import config for task '{self.task_name}': {e}")

    def export_config(self):
        file_path, _unused = QFileDialog.getSaveFileName(
            self, _("export_config_dialog_title"),
            f"{self.task_name}_config.json",
            "JSON/YAML Files (*.json *.yml *.yaml)")
        if not file_path:
            return

        config_data = self.task_config_widget.get_config()

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                if file_path.endswith(('.yml', '.yaml')):
                    yaml.dump(config_data,
                              f,
                              default_flow_style=False,
                              sort_keys=False)
                else:
                    json.dump(config_data, f, indent=4, sort_keys=True)
            QMessageBox.information(self, _("success_title"),
                                    _("config_exported_message"))
        except Exception as e:
            QMessageBox.critical(self, _("error_title"),
                                 f"{_('config_export_failed_message')}:\n{e}")
            logger.error(
                f"Failed to export config for task '{self.task_name}': {e}")

    def save_splitter_state(self):
        self.settings.setValue(f"splitter_state_{self.task_name}",
                               self.splitter.saveState())

    def load_splitter_state(self):
        state = self.settings.value(f"splitter_state_{self.task_name}")
        if state:
            self.splitter.restoreState(state)
        else:
            # Set default sizes if no state is saved
            self.splitter.setSizes(
                [int(self.height() * 0.6),
                 int(self.height() * 0.4)])

    def closeEvent(self, event):
        self.save_splitter_state()
        super().closeEvent(event)
