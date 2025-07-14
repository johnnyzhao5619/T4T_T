import logging
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLineEdit, QCheckBox,
                             QLabel, QScrollArea, QComboBox, QSpinBox,
                             QHBoxLayout, QFrame, QStackedWidget, QTableWidget,
                             QTableWidgetItem, QPushButton, QHeaderView,
                             QDateTimeEdit, QFormLayout)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime
from utils.icon_manager import get_icon

from utils.i18n import _
from view.components.separator import Separator

logger = logging.getLogger(__name__)


class TaskConfigWidget(QWidget):
    """
    A widget that dynamically generates a form to edit task configurations.

    Supports various input types, validation, change tracking, a dynamic
    trigger UI, and a table-based inputs editor.

    TODO (Schema Simplification): The current schema-driven UI generation
    relies on a nested structure (e.g., schema -> group -> properties).
    A potential future optimization is to flatten this structure.
    Instead of nesting, parameters could be defined at the top level of the
    schema, with an optional 'group' key to assign them to a UI group.
    This would simplify the manifest.yaml files.
    Example:
    schema:
      debug:
        type: "boolean"
        label: "Debug Mode"
        group: "Execution"
      increment_by:
        type: "integer"
        label: "Increment By"
        group: "Settings"
    This change would require refactoring _populate_form to handle the
    flattened structure and create groups based on the 'group' key.
    """
    config_changed = pyqtSignal()
    config_reloaded = pyqtSignal(str)

    def __init__(self, task_name, task_manager, parent=None):
        super().__init__(parent)
        self.task_name = task_name
        self.task_manager = task_manager
        self.widgets = {}
        self.changed_widgets = set()
        self.error_widgets = {}

        # Widgets for special sections
        self.trigger_widget = None
        self.inputs_widget = None

        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Create a dedicated title bar
        self.title_bar = self._create_title_bar()
        self.main_layout.addWidget(self.title_bar)

        # Create a scroll area for the form content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.NoFrame)

        # Content widget and form layout
        self.content_widget = QWidget()
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(20, 20, 20, 20)
        self.form_layout.setSpacing(15)
        self.form_layout.setLabelAlignment(Qt.AlignLeft)
        self.form_layout.setRowWrapPolicy(QFormLayout.WrapAllRows)

        # A wrapper widget to hold the form layout with left alignment
        form_wrapper = QWidget()
        form_wrapper_layout = QVBoxLayout(form_wrapper)
        form_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        form_wrapper_layout.addLayout(self.form_layout)
        form_wrapper_layout.addStretch(1)  # Pushes the form to the top

        self.content_widget.setLayout(form_wrapper_layout)

        scroll_area.setWidget(self.content_widget)
        self.main_layout.addWidget(scroll_area)

    def load_config(self):
        config_data = self.task_manager.get_task_config(self.task_name)
        if not config_data:
            logger.warning("No configuration found for task '%s'.",
                           self.task_name)
            self._clear_form()
            self.form_layout.addWidget(QLabel(_("config_load_failed_message")))
            return

        self._populate_form(config_data)

    def _clear_form(self):
        for i in reversed(range(self.form_layout.count())):
            item = self.form_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()
        self.widgets.clear()
        self.changed_widgets.clear()
        self.error_widgets.clear()
        self.trigger_widget = None
        self.inputs_widget = None

    def _create_title_bar(self):
        title_bar = QWidget()
        title_bar.setObjectName("configTitleBar")
        title_bar.setFixedHeight(50)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(15, 0, 15, 0)

        self.title_icon = QLabel()
        self.title_icon.setPixmap(get_icon("fa5s.cog").pixmap(24, 24))

        self.title_label = QLabel("Settings")
        self.title_label.setObjectName("configTitleLabel")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")

        title_layout.addWidget(self.title_icon)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        return title_bar

    def _update_title(self):
        """Updates the title bar with the current task name."""
        self.title_label.setText(self.task_name)
        # You can also fetch a specific icon for the task type if available
        # For now, we use a default cog icon.

    def _populate_form(self, config_data):
        self._clear_form()
        self._update_title()  # Update the title bar
        schema = self.task_manager.get_task_schema(self.task_name) or {}

        # Hardcoded handling for the 'debug' setting
        if 'debug' in config_data:
            self._create_debug_widget(self.form_layout, config_data['debug'])

        # Process other configuration items
        standard_config = {
            k: v
            for k, v in config_data.items() if k != 'debug'
        }
        self._recursive_populate(self.form_layout, standard_config, schema)

    def _recursive_populate(self, layout, config_data, schema, base_key=""):
        for key, value in config_data.items():
            full_key = f"{base_key}.{key}" if base_key else key
            param_schema = schema.get(key, {})

            if key == 'trigger' and isinstance(value, dict):
                self._create_trigger_widget(layout, value, param_schema)
                continue

            if key == 'inputs' and isinstance(value, list):
                self._create_inputs_widget(layout, value, param_schema)
                continue

            if isinstance(value, dict):
                self._create_group_box(layout, key, value, param_schema,
                                       full_key)
            else:
                self._create_standard_input(layout, full_key, key, value,
                                            param_schema)

    def _create_group_box(self, layout, key, value, param_schema, full_key):
        # Add a separator and a title for the group
        label_text = param_schema.get("label", key.replace("_", " ").title())
        group_label = QLabel(label_text)
        group_label.setObjectName(f"group_label_{key}")
        group_label.setStyleSheet("""
            font-size: 16px; 
            font-weight: bold; 
            margin-top: 10px;
        """)

        layout.addRow(Separator())
        layout.addRow(group_label)

        # Create a nested form layout for the group's content
        group_content_widget = QWidget()
        group_layout = QFormLayout(group_content_widget)
        group_layout.setContentsMargins(0, 5, 0, 5)
        group_layout.setSpacing(10)

        self._recursive_populate(group_layout, value,
                                 param_schema.get("properties", {}), full_key)

        layout.addRow(group_content_widget)

    def _create_standard_input(self, layout, full_key, key, value,
                               param_schema):
        label_widget = self._create_label_with_help(param_schema, key)

        input_type = param_schema.get("type", self._infer_type(value))
        input_widget = self._create_input_widget(full_key, value, input_type,
                                                 param_schema)

        layout.addRow(label_widget, input_widget)
        self.widgets[full_key] = input_widget

    def _create_label_with_help(self, param_schema, key):
        label_text = param_schema.get("label", key.replace("_", " ").title())
        description = param_schema.get("description", "")

        label_widget = QLabel(label_text)
        if description:
            label_widget.setToolTip(description)

        return label_widget

    def _create_debug_widget(self, layout, is_checked):
        """
        Creates a dedicated widget for the debug toggle in the QFormLayout.
        """
        debug_checkbox = QCheckBox()
        debug_checkbox.setChecked(is_checked)
        debug_checkbox.stateChanged.connect(self.config_changed.emit)

        layout.addRow(_("debug_mode_label"), debug_checkbox)
        self.widgets['debug'] = debug_checkbox

    def _create_trigger_widget(self, layout, trigger_data, schema):
        # Add a separator and a title for the trigger group
        label_text = schema.get("label", "Trigger")
        group_label = QLabel(label_text)
        group_label.setObjectName("group_label_trigger")
        group_label.setStyleSheet("""
            font-size: 16px; 
            font-weight: bold; 
            margin-top: 10px;
        """)
        layout.addRow(Separator())
        layout.addRow(group_label)

        # Create a widget to hold the trigger configuration
        trigger_content_widget = QWidget()
        trigger_layout = QVBoxLayout(trigger_content_widget)
        trigger_layout.setContentsMargins(0, 5, 0, 5)
        trigger_layout.setSpacing(10)

        combo = QComboBox()
        trigger_types = ["cron", "interval", "date", "event"]
        combo.addItems([t.title() for t in trigger_types])

        stack = QStackedWidget()
        self.trigger_widget = {"combo": combo, "stack": stack, "widgets": {}}

        # Create panels for each trigger type
        self._create_cron_panel(stack)
        self._create_interval_panel(stack)
        self._create_date_panel(stack)
        self._create_event_panel(stack)

        combo.currentIndexChanged.connect(stack.setCurrentIndex)
        combo.currentIndexChanged.connect(self.config_changed.emit)

        trigger_layout.addWidget(combo)
        trigger_layout.addWidget(stack)
        layout.addRow(trigger_content_widget)

        # Set initial values
        current_type = trigger_data.get("type", "cron")
        if current_type in trigger_types:
            combo.setCurrentIndex(trigger_types.index(current_type))
            stack.setCurrentIndex(trigger_types.index(current_type))

        config = trigger_data.get("config", {})
        self.trigger_widget["widgets"]["cron"].setText(
            config.get("cron_expression", ""))
        self.trigger_widget["widgets"]["interval_days"].setValue(
            config.get("days", 0))
        self.trigger_widget["widgets"]["interval_hours"].setValue(
            config.get("hours", 0))
        self.trigger_widget["widgets"]["interval_minutes"].setValue(
            config.get("minutes", 5))
        self.trigger_widget["widgets"]["interval_seconds"].setValue(
            config.get("seconds", 0))
        self.trigger_widget["widgets"]["date"].setDateTime(
            QDateTime.fromString(config.get("run_date", ""), Qt.ISODate)
            if config.get("run_date") else QDateTime.currentDateTime())
        self.trigger_widget["widgets"]["event"].setText(
            trigger_data.get("topic", ""))

    def _create_cron_panel(self, stack):
        panel = QWidget()
        layout = QFormLayout(panel)
        cron_widget = QLineEdit()
        cron_widget.setPlaceholderText(_("cron_placeholder"))
        layout.addRow(QLabel(_("cron_expression_label")), cron_widget)
        stack.addWidget(panel)
        self.trigger_widget["widgets"]["cron"] = cron_widget
        cron_widget.textChanged.connect(self.config_changed.emit)

    def _create_interval_panel(self, stack):
        panel = QWidget()
        layout = QFormLayout(panel)
        layout.setSpacing(10)
        days = QSpinBox()
        hours = QSpinBox()
        minutes = QSpinBox()
        seconds = QSpinBox()
        for w in [days, hours, minutes, seconds]:
            w.setRange(0, 99999)
            w.valueChanged.connect(self.config_changed.emit)
        layout.addRow(_("days_label"), days)
        layout.addRow(_("hours_label"), hours)
        layout.addRow(_("minutes_label"), minutes)
        layout.addRow(_("seconds_label"), seconds)
        stack.addWidget(panel)
        self.trigger_widget["widgets"].update({
            "interval_days": days,
            "interval_hours": hours,
            "interval_minutes": minutes,
            "interval_seconds": seconds
        })

    def _create_date_panel(self, stack):
        panel = QWidget()
        layout = QFormLayout(panel)
        date_widget = QDateTimeEdit()
        date_widget.setCalendarPopup(True)
        date_widget.setDateTime(QDateTime.currentDateTime())
        layout.addRow(_("run_date_label"), date_widget)
        stack.addWidget(panel)
        self.trigger_widget["widgets"]["date"] = date_widget
        date_widget.dateTimeChanged.connect(self.config_changed.emit)

    def _create_event_panel(self, stack):
        panel = QWidget()
        layout = QFormLayout(panel)
        topic_widget = QLineEdit()
        topic_widget.setPlaceholderText(_("topic_placeholder"))
        layout.addRow(QLabel(_("topic_label")), topic_widget)
        stack.addWidget(panel)
        self.trigger_widget["widgets"]["event"] = topic_widget
        topic_widget.textChanged.connect(self.config_changed.emit)

    def _create_inputs_widget(self, layout, inputs_data, schema):
        # Add a separator and a title for the inputs group
        label_text = schema.get("label", "Inputs")
        group_label = QLabel(label_text)
        group_label.setObjectName("group_label_inputs")
        group_label.setStyleSheet("""
            font-size: 16px; 
            font-weight: bold; 
            margin-top: 10px;
        """)
        layout.addRow(Separator())
        layout.addRow(group_label)

        # Create a widget to hold the inputs table and buttons
        inputs_content_widget = QWidget()
        inputs_layout = QVBoxLayout(inputs_content_widget)
        inputs_layout.setContentsMargins(0, 5, 0, 5)
        inputs_layout.setSpacing(10)

        table = QTableWidget()
        table.setColumnCount(5)
        headers = ["Name", "Type", "Description", "Default Value", "Required"]
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2,
                                                      QHeaderView.Interactive)

        for item_data in inputs_data:
            self._add_input_row(table, item_data)

        inputs_layout.addWidget(table)
        self._create_add_remove_buttons(inputs_layout, table)

        layout.addRow(inputs_content_widget)
        self.inputs_widget = table
        table.itemChanged.connect(self.config_changed.emit)

    def _create_add_remove_buttons(self, layout, table):
        btn_layout = QHBoxLayout()
        add_btn = QPushButton(_("add_input_button"))
        remove_btn = QPushButton(_("remove_input_button"))
        add_btn.clicked.connect(lambda: self._add_input_row(table))
        remove_btn.clicked.connect(
            lambda: self._remove_selected_input_row(table))
        btn_layout.addStretch()
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        layout.addLayout(btn_layout)

    def _add_input_row(self, table, item_data=None):
        if item_data is None:
            item_data = {
                "name": "",
                "type": "string",
                "description": "",
                "default": "",
                "required": False
            }

        row_position = table.rowCount()
        table.insertRow(row_position)

        table.setItem(row_position, 0,
                      QTableWidgetItem(item_data.get("name", "")))
        table.setItem(row_position, 1,
                      QTableWidgetItem(item_data.get("type", "string")))
        table.setItem(row_position, 2,
                      QTableWidgetItem(item_data.get("description", "")))
        table.setItem(row_position, 3,
                      QTableWidgetItem(str(item_data.get("default", ""))))

        check_box_widget = QWidget()
        check_box_layout = QHBoxLayout(check_box_widget)
        check_box = QCheckBox()
        check_box.setChecked(item_data.get("required", False))
        check_box_layout.addWidget(check_box)
        check_box_layout.setAlignment(Qt.AlignCenter)
        check_box_layout.setContentsMargins(0, 0, 0, 0)
        table.setCellWidget(row_position, 4, check_box_widget)
        check_box.stateChanged.connect(self.config_changed.emit)

    def _remove_selected_input_row(self, table):
        current_row = table.currentRow()
        if current_row >= 0:
            table.removeRow(current_row)
            self.config_changed.emit()

    def _create_input_widget(self, key, value, input_type, param_schema):
        if input_type == "boolean":
            widget = QCheckBox()
            widget.setChecked(bool(value))
            widget.stateChanged.connect(
                lambda state, k=key: self._on_widget_change(k))
        elif input_type == "integer":
            widget = QSpinBox()
            min_val = param_schema.get("min", -2147483647)
            max_val = param_schema.get("max", 2147483647)
            widget.setRange(min_val, max_val)
            widget.setValue(int(value))
            widget.valueChanged.connect(
                lambda val, k=key: self._on_widget_change(k))
        elif input_type == "choice":
            widget = QComboBox()
            options = param_schema.get("options", [])
            widget.addItems(options)
            if value in options:
                widget.setCurrentText(value)
            widget.currentTextChanged.connect(
                lambda text, k=key: self._on_widget_change(k))
        else:
            widget = QLineEdit()
            widget.setText(str(value))
            widget.textChanged.connect(
                lambda text, k=key: self._on_widget_change(k))

        widget.setObjectName(key)
        return widget

    def _infer_type(self, value):
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        return "string"

    def _on_widget_change(self, key):
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
        # Get standard widget values
        for full_key, widget in self.widgets.items():
            # Handle hardcoded 'debug' key
            if full_key == 'debug':
                config_data['debug'] = widget.isChecked()
                continue

            keys = full_key.split('.')
            current_level = config_data
            for i, key in enumerate(keys[:-1]):
                current_level = current_level.setdefault(key, {})

            last_key = keys[-1]
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QSpinBox):
                value = widget.value()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            else:
                value = widget.text()
            current_level[last_key] = value

        if self.trigger_widget:
            config_data["trigger"] = self._get_trigger_config()

        if self.inputs_widget:
            config_data["inputs"] = self._get_inputs_config()

        return config_data

    def _get_trigger_config(self):
        trigger_config = {}
        combo = self.trigger_widget["combo"]
        current_type = combo.currentText().lower()
        trigger_config["type"] = current_type

        if current_type == "cron":
            trigger_config["config"] = {
                "cron_expression":
                self.trigger_widget["widgets"]["cron"].text()
            }
        elif current_type == "interval":
            trigger_config["config"] = {
                "days":
                self.trigger_widget["widgets"]["interval_days"].value(),
                "hours":
                self.trigger_widget["widgets"]["interval_hours"].value(),
                "minutes":
                self.trigger_widget["widgets"]["interval_minutes"].value(),
                "seconds":
                self.trigger_widget["widgets"]["interval_seconds"].value()
            }
        elif current_type == "date":
            trigger_config["config"] = {
                "run_date":
                self.trigger_widget["widgets"]["date"].dateTime().toString(
                    Qt.ISODate)
            }
        elif current_type == "event":
            trigger_config["topic"] = self.trigger_widget["widgets"][
                "event"].text()

        return trigger_config

    def _get_inputs_config(self):
        inputs_list = []
        table = self.inputs_widget
        for row in range(table.rowCount()):
            item = {
                "name":
                table.item(row, 0).text(),
                "type":
                table.item(row, 1).text(),
                "description":
                table.item(row, 2).text(),
                "default":
                table.item(row, 3).text(),
                "required":
                table.cellWidget(row, 4).findChild(QCheckBox).isChecked()
            }
            inputs_list.append(item)
        return inputs_list

    def set_config(self, config_data):
        self._populate_form(config_data)
        self.changed_widgets = set(self.widgets.keys())
        for key in self.widgets:
            self._update_widget_style(key)
        self.config_changed.emit()

    def validate_config(self):
        self.error_widgets.clear()
        is_valid = True
        # Basic validation can be added here if needed
        for key in self.widgets:
            self._update_widget_style(key)
        return is_valid

    def get_errors(self):
        return self.error_widgets

    def mark_as_saved(self, new_task_name=None):
        if new_task_name and self.task_name != new_task_name:
            old_task_name = self.task_name
            self.task_name = new_task_name
            logger.info("Task '%s' has been renamed to '%s'.", old_task_name,
                        self.task_name)
            self.config_reloaded.emit(self.task_name)

        self.changed_widgets.clear()
        self.error_widgets.clear()
        for key in self.widgets.keys():
            self._update_widget_style(key)
