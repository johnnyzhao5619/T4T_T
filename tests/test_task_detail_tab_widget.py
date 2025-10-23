import json
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PyQt5.QtWidgets import (QApplication, QLabel, QMessageBox,
                                 QFileDialog)
except ImportError as exc:  # pragma: no cover - handled via pytest skip
    pytest.skip(
        f"PyQt5 is required for TaskDetailTabWidget tests: {exc}",
        allow_module_level=True,
    )

from view.task_detail_tab_widget import TaskDetailTabWidget
from view.detail_area_widget import DetailAreaWidget
from utils.i18n import _
from utils.signals import global_signals


class _TaskManagerStub:
    def __init__(self):
        self._configs = {
            "demo": {
                "name": "DemoTask",
                "enabled": True,
                "trigger": {
                    "type": "event",
                    "topic": "demo/topic",
                },
            }
        }
        self.save_calls = []

    def get_task_config(self, task_name):
        config = self._configs.get(task_name)
        return deepcopy(config) if config is not None else None

    def get_task_schema(self, task_name):  # pragma: no cover - schema not used
        return {}

    def save_task_config(self, task_name, config_data):
        self.save_calls.append((task_name, deepcopy(config_data)))
        new_task_name = config_data.get("name", task_name)
        if task_name != new_task_name:
            self._configs.pop(task_name, None)
        self._configs[new_task_name] = deepcopy(config_data)
        return True, new_task_name


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_save_config_skips_when_json_invalid(monkeypatch, qapp):
    manager = _TaskManagerStub()
    widget = TaskDetailTabWidget("demo", manager)

    try:
        original_config = widget.task_config_widget.get_config()

        captured_messages = []
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda *args, **kwargs: captured_messages.append((args, kwargs)),
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

        json_index = widget.config_tabs.indexOf(widget.json_editor_widget)
        form_index = widget.config_tabs.indexOf(widget.task_config_widget)

        widget.config_tabs.setCurrentIndex(json_index)
        qapp.processEvents()

        widget.json_editor_widget.editor.setPlainText("{ invalid json")
        qapp.processEvents()

        widget.save_config()

        assert manager.save_calls == []
        assert captured_messages, "Expected validation error dialog for invalid JSON"

        widget.config_tabs.setCurrentIndex(form_index)
        qapp.processEvents()

        assert widget.task_config_widget.get_config() == original_config
    finally:
        widget.deleteLater()


def test_save_config_reload_after_rename(monkeypatch, qapp):
    manager = _TaskManagerStub()
    widget = TaskDetailTabWidget("demo", manager)

    try:
        monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

        updated_config = widget.task_config_widget.get_config()
        updated_config["name"] = "RenamedTask"

        widget.config_tabs.setCurrentWidget(widget.json_editor_widget)
        qapp.processEvents()

        widget.json_editor_widget.editor.setPlainText(
            json.dumps(updated_config, indent=4, sort_keys=True)
        )
        qapp.processEvents()

        widget.save_config()
        qapp.processEvents()

        assert manager.save_calls[-1][1]["name"] == "RenamedTask"
        assert widget.task_config_widget.task_name == "RenamedTask"
        assert widget.json_editor_widget.task_name == "RenamedTask"

        assert "name" in widget.task_config_widget.widgets
        assert widget.task_config_widget.widgets["name"].text() == "RenamedTask"

        assert "RenamedTask" in widget.json_editor_widget.editor.toPlainText()

        failure_message = _("config_load_failed_message")
        labels = widget.task_config_widget.findChildren(QLabel)
        assert all(label.text() != failure_message for label in labels)
    finally:
        widget.deleteLater()


def test_switch_tabs_keeps_save_disabled_and_import_triggers(monkeypatch, tmp_path, qapp):
    manager = _TaskManagerStub()
    widget = TaskDetailTabWidget("demo", manager)

    try:
        monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

        json_index = widget.config_tabs.indexOf(widget.json_editor_widget)
        form_index = widget.config_tabs.indexOf(widget.task_config_widget)

        widget.config_tabs.setCurrentIndex(json_index)
        qapp.processEvents()

        assert not widget.save_button.isEnabled()

        widget.config_tabs.setCurrentIndex(form_index)
        qapp.processEvents()

        assert not widget.save_button.isEnabled()
        assert not widget.task_config_widget.changed_widgets
        assert not widget.task_config_widget.error_widgets

        imported_config = manager.get_task_config("demo")
        imported_config["enabled"] = not imported_config.get("enabled", False)
        file_path = tmp_path / "import_config.json"
        file_path.write_text(json.dumps(imported_config))

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(file_path), ""),
        )

        widget.import_config()
        qapp.processEvents()

        assert widget.save_button.isEnabled()
        assert widget.task_config_widget.widgets["enabled"].isChecked() == \
            imported_config["enabled"]
    finally:
        widget.deleteLater()


