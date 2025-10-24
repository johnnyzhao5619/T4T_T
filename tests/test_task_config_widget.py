import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QLabel, QTableWidgetItem, QSpinBox
except ImportError as exc:  # pragma: no cover - handled via pytest skip
    pytest.skip(
        f"PyQt5 is required for TaskConfigWidget tests: {exc}",
        allow_module_level=True,
    )

from utils.i18n import _
from view.task_config_widget import TaskConfigWidget


class _DummyTaskManager:
    def __init__(self, schema=None):
        self._schema = schema or {}

    def get_task_config(self, task_name):  # pragma: no cover - not used directly
        return {}

    def get_task_schema(self, task_name):
        return self._schema


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _create_widget(config, schema=None):
    manager = _DummyTaskManager(schema=schema)
    widget = TaskConfigWidget("demo", manager)
    widget._populate_form(config)
    return widget


def test_validate_event_topic_required(qapp):
    widget = _create_widget({
        "trigger": {
            "type": "event",
            "topic": ""
        }
    })
    try:
        assert not widget.validate_config()
        errors = widget.get_errors()
        assert "trigger.event.topic" in errors
        assert errors["trigger.event.topic"] == _(
            "validation_trigger_event_topic_required")
        assert "border: 1px solid red" in widget.trigger_widget["widgets"][
            "event"].styleSheet()

        widget.trigger_widget["widgets"]["event"].setText("demo/topic")
        assert widget.validate_config()
        assert "trigger.event.topic" not in widget.get_errors()
        assert widget.trigger_widget["widgets"]["event"].styleSheet() == ""
    finally:
        widget.deleteLater()


def test_validate_cron_expression(qapp):
    widget = _create_widget({
        "trigger": {
            "type": "cron",
            "config": {
                "cron_expression": "invalid"
            }
        }
    })
    try:
        assert not widget.validate_config()
        errors = widget.get_errors()
        assert errors["trigger.cron_expression"] == _(
            "validation_trigger_cron_invalid")
        assert "border: 1px solid red" in widget.trigger_widget["widgets"][
            "cron"].styleSheet()

        widget.trigger_widget["widgets"]["cron"].setText("*/5 * * * *")
        assert widget.validate_config()
        assert "trigger.cron_expression" not in widget.get_errors()
        assert widget.trigger_widget["widgets"]["cron"].styleSheet() == ""
    finally:
        widget.deleteLater()


def test_trigger_cron_expression_fallback_on_expression_key(qapp):
    widget = _create_widget({
        "trigger": {
            "type": "cron",
            "config": {
                "type": "cron",
                "expression": "*/5 * * * *"
            }
        }
    })
    try:
        cron_widget = widget.trigger_widget["widgets"]["cron"]
        assert cron_widget.text() == "*/5 * * * *"

        widget.set_config({
            "trigger": {
                "type": "cron",
                "config": {
                    "type": "cron",
                    "expression": "0 * * * *"
                }
            }
        }, mark_changed=False)

        assert cron_widget.text() == "0 * * * *"

        saved_config = widget.get_config()
        assert saved_config["trigger"]["config"]["cron_expression"] == "0 * * * *"
        assert widget.validate_config()
    finally:
        widget.deleteLater()


