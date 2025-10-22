import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PyQt5.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - handled via pytest skip
    pytest.skip(
        f"PyQt5 is required for TaskListWidget tests: {exc}",
        allow_module_level=True,
    )

from core.task_manager import TaskManager
from utils.i18n import _
from utils.signals import global_signals
from view.task_list_widget import TaskListWidget


class _TaskManagerStub:
    def __init__(self):
        self._statuses = {"event_task": "stopped"}
        self._configs = {
            "event_task": {
                "name": "event_task",
                "trigger": {
                    "type": "event",
                    "config": {
                        "topic": "demo/config/topic",
                    },
                },
            }
        }

    def get_task_list(self):
        return list(self._configs.keys())

    def get_task_status(self, task_name):
        return self._statuses.get(task_name, "stopped")

    def get_task_config(self, task_name):
        config = self._configs.get(task_name)
        return deepcopy(config) if config is not None else None

    def _parse_trigger(self, config):
        return TaskManager._parse_trigger(self, config)


class _MainWindowStub:
    def start_task(self):  # pragma: no cover - not used directly in tests
        pass

    def stop_task(self):  # pragma: no cover - not used directly in tests
        pass

    def delete_task(self):  # pragma: no cover - not used directly in tests
        pass


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_task_list_widget_displays_event_topic_from_nested_config(qapp):
    manager = _TaskManagerStub()
    widget = TaskListWidget(manager, scheduler=None, main_window=_MainWindowStub())

    try:
        global_signals.task_status_changed.emit("event_task", "listening")
        qapp.processEvents()

        item = widget.find_item_by_name("event_task")
        assert item is not None

        expected_text = f"{_('listening_on')}: demo/config/topic"
        expected_tooltip = f"{_('listening_on_tooltip')}: demo/config/topic"

        assert item.text(3) == expected_text
        assert item.toolTip(3) == expected_tooltip
    finally:
        widget.deleteLater()