def test_json_editor_changes_refresh_form(qapp):
    manager = _TaskManagerStub()
    widget = TaskDetailTabWidget("demo", manager)

    try:
        json_index = widget.config_tabs.indexOf(widget.json_editor_widget)
        form_index = widget.config_tabs.indexOf(widget.task_config_widget)

        widget.config_tabs.setCurrentIndex(json_index)
        qapp.processEvents()

        updated_config = manager.get_task_config("demo")
        updated_config["name"] = "DemoTaskUpdated"
        updated_config["enabled"] = not updated_config["enabled"]

        widget.json_editor_widget.editor.setPlainText(
            json.dumps(updated_config, indent=4, sort_keys=True)
        )
        qapp.processEvents()

        widget.config_tabs.setCurrentIndex(form_index)
        qapp.processEvents()

        assert widget.task_config_widget.widgets["name"].text() == \
            "DemoTaskUpdated"
        assert widget.task_config_widget.widgets["enabled"].isChecked() == \
            updated_config["enabled"]
        assert not widget.task_config_widget.changed_widgets
        assert not widget.task_config_widget.error_widgets
        assert not widget.save_button.isEnabled()
    finally:
        widget.deleteLater()


def test_cron_trigger_roundtrip_preserves_extra_fields(monkeypatch, qapp):
    manager = _TaskManagerStub()
    manager._configs["demo"]["trigger"] = {
        "type": "cron",
        "config": {
            "type": "cron",
            "cron_expression": "0 12 * * *",
            "timezone": "UTC",
            "start_date": "2024-01-01T00:00:00"
        }
    }

    widget = TaskDetailTabWidget("demo", manager)

    try:
        monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

        json_index = widget.config_tabs.indexOf(widget.json_editor_widget)
        form_index = widget.config_tabs.indexOf(widget.task_config_widget)

        cron_widget = widget.task_config_widget.trigger_widget["widgets"]["cron"]
        assert cron_widget.text() == "0 12 * * *"
        assert widget.task_config_widget.trigger_widget["cron_extras"] == {
            "type": "cron",
            "timezone": "UTC",
            "start_date": "2024-01-01T00:00:00"
        }

        widget.config_tabs.setCurrentIndex(json_index)
        qapp.processEvents()

        updated_config = manager.get_task_config("demo")
        updated_config["trigger"]["config"]["cron_expression"] = "*/5 * * * *"

        widget.json_editor_widget.editor.setPlainText(
            json.dumps(updated_config, indent=4, sort_keys=True))
        qapp.processEvents()

        widget.config_tabs.setCurrentIndex(form_index)
        qapp.processEvents()

        assert cron_widget.text() == "*/5 * * * *"
        assert widget.task_config_widget.trigger_widget["cron_extras"] == {
            "type": "cron",
            "timezone": "UTC",
            "start_date": "2024-01-01T00:00:00"
        }

        widget.save_button.setEnabled(True)
        widget.save_config()
        qapp.processEvents()

        assert manager.save_calls, "Expected configuration to be saved"
        saved_config = manager.save_calls[-1][1]
        assert saved_config["trigger"]["type"] == "cron"
        assert saved_config["trigger"]["config"]["cron_expression"] == \
            "*/5 * * * *"
        assert saved_config["trigger"]["config"]["timezone"] == "UTC"
        assert saved_config["trigger"]["config"]["start_date"] == \
            "2024-01-01T00:00:00"
        assert saved_config["trigger"]["config"]["type"] == "cron"
    finally:
        widget.deleteLater()