def test_trigger_cron_preserves_additional_fields(qapp):
    initial_config = {
        "trigger": {
            "type": "cron",
            "config": {
                "type": "cron",
                "expression": "0 12 * * *",
                "timezone": "UTC",
                "start_date": "2024-01-01T00:00:00"
            }
        }
    }
    widget = _create_widget(initial_config)

    try:
        cron_widget = widget.trigger_widget["widgets"]["cron"]
        assert cron_widget.text() == "0 12 * * *"
        assert widget.trigger_widget["cron_extras"] == {
            "type": "cron",
            "timezone": "UTC",
            "start_date": "2024-01-01T00:00:00"
        }

        updated_config = {
            "trigger": {
                "type": "cron",
                "config": {
                    "type": "cron",
                    "cron_expression": "30 8 * * *",
                    "timezone": "Asia/Shanghai",
                    "start_date": "2024-01-01T00:00:00"
                }
            }
        }

        widget.set_config(updated_config, mark_changed=False)
        assert cron_widget.text() == "30 8 * * *"
        assert widget.trigger_widget["cron_extras"] == {
            "type": "cron",
            "timezone": "Asia/Shanghai",
            "start_date": "2024-01-01T00:00:00"
        }

        cron_widget.setText("45 10 * * *")
        saved_config = widget.get_config()

        assert saved_config["trigger"]["type"] == "cron"
        assert saved_config["trigger"]["config"]["cron_expression"] == \
            "45 10 * * *"
        assert saved_config["trigger"]["config"]["timezone"] == \
            "Asia/Shanghai"
        assert saved_config["trigger"]["config"]["start_date"] == \
            "2024-01-01T00:00:00"
        assert saved_config["trigger"]["config"]["type"] == "cron"
        assert "expression" not in saved_config["trigger"]["config"]
    finally:
        widget.deleteLater()


def test_validate_interval_requires_positive_value(qapp):
    widget = _create_widget({
        "trigger": {
            "type": "interval",
            "config": {
                "days": 0,
                "hours": 0,
                "minutes": 0,
                "seconds": 0
            }
        }
    })
    try:
        assert not widget.validate_config()
        errors = widget.get_errors()
        assert errors["trigger.interval.panel"] == _(
            "validation_trigger_interval_required")
        interval_panel = widget.trigger_widget["panels"]["interval"]
        assert "border: 1px solid red" in interval_panel.styleSheet()

        widget.trigger_widget["widgets"]["interval_seconds"].setValue(5)
        assert widget.validate_config()
        assert "trigger.interval.panel" not in widget.get_errors()
        assert interval_panel.styleSheet() == ""
    finally:
        widget.deleteLater()


def test_flat_schema_grouping_and_change_tracking(qapp):
    schema = {
        "name": {
            "label": "Task Name",
            "group": "General"
        },
        "settings.increment_by": {
            "type": "integer",
            "label": "Increment By",
            "group": "Counter Settings",
            "min": 1
        },
        "trigger": {
            "label": "Trigger Settings",
            "group": "Scheduling"
        }
    }

    config = {
        "name": "Counter Task",
        "module_type": "counter",
        "enabled": True,
        "settings": {
            "increment_by": 2
        },
        "trigger": {
            "type": "cron",
            "config": {
                "cron_expression": "*/5 * * * *"
            }
        }
    }

    widget = _create_widget(config, schema)

    try:
        assert "name" in widget.widgets
        assert widget.widgets["name"].text() == "Counter Task"

        increment_widget = widget.widgets["settings.increment_by"]
        assert isinstance(increment_widget, QSpinBox)
        assert increment_widget.value() == 2

        assert widget.findChild(QLabel, "group_label_General") is not None
        assert widget.findChild(QLabel, "group_label_Counter_Settings") is not None
        assert widget.findChild(QLabel, "group_label_Scheduling") is not None

        widget.widgets["name"].setText("Updated Task")
        assert "name" in widget.changed_widgets
    finally:
        widget.deleteLater()


def test_legacy_schema_remains_supported(qapp):
    schema = {
        "settings": {
            "label": "Settings",
            "properties": {
                "increment_by": {
                    "type": "integer",
                    "label": "Increment"
                }
            }
        }
    }

    config = {
        "settings": {
            "increment_by": 4
        }
    }

    widget = _create_widget(config, schema)

    try:
        increment_widget = widget.widgets["settings.increment_by"]
        assert isinstance(increment_widget, QSpinBox)
        assert increment_widget.value() == 4

        increment_widget.setValue(6)
        assert "settings.increment_by" in widget.changed_widgets
    finally:
        widget.deleteLater()


