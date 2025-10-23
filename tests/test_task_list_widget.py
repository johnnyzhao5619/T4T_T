import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import yaml

try:
    from PyQt5.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - handled via pytest skip
    pytest.skip(
        f"PyQt5 is required for TaskListWidget tests: {exc}",
        allow_module_level=True,
    )

from core.task_manager import TaskExecutableNotFoundError, TaskManager
from core.scheduler import SchedulerManager
from utils.i18n import _
from utils.signals import global_signals
from view.task_list_widget import TaskListWidget


class _TaskManagerStub:
    def __init__(self, config):
        self._config = deepcopy(config)
        self._task_name = self._config.get("name", "event_task")
        self._statuses = {self._task_name: "stopped"}

    def get_task_list(self):
        return [self._task_name]

    def get_task_status(self, task_name):
        return self._statuses.get(task_name, "stopped")

    def get_task_config(self, task_name):
        if task_name != self._task_name:
            return None
        return deepcopy(self._config)

    def _parse_trigger(self, config):
        return TaskManager._parse_trigger(self, config)


class _MainWindowStub:
    def start_task(self):  # pragma: no cover - not used directly in tests
        pass

    def stop_task(self):  # pragma: no cover - not used directly in tests
        pass

    def delete_task(self):  # pragma: no cover - not used directly in tests
        pass


def _create_task_without_run(tasks_dir, task_name, *, enabled=False):
    task_dir = tasks_dir / task_name
    task_dir.mkdir()

    config = {
        "name": task_name,
        "module_type": "test",
        "enabled": enabled,
        "trigger": {
            "type": "event",
            "topic": f"{task_name}/topic"
        }
    }

    with open(task_dir / "config.yaml", "w", encoding="utf-8") as config_file:
        yaml.safe_dump(config, config_file, allow_unicode=True, sort_keys=False)

    with open(task_dir / "main.py", "w", encoding="utf-8") as script_file:
        script_file.write("def helper(context, inputs):\n    return inputs\n")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.mark.parametrize(
    "trigger_section, expected_topic",
    [
        (
            {
                "type": "event",
                "config": {"topic": "demo/config/topic"},
            },
            "demo/config/topic",
        ),
        (
            {
                "type": "event",
                "topic": "demo/direct/topic",
            },
            "demo/direct/topic",
        ),
        (
            {
                "event": {"topic": "demo/event/topic"},
            },
            "demo/event/topic",
        ),
    ],
)
def test_task_list_widget_displays_event_topic_from_legacy_formats(
    qapp, trigger_section, expected_topic
):
    task_name = "event_task"
    task_config = {
        "name": task_name,
        "trigger": deepcopy(trigger_section),
    }
    manager = _TaskManagerStub(task_config)
    widget = TaskListWidget(manager, scheduler=None, main_window=_MainWindowStub())

    try:
        global_signals.task_status_changed.emit(task_name, "listening")
        qapp.processEvents()

        item = widget.find_item_by_name(task_name)
        assert item is not None

        expected_text = f"{_('listening_on')}: {expected_topic}"
        expected_tooltip = f"{_('listening_on_tooltip')}: {expected_topic}"

        assert item.text(3) == expected_text
        assert item.toolTip(3) == expected_tooltip
    finally:
        widget.deleteLater()
        qapp.processEvents()


@pytest.mark.usefixtures('qapp')
def test_task_list_widget_updates_on_task_failure(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    task_name = "BrokenTask"
    _create_task_without_run(tasks_dir, task_name)

    scheduler = SchedulerManager()
    manager = TaskManager(scheduler_manager=scheduler, tasks_dir=str(tasks_dir))
    widget = TaskListWidget(manager, scheduler=None, main_window=_MainWindowStub())

    failures: list[tuple[str, str, str]] = []

    def capture_failure(name: str, timestamp: str, error: str):
        failures.append((name, timestamp, error))

    global_signals.task_failed.connect(capture_failure)

    try:
        with pytest.raises(TaskExecutableNotFoundError):
            manager.run_task(task_name, use_executor=False)

        QApplication.processEvents()

        assert failures, "Expected a failure signal to be emitted."
        last_failure = failures[-1]
        assert last_failure[0] == task_name

        item = widget.find_item_by_name(task_name)
        assert item is not None
        assert item.text(2) == last_failure[1]
        assert item.text(3) == _("status_failed")
        assert item.toolTip(3) == last_failure[2]
        assert "callable 'run'" in last_failure[2]
    finally:
        global_signals.task_failed.disconnect(capture_failure)
        widget.deleteLater()
        QApplication.processEvents()
        manager.shutdown()