def test_on_task_renamed_reloads_when_clean(monkeypatch, qapp):
    manager = _TaskManagerStub()
    widget = TaskDetailTabWidget("demo", manager)

    try:
        new_name = "demo_external"
        config_copy = deepcopy(manager._configs["demo"])
        config_copy["name"] = new_name
        manager._configs[new_name] = config_copy

        original_load_config = widget.load_config
        reload_calls = []

        def wrapped_load_config():
            reload_calls.append(widget.task_name)
            return original_load_config()

        monkeypatch.setattr(widget, "load_config", wrapped_load_config)

        widget.save_button.setEnabled(False)
        widget.on_task_renamed(new_name)
        qapp.processEvents()

        assert reload_calls == [new_name]
        assert widget.task_name == new_name
        assert widget.task_config_widget.task_name == new_name
        assert widget.json_editor_widget.task_name == new_name
        assert widget.output_widget.task_name == new_name
        assert widget._last_loaded_task_name == new_name

        global_signals.log_message.emit(new_name, "log after rename")
        qapp.processEvents()
        assert "log after rename" in widget.output_widget.log_output_area.toPlainText()
    finally:
        widget.deleteLater()


def test_on_task_renamed_preserves_unsaved_changes(monkeypatch, qapp):
    manager = _TaskManagerStub()
    widget = TaskDetailTabWidget("demo", manager)

    try:
        new_name = "demo_pending"
        config_copy = deepcopy(manager._configs["demo"])
        config_copy["name"] = new_name
        manager._configs[new_name] = config_copy

        original_load_config = widget.load_config
        reload_calls = []

        def wrapped_load_config():
            reload_calls.append(widget.task_name)
            return original_load_config()

        monkeypatch.setattr(widget, "load_config", wrapped_load_config)

        modified_content = json.dumps({"name": "demo"}, indent=4, sort_keys=True)
        widget.config_tabs.setCurrentWidget(widget.json_editor_widget)
        qapp.processEvents()

        widget.json_editor_widget.editor.setPlainText(modified_content)
        widget.save_button.setEnabled(True)

        widget.on_task_renamed(new_name)
        qapp.processEvents()

        assert reload_calls == []
        assert widget.task_name == new_name
        assert widget.task_config_widget.task_name == new_name
        assert widget.json_editor_widget.task_name == new_name
        assert widget.output_widget.task_name == new_name
        assert widget._last_loaded_task_name == new_name
        expected_content = json.dumps({"name": new_name}, indent=4, sort_keys=True)
        assert widget.json_editor_widget.editor.toPlainText() == expected_content
        assert widget.save_button.isEnabled()
    finally:
        widget.deleteLater()


def test_on_task_renamed_keeps_new_name_when_saving(monkeypatch, qapp):
    manager = _TaskManagerStub()
    widget = TaskDetailTabWidget("demo", manager)

    try:
        monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
        monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

        enabled_widget = widget.task_config_widget.widgets["enabled"]
        enabled_widget.setChecked(not enabled_widget.isChecked())
        qapp.processEvents()

        assert widget.save_button.isEnabled()

        new_name = "demo_saved"
        config_copy = deepcopy(manager._configs["demo"])
        config_copy["name"] = new_name
        manager._configs[new_name] = config_copy

        widget.on_task_renamed(new_name)
        qapp.processEvents()

        assert widget.task_config_widget.widgets["name"].text() == new_name

        widget.save_config()
        qapp.processEvents()

        assert manager.save_calls[-1][1]["name"] == new_name
    finally:
        widget.deleteLater()


def test_detail_area_widget_updates_task_tab_on_rename(monkeypatch, qapp):
    manager = _TaskManagerStub()
    config_manager = object()
    detail_widget = DetailAreaWidget(manager, config_manager)

    try:
        detail_widget.open_task_tab("demo")
        qapp.processEvents()

        index = detail_widget.open_tabs["demo"]
        task_widget = detail_widget.widget(index)

        new_name = "demo_area"
        config_copy = deepcopy(manager._configs["demo"])
        config_copy["name"] = new_name
        manager._configs[new_name] = config_copy

        original_on_task_renamed = task_widget.on_task_renamed
        forwarded_names = []

        def wrapped_on_task_renamed(name):
            forwarded_names.append(name)
            return original_on_task_renamed(name)

        monkeypatch.setattr(task_widget, "on_task_renamed", wrapped_on_task_renamed)

        global_signals.task_renamed.emit("demo", new_name)
        qapp.processEvents()

        assert forwarded_names == [new_name]
        assert detail_widget.open_tabs[new_name] == index
        assert detail_widget.tabText(index) == new_name
        assert task_widget.widget_id == new_name
        assert task_widget.task_name == new_name
    finally:
        task_widget.deleteLater()
        detail_widget.deleteLater()
