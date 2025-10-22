import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication, QTableWidgetItem
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


def _create_widget(config):
    manager = _DummyTaskManager()
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