def test_validate_required_input_name(qapp):
    widget = _create_widget({
        "trigger": {
            "type": "cron",
            "config": {
                "cron_expression": "*/1 * * * *"
            }
        },
        "inputs": [{
            "name": "",
            "type": "string",
            "description": "",
            "default": "",
            "required": True
        }]
    })
    try:
        assert not widget.validate_config()
        errors = widget.get_errors()
        assert errors["inputs.table"] == _(
            "validation_inputs_required_name").format(index=1)
        assert "border: 1px solid red" in widget.inputs_widget.styleSheet()

        widget.inputs_widget.setItem(0, 0, QTableWidgetItem("username"))
        widget.inputs_widget.setItem(0, 1, QTableWidgetItem(""))
        assert not widget.validate_config()
        errors = widget.get_errors()
        assert errors["inputs.table"] == _(
            "validation_inputs_required_type").format(index=1)

        widget.inputs_widget.setItem(0, 1, QTableWidgetItem("string"))
        assert widget.validate_config()
        assert "inputs.table" not in widget.get_errors()
        assert widget.inputs_widget.styleSheet() == ""
    finally:
        widget.deleteLater()


def test_inputs_default_value_parsing(qapp):
    widget = _create_widget({
        "inputs": [{
            "name": "count",
            "type": "integer",
            "description": "",
            "default": 5,
            "required": False
        }, {
            "name": "enabled",
            "type": "boolean",
            "description": "",
            "default": True,
            "required": True
        }]
    })
    try:
        config = widget.get_config()
        inputs_by_name = {item["name"]: item for item in config["inputs"]}

        assert isinstance(inputs_by_name["count"]["default"], int)
        assert inputs_by_name["count"]["default"] == 5

        assert isinstance(inputs_by_name["enabled"]["default"], bool)
        assert inputs_by_name["enabled"]["default"] is True
    finally:
        widget.deleteLater()


def test_inputs_default_value_parse_failure_preserves_text(qapp, caplog):
    widget = _create_widget({
        "inputs": [{
            "name": "feature_flag",
            "type": "boolean",
            "description": "",
            "default": False,
            "required": False
        }]
    })
    try:
        widget.inputs_widget.item(0, 3).setText("maybe")
        with caplog.at_level(logging.WARNING):
            config = widget.get_config()

        assert config["inputs"][0]["default"] == "maybe"
        assert "Unable to parse default value" in caplog.text
    finally:
        widget.deleteLater()


def test_schedule_interval_trigger_preserves_inner_type(qapp):
    widget = _create_widget({
        "trigger": {
            "type": "schedule",
            "config": {
                "type": "interval",
                "seconds": 30
            }
        }
    })
    try:
        combo = widget.trigger_widget["combo"]
        assert combo.currentText().lower() == "interval"

        interval_widgets = widget.trigger_widget["widgets"]
        assert interval_widgets["interval_seconds"].value() == 30

        saved_trigger = widget.get_config()["trigger"]
        assert saved_trigger["type"] == "interval"
        assert saved_trigger["config"]["seconds"] == 30
    finally:
        widget.deleteLater()


def test_schedule_date_trigger_preserves_inner_type(qapp):
    run_date = "2024-05-01T12:00:00"
    widget = _create_widget({
        "trigger": {
            "type": "schedule",
            "config": {
                "type": "date",
                "run_date": run_date
            }
        }
    })
    try:
        combo = widget.trigger_widget["combo"]
        assert combo.currentText().lower() == "date"

        date_widget = widget.trigger_widget["widgets"]["date"]
        assert date_widget.dateTime().toString(Qt.ISODate) == run_date

        saved_trigger = widget.get_config()["trigger"]
        assert saved_trigger["type"] == "date"
        assert saved_trigger["config"]["run_date"] == run_date
    finally:
        widget.deleteLater()
