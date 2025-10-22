import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PyQt5.QtWidgets import QApplication, QMessageBox
except ImportError as exc:  # pragma: no cover - handled via pytest skip
    pytest.skip(
        f"PyQt5 is required for TaskDetailTabWidget tests: {exc}",
        allow_module_level=True,
    )

from view.task_detail_tab_widget import TaskDetailTabWidget


class _TaskManagerStub:
    def __init__(self):
        self._config = {
            "name": "DemoTask",
            "enabled": True,
            "trigger": {
                "type": "event",
                "topic": "demo/topic",
            },
        }
        self.save_calls = []

    def get_task_config(self, task_name):
        return deepcopy(self._config)

    def get_task_schema(self, task_name):  # pragma: no cover - schema not used
        return {}

    def save_task_config(self, task_name, config_data):
        self.save_calls.append((task_name, deepcopy(config_data)))
        self._config = deepcopy(config_data)
        return True, task_name


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
