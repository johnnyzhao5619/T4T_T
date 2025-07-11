import logging
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLineEdit, QCheckBox,
                             QLabel, QScrollArea, QComboBox, QSpinBox,
                             QHBoxLayout, QStyle, QFrame)
from PyQt5.QtCore import Qt, pyqtSignal
from utils.i18n import _

logger = logging.getLogger(__name__)


class TaskConfigWidget(QWidget):
    """
    A widget that dynamically generates a form to edit task configurations,
    with support for various input types, validation, and change tracking.
    """
    config_changed = pyqtSignal()
    config_reloaded = pyqtSignal(str)  # Emits the new task name if it changed

    def __init__(self, task_name, task_manager, parent=None):
        super().__init__(parent)
        self.task_name = task_name
        self.task_manager = task_manager
        self.widgets = {}
        self.changed_widgets = set()
        self.error_widgets = {}

        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        self.form_layout = QVBoxLayout(
            self.content_widget)  # Changed to QVBoxLayout
        self.form_layout.setContentsMargins(20, 10, 20,
                                            10)  # Added left margin
        self.form_layout.setSpacing(10)  # Reduced spacing
        self.form_layout.setAlignment(Qt.AlignTop)

        scroll_area.setWidget(self.content_widget)
        self.main_layout.addWidget(scroll_area)

    def load_config(self):
        config_data = self.task_manager.get_task_config(self.task_name)
        schema = self.task_manager.get_task_schema(self.task_name)
        if not config_data:
            logger.warning(
                f"No configuration found for task '{self.task_name}'.")
            self._clear_form()
            self.form_layout.addRow(QLabel(_("config_load_failed_message")))
            return

        self._populate_form(config_data, schema)

    def _clear_form(self):
        # Clear layout by deleting all child widgets
        for i in reversed(range(self.form_layout.count())):
            widget_to_remove = self.form_layout.itemAt(i).widget()
            if widget_to_remove:
                self.form_layout.removeWidget(widget_to_remove)
                widget_to_remove.setParent(None)
                widget_to_remove.deleteLater()
        self.widgets.clear()
        self.changed_widgets.clear()
        self.error_widgets.clear()

    def _populate_form(self, config_data, schema=None):
        self._clear_form()
        self._recursive_populate(self.form_layout, config_data, schema or {})
        self.form_layout.addStretch()

    def _recursive_populate(self, layout, config_data, schema, base_key=""):
        for key, value in config_data.items():
            full_key = f"{base_key}.{key}" if base_key else key
            param_schema = schema.get(key, {})

            if isinstance(value, dict):
                group_box = QFrame()
                group_box.setObjectName(f"group_{key}")
                group_box.setFrameShape(QFrame.StyledPanel)

                group_layout = QVBoxLayout(group_box)
                group_layout.setContentsMargins(10, 10, 10, 10)

                label_text = param_schema.get("label",
                                              key.replace("_", " ").title())
                group_label = QLabel(f"<h3>{label_text}</h3>")
                group_layout.addWidget(group_label)

                self._recursive_populate(group_layout, value,
                                         param_schema.get("properties", {}),
                                         full_key)
                layout.addWidget(group_box)
            else:
                row_widget = QWidget()
                row_layout = QVBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 5)
                row_layout.setSpacing(5)

                label_container = QWidget()
                label_layout = QHBoxLayout(label_container)
                label_layout.setContentsMargins(0, 0, 0, 0)
                label_text = param_schema.get("label",
                                              key.replace("_", " ").title())
                label_widget = QLabel(f"<b>{label_text}</b>")
                label_layout.addWidget(label_widget)

                description = param_schema.get("description", "")
                if description:
                    help_icon = QLabel()
                    icon = self.style().standardIcon(
                        QStyle.SP_MessageBoxQuestion)
                    help_icon.setPixmap(icon.pixmap(14, 14))
                    help_icon.setToolTip(description)
                    label_layout.addWidget(help_icon)
                label_layout.addStretch()
                row_layout.addWidget(label_container)

                input_type = param_schema.get("type", self._infer_type(value))
                widget = self._create_input_widget(full_key, value, input_type,
                                                   param_schema)

                row_layout.addWidget(widget)
                layout.addWidget(row_widget)
                self.widgets[full_key] = widget

    def _create_input_widget(self, key, value, input_type, param_schema):
        if input_type == "boolean":
            widget = QCheckBox()
            widget.setChecked(bool(value))
            widget.stateChanged.connect(
                lambda state, k=key: self._on_widget_change(k))
        elif input_type == "integer":
            widget = QSpinBox()
            widget.setRange(param_schema.get("min", -2147483647),
                            param_schema.get("max", 2147483647))
            widget.setValue(int(value))
            widget.valueChanged.connect(
                lambda val, k=key: self._on_widget_change(k))
        elif input_type == "choice":
            widget = QComboBox()
            widget.addItems(param_schema.get("options", []))
            if value in param_schema.get("options", []):
                widget.setCurrentText(value)
            widget.currentTextChanged.connect(
                lambda text, k=key: self._on_widget_change(k))
        else:  # Default to string/text
            widget = QLineEdit()
            widget.setText(str(value))
            widget.textChanged.connect(
                lambda text, k=key: self._on_widget_change(k))

        # Set object name for styling and identification
        widget.setObjectName(key)
        return widget

    def _infer_type(self, value):
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "float"  # Not fully supported yet, defaults to string
        return "string"

    def _on_widget_change(self, key):
        widget = self.widgets.get(key)
        if not widget:
            return

        self.changed_widgets.add(key)
        self._update_widget_style(key)
        self.config_changed.emit()

    def _update_widget_style(self, key):
        widget = self.widgets.get(key)
        if not widget:
            return

        style = ""
        if key in self.error_widgets:
            style = "border: 1px solid red;"
        elif key in self.changed_widgets:
            style = "border: 1px solid orange;"

        widget.setStyleSheet(style)

    def get_config(self):
        config_data = {}
        for full_key, widget in self.widgets.items():
            keys = full_key.split('.')
            current_level = config_data
            for i, key in enumerate(keys[:-1]):
                current_level = current_level.setdefault(key, {})

            last_key = keys[-1]
            value = None
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QLineEdit):
                # For line edits, we return a string. The JSON dump will
                # handle it.
                # If a numeric type is desired, the user should use a QSpinBox
                # or a validator, which is a more robust approach.
                value = widget.text()

            current_level[last_key] = value

        return config_data

    def set_config(self, config_data):
        """
        Public method to update the form from external data (e.g., import).
        """
        schema = self.task_manager.get_task_schema(self.task_name)
        self._populate_form(config_data, schema)
        # Mark all as changed to allow saving
        self.changed_widgets = set(self.widgets.keys())
        for key in self.widgets:
            self._update_widget_style(key)
        self.config_changed.emit()

    def validate_config(self):
        """Validates the form. Returns True if valid, False otherwise."""
        self.error_widgets.clear()
        config_data = self.get_config()
        schema = self.task_manager.get_task_schema(self.task_name) or {}

        is_valid = True
        for key, value in config_data.items():
            param_schema = schema.get(key, {})
            if param_schema.get("required", False) and not value:
                self.error_widgets[key] = _("field_required_error")
                is_valid = False

            # Add more validation rules here based on schema
            # e.g., min/max length for strings, regex patterns, etc.

        # Update styles for all widgets
        for key in self.widgets:
            self._update_widget_style(key)

        return is_valid

    def get_errors(self):
        return self.error_widgets

    def mark_as_saved(self, new_task_name=None):
        """
        Resets the change tracking and error states after a successful save.
        Optionally updates the task name if it was changed.
        """
        if new_task_name and self.task_name != new_task_name:
            old_task_name = self.task_name
            self.task_name = new_task_name
            logger.info(f"Task '{old_task_name}' has been"
                        f" renamed to '{self.task_name}'.")
            self.config_reloaded.emit(self.task_name)

        self.changed_widgets.clear()
        self.error_widgets.clear()
        for key in self.widgets.keys():
            self._update_widget_style(key)
