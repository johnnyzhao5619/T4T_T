import logging
from contextlib import contextmanager
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
        self._aux_widgets = {}
        self._suspend_change_notifications = False

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
        self._aux_widgets.clear()
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
        debug_checkbox.stateChanged.connect(self._emit_config_changed)

        layout.addRow(_("debug_mode_label"), debug_checkbox)
        self.widgets['debug'] = debug_checkbox

    @staticmethod
    def _resolve_cron_expression(config_section):
        if not isinstance(config_section, dict):
            return ""

        cron_expression = config_section.get("cron_expression")
        if cron_expression not in (None, ""):
            return str(cron_expression)

        fallback_expression = config_section.get("expression")
        if fallback_expression in (None, ""):
            return ""

        return str(fallback_expression)

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
        self.trigger_widget = {
            "combo": combo,
            "stack": stack,
            "widgets": {},
            "panels": {}
        }

        # Create panels for each trigger type
        self._create_cron_panel(stack)
        self._create_interval_panel(stack)
        self._create_date_panel(stack)
        self._create_event_panel(stack)

        combo.currentIndexChanged.connect(stack.setCurrentIndex)
        combo.currentIndexChanged.connect(self._emit_config_changed)

        trigger_layout.addWidget(combo)
        trigger_layout.addWidget(stack)
        layout.addRow(trigger_content_widget)

        # Set initial values
        raw_type = str(trigger_data.get("type", "cron")).lower()
        config_section = trigger_data.get("config")
        config = config_section if isinstance(config_section, dict) else {}
        schedule_section = trigger_data.get("schedule")
        schedule_config = schedule_section if isinstance(schedule_section, dict) else {}

        fallback_type = None
        if isinstance(config, dict):
            fallback_type = config.get("type")
        if not fallback_type:
            if isinstance(schedule_section, dict):
                fallback_type = schedule_section.get("type")
            elif isinstance(schedule_section, str):
                fallback_type = schedule_section
        fallback_type = str(fallback_type).lower() if fallback_type else None

        selected_type = raw_type if raw_type in trigger_types else None
        if not selected_type and fallback_type in trigger_types:
            selected_type = fallback_type
        if not config and schedule_config and fallback_type in trigger_types:
            config = schedule_config

        if not selected_type:
            selected_type = trigger_types[0]

        combo.setCurrentIndex(trigger_types.index(selected_type))
        stack.setCurrentIndex(trigger_types.index(selected_type))

        cron_expression = self._resolve_cron_expression(config)
        self.trigger_widget["widgets"]["cron"].setText(cron_expression)

        if selected_type == "interval":
            interval_fields = {
                "days": "interval_days",
                "hours": "interval_hours",
                "minutes": "interval_minutes",
                "seconds": "interval_seconds",
            }
            for field, widget_key in interval_fields.items():
                widget = self.trigger_widget["widgets"][widget_key]
                if isinstance(config, dict) and field in config:
                    value = config.get(field)
                    if value is not None:
                        widget.setValue(int(value))
                elif field == "minutes":
                    widget.setValue(5)

        if selected_type == "date" and isinstance(config, dict):
            run_date = config.get("run_date")
            if run_date:
                parsed_date = QDateTime.fromString(str(run_date), Qt.ISODate)
                if (not parsed_date.isValid() and
                        hasattr(Qt, "ISODateWithMs")):
                    parsed_date = QDateTime.fromString(
                        str(run_date), Qt.ISODateWithMs)
                if parsed_date.isValid():
                    self.trigger_widget["widgets"]["date"].setDateTime(parsed_date)

        event_topic = ""
        if isinstance(config, dict):
            event_topic = config.get("topic", "")
        if not event_topic:
            event_topic = trigger_data.get("topic", "")
        self.trigger_widget["widgets"]["event"].setText(event_topic)

    def _create_cron_panel(self, stack):
        panel = QWidget()
        layout = QFormLayout(panel)
        cron_widget = QLineEdit()
        cron_widget.setPlaceholderText(_("cron_placeholder"))
        layout.addRow(QLabel(_("cron_expression_label")), cron_widget)
        stack.addWidget(panel)
        self.trigger_widget["widgets"]["cron"] = cron_widget
        cron_widget.textChanged.connect(self._emit_config_changed)
        self._register_aux_widget("trigger.cron_expression", cron_widget)

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
            w.valueChanged.connect(self._emit_config_changed)
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
        self.trigger_widget["panels"]["interval"] = panel
        self._register_aux_widget("trigger.interval.panel", panel)

    def _create_date_panel(self, stack):
        panel = QWidget()
        layout = QFormLayout(panel)
        date_widget = QDateTimeEdit()
        date_widget.setCalendarPopup(True)
        date_widget.setDateTime(QDateTime.currentDateTime())
        layout.addRow(_("run_date_label"), date_widget)
        stack.addWidget(panel)
        self.trigger_widget["widgets"]["date"] = date_widget
        date_widget.dateTimeChanged.connect(self._emit_config_changed)

    def _create_event_panel(self, stack):
        panel = QWidget()
        layout = QFormLayout(panel)
        topic_widget = QLineEdit()
        topic_widget.setPlaceholderText(_("topic_placeholder"))
        layout.addRow(QLabel(_("topic_label")), topic_widget)
        stack.addWidget(panel)
        self.trigger_widget["widgets"]["event"] = topic_widget
        topic_widget.textChanged.connect(self._emit_config_changed)
        self._register_aux_widget("trigger.event.topic", topic_widget)

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
        table.itemChanged.connect(self._emit_config_changed)
        self._register_aux_widget("inputs.table", table)

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
        check_box.stateChanged.connect(self._emit_config_changed)

    def _remove_selected_input_row(self, table):
        current_row = table.currentRow()
        if current_row >= 0:
            table.removeRow(current_row)
            self._emit_config_changed()

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
        if self._suspend_change_notifications:
            return
        self.changed_widgets.add(key)
        self._update_widget_style(key)
        self._emit_config_changed()

    def _register_aux_widget(self, key, widget):
        if widget:
            self._aux_widgets[key] = widget

    def _emit_config_changed(self, *args, **_kwargs):
        if not self._suspend_change_notifications:
            self.config_changed.emit()

    @contextmanager
    def _maybe_block_signals(self, widget, should_block):
        if not widget or not should_block:
            yield
            return
        previous_state = widget.blockSignals(True)
        try:
            yield
        finally:
            widget.blockSignals(previous_state)

    def _update_widget_style(self, key, widget_override=None):
        widget = widget_override or self.widgets.get(key) or self._aux_widgets.get(
            key)
        if not widget:
            return

        style = ""
        if key in self.error_widgets:
            style = "border: 1px solid red;"
        elif key in self.changed_widgets:
            style = "border: 1px solid orange;"
        widget.setStyleSheet(style)

    def _refresh_form_widgets(self, config_data, mark_changed):
        if not isinstance(config_data, dict):
            config_data = {}

        if 'debug' in self.widgets:
            self.set_field_value('debug', bool(config_data.get('debug', False)),
                                 mark_changed=mark_changed)

        flat_values = {}

        def collect_values(data, prefix=""):
            for key, value in data.items():
                if key in {"trigger", "inputs"}:
                    continue
                full_key = f"{prefix}.{key}" if prefix else key
                if full_key == 'debug' and not prefix:
                    continue
                if isinstance(value, dict):
                    collect_values(value, full_key)
                else:
                    flat_values[full_key] = value

        collect_values(config_data)

        for key, value in flat_values.items():
            if key in self.widgets:
                self.set_field_value(key, value, mark_changed=mark_changed)

        self._refresh_trigger_widget(config_data.get('trigger'),
                                     mark_changed=mark_changed)
        self._refresh_inputs_widget(config_data.get('inputs'),
                                    mark_changed=mark_changed)

    def _refresh_trigger_widget(self, trigger_data, mark_changed):
        if not self.trigger_widget:
            return

        combo = self.trigger_widget.get("combo")
        if not combo:
            return
        trigger_types = [combo.itemText(i).lower() for i in range(combo.count())]

        trigger_dict = trigger_data if isinstance(trigger_data, dict) else {}
        raw_type = str(trigger_dict.get("type", "")).lower()
        config_section = trigger_dict.get("config")
        config = config_section if isinstance(config_section, dict) else {}
        schedule_section = trigger_dict.get("schedule")
        schedule_config = (schedule_section if isinstance(schedule_section, dict)
                           else {})

        fallback_type = None
        if isinstance(config, dict):
            fallback_type = config.get("type")
        if not fallback_type:
            if isinstance(schedule_section, dict):
                fallback_type = schedule_section.get("type")
            elif isinstance(schedule_section, str):
                fallback_type = schedule_section
        fallback_type = str(fallback_type).lower() if fallback_type else None

        selected_type = raw_type if raw_type in trigger_types else None
        if not selected_type and fallback_type in trigger_types:
            selected_type = fallback_type
        if not selected_type and trigger_types:
            selected_type = trigger_types[0]

        if selected_type in trigger_types:
            target_index = trigger_types.index(selected_type)
            with self._maybe_block_signals(combo, not mark_changed):
                combo.setCurrentIndex(target_index)
            stack = self.trigger_widget.get("stack")
            if stack:
                stack.setCurrentIndex(target_index)
        else:
            target_index = combo.currentIndex()
            selected_type = trigger_types[target_index] if trigger_types else None

        if not config and schedule_config and fallback_type == selected_type:
            config = schedule_config
        if not isinstance(config, dict):
            config = {}

        widgets = self.trigger_widget.get("widgets", {})

        if selected_type == "cron":
            cron_widget = widgets.get("cron")
            if cron_widget:
                cron_expression = self._resolve_cron_expression(config)
                with self._maybe_block_signals(cron_widget, not mark_changed):
                    cron_widget.setText(str(cron_expression))
        elif selected_type == "interval":
            interval_fields = {
                "days": "interval_days",
                "hours": "interval_hours",
                "minutes": "interval_minutes",
                "seconds": "interval_seconds",
            }
            for field, widget_key in interval_fields.items():
                widget = widgets.get(widget_key)
                if not widget:
                    continue
                value = config.get(field, 0)
                with self._maybe_block_signals(widget, not mark_changed):
                    widget.setValue(int(value) if value is not None else 0)
        elif selected_type == "date":
            date_widget = widgets.get("date")
            if date_widget:
                run_date = config.get("run_date")
                if run_date:
                    parsed_date = QDateTime.fromString(str(run_date), Qt.ISODate)
                    if (not parsed_date.isValid()
                            and hasattr(Qt, "ISODateWithMs")):
                        parsed_date = QDateTime.fromString(
                            str(run_date), Qt.ISODateWithMs)
                    if parsed_date.isValid():
                        with self._maybe_block_signals(date_widget,
                                                       not mark_changed):
                            date_widget.setDateTime(parsed_date)
        elif selected_type == "event":
            event_widget = widgets.get("event")
            if event_widget:
                topic = ""
                if isinstance(config, dict):
                    topic = config.get("topic", "")
                if not topic:
                    topic = trigger_dict.get("topic", "")
                with self._maybe_block_signals(event_widget, not mark_changed):
                    event_widget.setText(str(topic))

    def _refresh_inputs_widget(self, inputs_data, mark_changed):
        if not self.inputs_widget:
            return

        table = self.inputs_widget
        inputs_list = inputs_data if isinstance(inputs_data, list) else []

        with self._maybe_block_signals(table, not mark_changed):
            table.setRowCount(0)
            for item_data in inputs_list:
                self._add_input_row(table, item_data)

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
            name = self._get_table_item_text(table, row, 0)
            type_name = self._get_table_item_text(table, row, 1)
            description = self._get_table_item_text(table, row, 2)
            default_text = self._get_table_item_text(table, row, 3)

            default_value = self._parse_input_default_value(name, type_name,
                                                            default_text,
                                                            row)

            item = {
                "name": name,
                "type": type_name,
                "description": description,
                "default": default_value,
                "required": table.cellWidget(row, 4).findChild(
                    QCheckBox).isChecked()
            }
            inputs_list.append(item)
        return inputs_list

    @staticmethod
    def _get_table_item_text(table, row, column):
        item = table.item(row, column)
        return item.text() if item else ""

    def _parse_input_default_value(self, name, type_name, raw_value, row):
        type_key = (type_name or "").strip().lower()
        if not type_key:
            return raw_value

        if raw_value is None:
            return None

        if isinstance(raw_value, str):
            text_value = raw_value
        else:
            text_value = str(raw_value)

        stripped_value = text_value.strip()

        if stripped_value == "":
            return raw_value

        try:
            if type_key in {"integer", "int"}:
                return int(stripped_value)
            if type_key in {"number", "float"}:
                return float(stripped_value)
            if type_key in {"boolean", "bool"}:
                lowered = stripped_value.lower()
                if lowered in {"true", "1", "yes", "on"}:
                    return True
                if lowered in {"false", "0", "no", "off"}:
                    return False
                raise ValueError("Unrecognised boolean literal")
        except ValueError:
            logger.warning(
                "Unable to parse default value '%s' for input '%s' (row %s) "
                "as type '%s'. Keeping original value.", text_value,
                name or f"#{row + 1}", row + 1, type_name)
            return raw_value

        return raw_value

    def set_config(self, config_data, mark_changed: bool = True):
        if not isinstance(config_data, dict):
            config_data = {}

        previous_suppression = self._suspend_change_notifications
        if not mark_changed:
            self._suspend_change_notifications = True

        try:
            if mark_changed or not self.widgets:
                self._populate_form(config_data)
            else:
                self._refresh_form_widgets(config_data, mark_changed=False)
        finally:
            if not mark_changed:
                self._suspend_change_notifications = previous_suppression

        all_keys = set(self.widgets.keys()) | set(self._aux_widgets.keys())

        if mark_changed:
            self.changed_widgets = set(self.widgets.keys())
            for key in all_keys:
                self._update_widget_style(key)
            self._emit_config_changed()
        else:
            self.changed_widgets.clear()
            self.error_widgets.clear()
            for key in all_keys:
                self._update_widget_style(key)

    def set_field_value(self, key, value, *, mark_changed=True):
        """Update a form field while optionally keeping change highlights."""
        widget = self.widgets.get(key)
        if not widget:
            return False

        if isinstance(widget, QLineEdit):
            previous_block_state = widget.blockSignals(True)
            try:
                if widget.text() == str(value):
                    # Ensure style is refreshed when the widget is already marked.
                    if mark_changed and key in self.changed_widgets:
                        self._update_widget_style(key)
                    return True
                widget.setText(str(value))
            finally:
                widget.blockSignals(previous_block_state)
        elif isinstance(widget, QCheckBox):
            previous_block_state = widget.blockSignals(True)
            try:
                bool_value = bool(value)
                if widget.isChecked() == bool_value:
                    if mark_changed and key in self.changed_widgets:
                        self._update_widget_style(key)
                    return True
                widget.setChecked(bool_value)
            finally:
                widget.blockSignals(previous_block_state)
        elif isinstance(widget, QSpinBox):
            previous_block_state = widget.blockSignals(True)
            try:
                int_value = int(value)
                if widget.value() == int_value:
                    if mark_changed and key in self.changed_widgets:
                        self._update_widget_style(key)
                    return True
                widget.setValue(int_value)
            finally:
                widget.blockSignals(previous_block_state)
        elif isinstance(widget, QComboBox):
            previous_block_state = widget.blockSignals(True)
            try:
                text_value = str(value)
                if widget.currentText() == text_value:
                    if mark_changed and key in self.changed_widgets:
                        self._update_widget_style(key)
                    return True
                index = widget.findText(text_value)
                if index >= 0:
                    widget.setCurrentIndex(index)
                else:
                    widget.setCurrentText(text_value)
            finally:
                widget.blockSignals(previous_block_state)
        else:
            logger.debug("Unsupported widget type for key '%s'.", key)
            return False

        if mark_changed:
            self.changed_widgets.add(key)
        else:
            self.changed_widgets.discard(key)
        self._update_widget_style(key)
        return True

    def validate_config(self):
        self.error_widgets.clear()
        is_valid = True
        all_keys = set(self.widgets.keys()) | set(self._aux_widgets.keys())

        def add_error(key, message, widget=None):
            nonlocal is_valid
            is_valid = False
            if key not in self.error_widgets:
                self.error_widgets[key] = message
            self._update_widget_style(key, widget)

        if self.trigger_widget:
            combo = self.trigger_widget["combo"]
            current_type = combo.currentText().lower()
            trigger_widgets = self.trigger_widget["widgets"]

            if current_type == "event":
                topic_widget = trigger_widgets.get("event")
                if topic_widget and not topic_widget.text().strip():
                    add_error("trigger.event.topic",
                              _("validation_trigger_event_topic_required"),
                              topic_widget)
            elif current_type == "cron":
                cron_widget = trigger_widgets.get("cron")
                cron_expression = cron_widget.text().strip() if cron_widget else ""
                if not cron_expression:
                    add_error("trigger.cron_expression",
                              _("validation_trigger_cron_required"),
                              cron_widget)
                else:
                    try:
                        from apscheduler.triggers.cron import CronTrigger
                        CronTrigger.from_crontab(cron_expression)
                    except Exception:
                        add_error("trigger.cron_expression",
                                  _("validation_trigger_cron_invalid"),
                                  cron_widget)
            elif current_type == "interval":
                days = trigger_widgets.get("interval_days")
                hours = trigger_widgets.get("interval_hours")
                minutes = trigger_widgets.get("interval_minutes")
                seconds = trigger_widgets.get("interval_seconds")
                values = [
                    w.value() if w else 0 for w in
                    (days, hours, minutes, seconds)
                ]
                if all(value == 0 for value in values):
                    interval_panel = self.trigger_widget["panels"].get(
                        "interval")
                    add_error("trigger.interval.panel",
                              _("validation_trigger_interval_required"),
                              interval_panel)

        if self.inputs_widget:
            table = self.inputs_widget
            rows = table.rowCount()
            for row in range(rows):
                required_widget = table.cellWidget(row, 4)
                checkbox = required_widget.findChild(QCheckBox) if required_widget else None
                if checkbox and checkbox.isChecked():
                    name_item = table.item(row, 0)
                    type_item = table.item(row, 1)
                    if not name_item or not name_item.text().strip():
                        add_error(
                            "inputs.table",
                            _("validation_inputs_required_name").format(
                                index=row + 1),
                            table)
                        break
                    if not type_item or not type_item.text().strip():
                        add_error(
                            "inputs.table",
                            _("validation_inputs_required_type").format(
                                index=row + 1),
                            table)
                        break

        for key in all_keys:
            if key not in self.error_widgets:
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
        for key in set(self.widgets.keys()) | set(self._aux_widgets.keys()):
            self._update_widget_style(key)
