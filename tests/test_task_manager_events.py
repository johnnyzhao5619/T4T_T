import importlib.util
import json
import logging
import os
import sys
import time
import types
from pathlib import Path
from typing import Any, Callable, Tuple

import pytest
import yaml
from apscheduler.triggers.cron import CronTrigger

PyQt5 = types.ModuleType("PyQt5")
QtCore = types.ModuleType("PyQt5.QtCore")
QtWidgets = types.ModuleType("PyQt5.QtWidgets")
QtGui = types.ModuleType("PyQt5.QtGui")


class _DummySignal:
    def __init__(self):
        self._callbacks: list[Callable[..., None]] = []

    def connect(self, callback, *args, **kwargs):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def disconnect(self, callback=None, *args, **kwargs):
        if callback is None:
            self._callbacks.clear()
            return
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class QWidget:
    def __init__(self, *args, **kwargs):
        pass


class QVBoxLayout:
    def __init__(self, parent=None):
        self.parent = parent

    def setContentsMargins(self, *args, **kwargs):
        return None

    def setAlignment(self, *args, **kwargs):
        return None

    def addWidget(self, *args, **kwargs):
        return None


class QFormLayout:
    def __init__(self, parent=None):
        self.parent = parent

    def setSpacing(self, *args, **kwargs):
        return None

    def addRow(self, *args, **kwargs):
        return None


class QLineEdit:
    def __init__(self):
        self._text = ""
        self.placeholder = ""

    def setPlaceholderText(self, text):
        self.placeholder = text

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text


class QComboBox:
    def __init__(self):
        self._items: list[str] = []
        self._index = 0

    def clear(self):
        self._items = []
        self._index = 0

    def addItems(self, items):
        self._items.extend(items)

    def currentText(self):
        if not self._items:
            return ""
        return self._items[self._index]

    def setCurrentIndex(self, index):
        if 0 <= index < len(self._items):
            self._index = index


class QPushButton:
    def __init__(self, *args, **kwargs):
        self.clicked = _DummySignal()

    def setEnabled(self, *args, **kwargs):
        return None


class QGroupBox(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class QMessageBox:
    @staticmethod
    def warning(*args, **kwargs):
        return None

    @staticmethod
    def information(*args, **kwargs):
        return None

    @staticmethod
    def critical(*args, **kwargs):
        return None


class QColor:
    def __init__(self, color):
        self.color = color


QtCore.QObject = object
QtCore.pyqtSignal = lambda *args, **kwargs: _DummySignal()
QtCore.Qt = types.SimpleNamespace(AlignTop=0)
QtWidgets.QWidget = QWidget
QtWidgets.QVBoxLayout = QVBoxLayout
QtWidgets.QFormLayout = QFormLayout
QtWidgets.QLineEdit = QLineEdit
QtWidgets.QComboBox = QComboBox
QtWidgets.QPushButton = QPushButton
QtWidgets.QGroupBox = QGroupBox
QtWidgets.QMessageBox = QMessageBox
QtGui.QColor = QColor

PyQt5.QtCore = QtCore
PyQt5.QtWidgets = QtWidgets
PyQt5.QtGui = QtGui

qtawesome = types.ModuleType("qtawesome")
qtawesome.icon = lambda *args, **kwargs: object()

sys.modules.setdefault("PyQt5", PyQt5)
sys.modules.setdefault("PyQt5.QtCore", QtCore)
sys.modules.setdefault("PyQt5.QtWidgets", QtWidgets)
sys.modules.setdefault("PyQt5.QtGui", QtGui)
sys.modules.setdefault("qtawesome", qtawesome)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from core.context import TaskContextFilter
from core.scheduler import SchedulerManager
from core.task_manager import (
    SCHEDULED_TRIGGER_TYPES,
    TaskExecutionError,
    TaskManager,
    is_scheduled_trigger,
)
from core.module_manager import ModuleManager
from utils.i18n import _, language_manager
from utils.logger import SignalHandler
from view.new_task_widget import NewTaskWidget


class DummySignal:
    def __init__(self):
        self.emitted = []

    def emit(self, *args, **kwargs):
        self.emitted.append((args, kwargs))


class DummySignals:
    def __init__(self):
        self.task_status_changed = DummySignal()
        self.task_manager_updated = DummySignal()
        self.task_renamed = DummySignal()
        self.task_succeeded = DummySignal()
        self.task_failed = DummySignal()
        self.log_message = DummySignal()


def test_is_scheduled_trigger_covers_known_types():
    for trigger_type in SCHEDULED_TRIGGER_TYPES:
        assert is_scheduled_trigger(trigger_type)

    assert not is_scheduled_trigger('event')
    assert not is_scheduled_trigger(None)


class FakeBusManager:
    def __init__(self):
        self.subscriptions: dict[str, list[Callable[[dict], None]]] = {}
        self.subscribe_calls: list[tuple[str, Callable[[dict], None]]] = []
        self.unsubscribe_calls: list[tuple[str, Callable[[dict], None] | None]] = []

    def subscribe(self, topic: str, callback: Callable[[dict], None]):
        callbacks = self.subscriptions.setdefault(topic, [])
        if callback not in callbacks:
            callbacks.append(callback)
            self.subscribe_calls.append((topic, callback))

    def unsubscribe(self, topic: str, callback: Callable[[dict], None] | None = None):
        callbacks = self.subscriptions.get(topic)
        if not callbacks:
            self.unsubscribe_calls.append((topic, callback))
            return

        if callback is None:
            self.subscriptions.pop(topic, None)
            self.unsubscribe_calls.append((topic, None))
            return

        if callback in callbacks:
            callbacks.remove(callback)
            self.unsubscribe_calls.append((topic, callback))
            if not callbacks:
                self.subscriptions.pop(topic, None)

    def publish(self, topic: str, payload: dict):
        callbacks = self.subscriptions.get(topic, [])
        for callback in list(callbacks):
            callback(payload)


_SCRIPT_CONTENT = "def run(context, inputs):\n    return inputs\n"


def _write_task_files(task_dir: Path, config: dict,
                      script_content: str | None = None) -> None:
    task_dir.mkdir()

    import yaml

    with open(task_dir / "config.yaml", "w", encoding="utf-8") as config_file:
        yaml.safe_dump(config,
                      config_file,
                      allow_unicode=True,
                      sort_keys=False)

    content = script_content if script_content is not None else _SCRIPT_CONTENT
    with open(task_dir / "main.py", "w", encoding="utf-8") as script_file:
        script_file.write(content)


def _create_module_template(modules_dir: Path,
                            module_name: str = "sample_module") -> str:
    module_dir = modules_dir / module_name
    module_dir.mkdir(parents=True)

    template_path = module_dir / f"{module_name}_template.py"
    template_path.write_text(_SCRIPT_CONTENT, encoding="utf-8")

    manifest_data = {
        "name": module_name,
        "module_type": module_name,
        "enabled": True,
        "trigger": {
            "type": "event",
            "topic": "tests/topic"
        }
    }

    with open(module_dir / "manifest.yaml", "w", encoding="utf-8") as manifest_file:
        yaml.safe_dump(manifest_data,
                       manifest_file,
                       allow_unicode=True,
                       sort_keys=False)

    return module_name


class _DummySchedulerManager:
    def submit(self, *args, **kwargs):
        raise RuntimeError("Scheduler should not be used in tests.")


@pytest.fixture
def temp_task_manager(tmp_path):
    modules_dir = tmp_path / "modules"
    tasks_dir = tmp_path / "tasks"
    module_name = _create_module_template(modules_dir)

    module_manager_instance = ModuleManager()
    default_modules_path = os.path.abspath(os.path.join(project_root,
                                                        "modules"))
    original_module_path = getattr(module_manager_instance, "module_path",
                                   default_modules_path)

    manager = TaskManager(_DummySchedulerManager(),
                          tasks_dir=str(tasks_dir),
                          modules_dir=str(modules_dir))

    try:
        yield manager, module_name
    finally:
        manager.apscheduler.shutdown(wait=False)
        module_manager_instance.set_module_path(original_module_path)


def _create_event_task(tasks_dir: Path, name: str = "EventTask",
                       topic: str = "test/topic", enabled: bool = True):
    task_dir = tasks_dir / name
    config = {
        "name": name,
        "module_type": "test",
        "enabled": enabled,
        "trigger": {
            "type": "event",
            "topic": topic
        }
    }

    _write_task_files(task_dir, config)


def _create_event_task_with_hop_limit(tasks_dir: Path,
                                      name: str,
                                      topic: str,
                                      max_hops: int):
    task_dir = tasks_dir / name
    config = {
        "name": name,
        "module_type": "test",
        "enabled": True,
        "trigger": {
            "event": {
                "topic": topic,
                "max_hops": max_hops,
            }
        }
    }

    _write_task_files(task_dir, config)


def _create_interval_task(tasks_dir: Path, name: str = "IntervalTask",
                          seconds: int = 1, enabled: bool = True):
    task_dir = tasks_dir / name
    config = {
        "name": name,
        "module_type": "test",
        "enabled": enabled,
        "trigger": {
            "type": "schedule",
            "config": {
                "type": "interval",
                "seconds": seconds
            }
        }
    }

    _write_task_files(task_dir, config)


def _create_cron_task(tasks_dir: Path,
                      name: str = "CronTask",
                      cron_expression: str = "*/5 * * * *",
                      timezone: str | None = "UTC",
                      enabled: bool = True,
                      **additional_config):
    task_dir = tasks_dir / name
    cron_config: dict[str, Any] = {
        "type": "cron",
        "cron_expression": cron_expression,
    }
    if timezone is not None:
        cron_config["timezone"] = timezone
    if additional_config:
        cron_config.update(additional_config)

    config = {
        "name": name,
        "module_type": "test",
        "enabled": enabled,
        "trigger": {
            "type": "schedule",
            "config": cron_config
        }
    }

    _write_task_files(task_dir, config)


def _create_persistent_task(tasks_dir: Path, name: str = "PersistentTask",
                            state: dict | None = None):
    task_dir = tasks_dir / name
    config = {
        "name": name,
        "module_type": "test",
        "enabled": False,
        "persist_state": True,
        "trigger": {
            "type": "event",
            "topic": "persist/topic"
        }
    }

    _write_task_files(task_dir, config)

    if state is not None:
        with open(task_dir / "state.json", "w", encoding="utf-8") as state_file:
            json.dump(state, state_file)


def _create_manager(monkeypatch, tasks_dir: Path) -> Tuple[TaskManager, FakeBusManager, DummySignals]:
    fake_bus = FakeBusManager()
    dummy_signals = DummySignals()
    monkeypatch.setattr("core.task_manager.message_bus_manager", fake_bus)
    monkeypatch.setattr("core.task_manager.global_signals", dummy_signals)

    scheduler = SchedulerManager()
    manager = TaskManager(scheduler_manager=scheduler,
                          tasks_dir=str(tasks_dir))

    return manager, fake_bus, dummy_signals


@pytest.fixture()
def prepared_manager(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_event_task(tasks_dir)

    manager, fake_bus, dummy_signals = _create_manager(monkeypatch, tasks_dir)

    yield manager, fake_bus, dummy_signals

    manager.shutdown()


@pytest.fixture()
def prepared_schedule_manager(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_interval_task(tasks_dir)

    dummy_signals = DummySignals()
    fake_bus = FakeBusManager()
    monkeypatch.setattr("core.task_manager.global_signals", dummy_signals)
    monkeypatch.setattr("core.task_manager.message_bus_manager", fake_bus)

    scheduler = SchedulerManager()
    manager = TaskManager(scheduler_manager=scheduler,
                          tasks_dir=str(tasks_dir))

    yield manager, dummy_signals

    manager.shutdown()


def test_initialize_tasks_autostart_only_once(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_interval_task(tasks_dir, name="AutoTask")

    dummy_signals = DummySignals()
    fake_bus = FakeBusManager()
    monkeypatch.setattr("core.task_manager.global_signals", dummy_signals)
    monkeypatch.setattr("core.task_manager.message_bus_manager", fake_bus)

    original_start = TaskManager.start_task
    start_calls: list[str] = []

    def tracked_start(self, task_name: str):
        start_calls.append(task_name)
        return original_start(self, task_name)

    monkeypatch.setattr(TaskManager, "start_task", tracked_start)

    scheduler = SchedulerManager()
    manager = TaskManager(scheduler_manager=scheduler,
                          tasks_dir=str(tasks_dir))

    try:
        assert start_calls == ["AutoTask"]
    finally:
        manager.shutdown()


def test_start_task_cron_with_timezone_and_options(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_cron_task(tasks_dir,
                      cron_expression="*/5 * * * *",
                      timezone="UTC",
                      misfire_grace_time=15)

    dummy_signals = DummySignals()
    fake_bus = FakeBusManager()
    monkeypatch.setattr("core.task_manager.global_signals", dummy_signals)
    monkeypatch.setattr("core.task_manager.message_bus_manager", fake_bus)

    scheduler = SchedulerManager()
    manager = TaskManager(scheduler_manager=scheduler,
                          tasks_dir=str(tasks_dir))

    try:
        job = manager.apscheduler.get_job("CronTask")
        assert job is not None
        assert isinstance(job.trigger, CronTrigger)
        assert str(job.trigger.timezone) == "UTC"
        assert job.misfire_grace_time == 15
        assert manager.tasks["CronTask"]["status"] == "running"
    finally:
        manager.shutdown()


def test_start_task_cron_missing_expression_returns_false(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_cron_task(tasks_dir,
                      cron_expression=" ",
                      enabled=False)

    manager, _, dummy_signals = _create_manager(monkeypatch, tasks_dir)

    try:
        result = manager.start_task("CronTask")
        assert result is False
        assert manager.apscheduler.get_job("CronTask") is None
        assert manager.tasks["CronTask"]["status"] == "stopped"
        assert len(dummy_signals.task_failed.emitted) == 1
        args, _ = dummy_signals.task_failed.emitted[-1]
        assert args[0] == "CronTask"
        assert "cron" in args[2].lower()
    finally:
        manager.shutdown()


def test_start_task_event_manual_subscription(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_event_task(tasks_dir, enabled=False)

    manager, fake_bus, dummy_signals = _create_manager(monkeypatch, tasks_dir)

    try:
        assert "test/topic" not in fake_bus.subscriptions
        assert manager.tasks["EventTask"]["status"] == "stopped"
        assert not dummy_signals.task_status_changed.emitted

        result = manager.start_task("EventTask")

        assert result is True
        assert "test/topic" in fake_bus.subscriptions
        assert manager.tasks["EventTask"]["status"] == "listening"
        assert dummy_signals.task_status_changed.emitted
        args, _ = dummy_signals.task_status_changed.emitted[-1]
        assert args == ("EventTask", "listening")
    finally:
        manager.shutdown()


def test_start_task_event_subscription_failure_reports_error(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_event_task(tasks_dir, enabled=False)

    manager, fake_bus, dummy_signals = _create_manager(monkeypatch, tasks_dir)

    try:
        def failing_subscribe(topic: str, callback: Callable[[dict], None]):
            raise RuntimeError("subscription failed")

        fake_bus.subscribe = failing_subscribe  # type: ignore[assignment]

        result = manager.start_task("EventTask")

        assert result is False
        assert manager.tasks["EventTask"]["status"] == "stopped"
        assert "EventTask" not in manager._event_task_topics
        assert not fake_bus.subscriptions
        assert dummy_signals.task_failed.emitted
        args, _ = dummy_signals.task_failed.emitted[-1]
        assert args[0] == "EventTask"
        assert "subscription failed" in args[2]
        assert not dummy_signals.task_status_changed.emitted
    finally:
        manager.shutdown()


def test_run_task_retries_until_success(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    task_dir = tasks_dir / "RetryTask"
    config = {
        "name": "RetryTask",
        "module_type": "test",
        "enabled": False,
        "debug": False,
        "persist_state": False,
        "retry": {
            "max_attempts": 3,
            "backoff_strategy": "exponential",
            "backoff_interval_seconds": 0.05,
            "backoff_multiplier": 2,
            "backoff_max_interval_seconds": 0.2,
        },
        "trigger": {
            "type": "schedule",
            "config": {
                "type": "interval",
                "seconds": 60,
            },
        },
    }

    retry_script = (
        "from core.task_manager import TaskExecutionError\n\n"
        "def run(context, inputs):\n"
        "    attempt = context.get_state(\"attempt\", 0) + 1\n"
        "    context.update_state(\"attempt\", attempt)\n"
        "    fail_until = inputs.get(\"fail_until\", 0)\n"
        "    if attempt <= fail_until:\n"
        "        raise TaskExecutionError(f\"transient failure {attempt}\")\n"
        "    return attempt\n"
    )

    _write_task_files(task_dir, config, script_content=retry_script)

    manager, _, dummy_signals = _create_manager(monkeypatch, tasks_dir)

    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(TaskManager, "_sleep", staticmethod(fake_sleep))

    try:
        result = manager.run_task("RetryTask", {"fail_until": 2}, use_executor=False)
        assert result == 3
        assert sleep_calls == pytest.approx([0.05, 0.1])
        assert dummy_signals.task_succeeded.emitted
        assert not dummy_signals.task_failed.emitted
        assert manager.state_manager.get_state("RetryTask", "attempt") == 3
    finally:
        manager.shutdown()


def test_async_retry_emits_failure_after_max_attempts(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    task_dir = tasks_dir / "AlwaysFail"
    config = {
        "name": "AlwaysFail",
        "module_type": "test",
        "enabled": False,
        "debug": False,
        "persist_state": False,
        "retry": {
            "max_attempts": 2,
            "backoff_strategy": "fixed",
            "backoff_interval_seconds": 0.01,
            "backoff_multiplier": 2,
            "backoff_max_interval_seconds": 0.5,
        },
        "trigger": {
            "type": "schedule",
            "config": {
                "type": "interval",
                "seconds": 60,
            },
        },
    }

    failure_script = (
        "from core.task_manager import TaskExecutionError\n\n"
        "def run(context, inputs):\n"
        "    raise TaskExecutionError(\"permanent failure\")\n"
    )

    _write_task_files(task_dir, config, script_content=failure_script)

    manager, _, dummy_signals = _create_manager(monkeypatch, tasks_dir)

    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(TaskManager, "_sleep", staticmethod(fake_sleep))

    try:
        future = manager.run_task("AlwaysFail", use_executor=True)
        with pytest.raises(TaskExecutionError):
            future.result(timeout=1)

        assert dummy_signals.task_failed.emitted
        assert not dummy_signals.task_succeeded.emitted
        args, _ = dummy_signals.task_failed.emitted[-1]
        assert args[0] == "AlwaysFail"
        assert "failed after 2 attempts" in args[2]
        assert sleep_calls == pytest.approx([0.01])
    finally:
        manager.shutdown()


def test_event_task_disable_unsubscribes(prepared_manager, monkeypatch):
    manager, fake_bus, dummy_signals = prepared_manager
    calls: list[str] = []

    def fake_execute(self, task_name, inputs):
        calls.append(task_name)

    monkeypatch.setattr(TaskManager, "_execute_task_logic", fake_execute)

    assert "test/topic" in fake_bus.subscriptions

    updated_config = manager.get_task_config("EventTask")
    updated_config["enabled"] = False

    success, _ = manager.save_task_config("EventTask", updated_config)
    assert success
    assert "test/topic" not in fake_bus.subscriptions
    assert manager.tasks["EventTask"]["status"] == "stopped"
    assert dummy_signals.task_status_changed.emitted[-1][0] == ("EventTask", "stopped")

    fake_bus.publish("test/topic", {"key": "value"})
    assert not calls


def test_event_task_removed_after_delete(prepared_manager, monkeypatch):
    manager, fake_bus, _ = prepared_manager
    calls: list[str] = []

    def fake_execute(self, task_name, inputs):
        calls.append(task_name)

    monkeypatch.setattr(TaskManager, "_execute_task_logic", fake_execute)

    assert "test/topic" in fake_bus.subscriptions

    assert manager.delete_task("EventTask")
    assert "test/topic" not in fake_bus.subscriptions
    assert "EventTask" not in manager.tasks

    fake_bus.publish("test/topic", {"after": "delete"})
    assert not calls


def test_event_wrapper_uses_custom_max_hops(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    topic = "custom/topic"
    _create_event_task_with_hop_limit(tasks_dir,
                                      name="LimitedTask",
                                      topic=topic,
                                      max_hops=2)

    manager, fake_bus, _ = _create_manager(monkeypatch, tasks_dir)

    try:
        calls: list[str] = []

        def fake_execute(self, task_name, inputs):
            calls.append(task_name)

        monkeypatch.setattr(TaskManager, "_execute_task_logic", fake_execute)

        fake_bus.publish(topic, {"__hops": 3})
        assert not calls

        fake_bus.publish(topic, {"__hops": 2})
        assert calls == ["LimitedTask"]
    finally:
        manager.shutdown()


def test_scheduled_task_deleted_removes_job_and_stops_triggers(
        prepared_schedule_manager):
    manager, dummy_signals = prepared_schedule_manager

    job = manager.apscheduler.get_job("IntervalTask")
    assert job is not None

    assert manager.delete_task("IntervalTask")

    assert manager.apscheduler.get_job("IntervalTask") is None
    assert "IntervalTask" not in manager.tasks
    assert dummy_signals.task_status_changed.emitted
    assert dummy_signals.task_status_changed.emitted[-1][0] == (
        "IntervalTask", "stopped")


def test_event_task_renamed_updates_subscription(prepared_manager, monkeypatch):
    manager, fake_bus, _ = prepared_manager
    calls: list[str] = []

    def fake_execute(self, task_name, inputs):
        calls.append(task_name)

    monkeypatch.setattr(TaskManager, "_execute_task_logic", fake_execute)

    new_config = manager.get_task_config("EventTask")
    new_config["name"] = "RenamedTask"

    success, final_name = manager.save_task_config("EventTask", new_config)
    assert success
    assert final_name == "RenamedTask"
    assert "EventTask" not in manager.tasks
    assert "RenamedTask" in manager.tasks
    assert "test/topic" in fake_bus.subscriptions

    fake_bus.publish("test/topic", {"after": "rename"})
    assert calls == ["RenamedTask"]


def test_rename_task_updates_logger_filter(prepared_manager, monkeypatch):
    manager, _, dummy_signals = prepared_manager

    old_logger = manager.tasks["EventTask"]["logger"]

    monkeypatch.setattr("utils.logger.global_signals", dummy_signals)

    assert manager.rename_task("EventTask", "RenamedLoggerTask")

    assert not any(isinstance(f, TaskContextFilter) for f in getattr(old_logger, "filters", []))

    new_logger = manager.tasks["RenamedLoggerTask"]["logger"]

    handler = SignalHandler()
    new_logger.addHandler(handler)
    try:
        new_logger.info("Logger rename message")
    finally:
        new_logger.removeHandler(handler)

    assert dummy_signals.log_message.emitted
    args, _ = dummy_signals.log_message.emitted[-1]
    assert args[0] == "RenamedLoggerTask"


def test_rename_task_updates_config_on_disk(prepared_manager):
    manager, _, _ = prepared_manager

    new_name = "RenamedDiskTask"

    assert manager.rename_task("EventTask", new_name)
    assert new_name in manager.tasks
    assert "EventTask" not in manager.tasks

    config_path = Path(manager.tasks[new_name]["config"])
    with open(config_path, "r", encoding="utf-8") as config_file:
        stored_config = yaml.safe_load(config_file)

    assert stored_config["name"] == new_name

    reloaded_config = manager.get_task_config(new_name)
    assert reloaded_config["name"] == new_name

    success, final_name = manager.save_task_config(new_name, reloaded_config)
    assert success
    assert final_name == new_name

    with open(config_path, "r", encoding="utf-8") as config_file:
        persisted_config = yaml.safe_load(config_file)

    assert persisted_config["name"] == new_name


def test_rename_task_rebuilds_scheduler_job(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_interval_task(tasks_dir)

    manager, _, _ = _create_manager(monkeypatch, tasks_dir)

    try:
        assert manager.apscheduler.get_job("IntervalTask") is not None

        new_name = "RenamedIntervalTask"
        assert manager.rename_task("IntervalTask", new_name)

        assert manager.apscheduler.get_job("IntervalTask") is None
        new_job = manager.apscheduler.get_job(new_name)
        assert new_job is not None
        assert manager.tasks[new_name]['status'] == 'running'
    finally:
        manager.shutdown()


def test_start_all_tasks_does_not_duplicate_event_subscription(prepared_manager,
                                                               monkeypatch):
    manager, fake_bus, _ = prepared_manager

    subscribe_calls_before = list(fake_bus.subscribe_calls)

    manager.start_all_tasks()

    assert fake_bus.subscribe_calls == subscribe_calls_before


def test_multiple_event_tasks_share_topic(prepared_manager, monkeypatch):
    manager, fake_bus, _ = prepared_manager

    tasks_dir = Path(manager.tasks['EventTask']['path']).parent
    _create_event_task(tasks_dir, name="SecondTask", topic="test/topic")

    manager.load_tasks()

    calls: list[str] = []

    def fake_execute(self, task_name, inputs):
        calls.append(task_name)

    monkeypatch.setattr(TaskManager, "_execute_task_logic", fake_execute)

    fake_bus.publish("test/topic", {"trigger": "initial"})
    assert set(calls) == {"EventTask", "SecondTask"}

    updated_config = manager.get_task_config("EventTask")
    updated_config["enabled"] = False
    success, _ = manager.save_task_config("EventTask", updated_config)
    assert success

    calls.clear()
    fake_bus.publish("test/topic", {"trigger": "after-disable"})
    assert calls == ["SecondTask"]

    second_config = manager.get_task_config("SecondTask")
    second_config["enabled"] = False
    success, _ = manager.save_task_config("SecondTask", second_config)
    assert success
    assert "test/topic" not in fake_bus.subscriptions


def test_event_wrapper_uses_default_max_hops(prepared_manager, monkeypatch):
    manager, fake_bus, _ = prepared_manager

    calls: list[str] = []

    def fake_execute(self, task_name, inputs):
        calls.append(task_name)

    monkeypatch.setattr(TaskManager, "_execute_task_logic", fake_execute)

    fake_bus.publish("test/topic", {"__hops": 6})
    assert not calls

    fake_bus.publish("test/topic", {"__hops": 5})
    assert calls == ["EventTask"]


def test_stop_all_tasks_unsubscribes_event_tasks(prepared_manager, monkeypatch):
    manager, fake_bus, dummy_signals = prepared_manager
    calls: list[str] = []

    def fake_execute(self, task_name, inputs):
        calls.append(task_name)

    monkeypatch.setattr(TaskManager, "_execute_task_logic", fake_execute)

    fake_bus.publish("test/topic", {"first": True})
    assert calls == ["EventTask"]

    manager.stop_all_tasks()

    assert "test/topic" not in fake_bus.subscriptions
    assert dummy_signals.task_status_changed.emitted[-1][0] == ("EventTask", "stopped")

    fake_bus.publish("test/topic", {"second": True})
    assert calls == ["EventTask"]


def test_save_task_config_disables_interval_task(prepared_schedule_manager):
    manager, dummy_signals = prepared_schedule_manager

    assert manager.apscheduler.get_job("IntervalTask") is not None

    updated_config = manager.get_task_config("IntervalTask")
    updated_config["enabled"] = False

    success, _ = manager.save_task_config("IntervalTask", updated_config)

    assert success
    assert manager.apscheduler.get_job("IntervalTask") is None
    assert len(manager.apscheduler.get_jobs()) == 0
    assert manager.tasks["IntervalTask"]["status"] == "stopped"
    assert dummy_signals.task_status_changed.emitted[-1][0] == (
        "IntervalTask", "stopped")


def test_save_task_config_reenables_interval_task(prepared_schedule_manager):
    manager, dummy_signals = prepared_schedule_manager

    disabled_config = manager.get_task_config("IntervalTask")
    disabled_config["enabled"] = False
    assert manager.save_task_config("IntervalTask", disabled_config)[0]
    assert manager.apscheduler.get_job("IntervalTask") is None

    disabled_config["enabled"] = True
    success, _ = manager.save_task_config("IntervalTask", disabled_config)

    assert success
    job = manager.apscheduler.get_job("IntervalTask")
    assert job is not None
    assert len(manager.apscheduler.get_jobs()) == 1
    assert manager.tasks["IntervalTask"]["status"] == "running"
    assert dummy_signals.task_status_changed.emitted[-1][0] == (
        "IntervalTask", "running")


def test_save_task_config_updates_interval_trigger(prepared_schedule_manager):
    manager, dummy_signals = prepared_schedule_manager

    original_job = manager.apscheduler.get_job("IntervalTask")
    original_interval = original_job.trigger.interval.total_seconds()

    updated_config = manager.get_task_config("IntervalTask")
    updated_config["trigger"]["config"]["seconds"] = int(original_interval) + 4

    success, _ = manager.save_task_config("IntervalTask", updated_config)

    assert success
    refreshed_job = manager.apscheduler.get_job("IntervalTask")
    assert refreshed_job is not None
    assert len(manager.apscheduler.get_jobs()) == 1
    assert refreshed_job.trigger.interval.total_seconds() == pytest.approx(
        int(original_interval) + 4)
    assert manager.tasks["IntervalTask"]["status"] == "running"
    assert dummy_signals.task_status_changed.emitted[-1][0] == (
        "IntervalTask", "running")


def test_save_task_config_switches_interval_to_event(prepared_schedule_manager):
    manager, dummy_signals = prepared_schedule_manager

    task_name = "IntervalTask"
    assert manager.apscheduler.get_job(task_name) is not None

    original_config = manager.get_task_config(task_name)
    success, _ = manager.save_task_config(task_name, original_config)
    assert success
    assert manager.apscheduler.get_job(task_name) is not None

    event_config = manager.get_task_config(task_name)
    event_config["trigger"] = {
        "type": "event",
        "topic": "switch/topic"
    }

    success, _ = manager.save_task_config(task_name, event_config)

    assert success
    assert manager.apscheduler.get_job(task_name) is None
    assert manager.tasks[task_name]["status"] == "listening"
    assert dummy_signals.task_status_changed.emitted[-1][0] == (
        task_name, "listening")


def test_load_tasks_refreshes_scheduler_jobs(prepared_schedule_manager):
    manager, dummy_signals = prepared_schedule_manager

    job = manager.apscheduler.get_job("IntervalTask")
    assert job is not None
    assert job.trigger.interval.total_seconds() == pytest.approx(1)

    config_path = Path(manager.tasks["IntervalTask"]["config"])

    with open(config_path, "r", encoding="utf-8") as config_file:
        config_data = yaml.safe_load(config_file)

    config_data["trigger"]["config"]["seconds"] = 3
    with open(config_path, "w", encoding="utf-8") as config_file:
        yaml.safe_dump(config_data,
                      config_file,
                      allow_unicode=True,
                      sort_keys=False)

    manager.load_tasks()

    jobs = manager.apscheduler.get_jobs()
    assert len(jobs) == 1
    refreshed_job = jobs[0]
    assert refreshed_job.id == "IntervalTask"
    assert refreshed_job.trigger.interval.total_seconds() == pytest.approx(3)

    with open(config_path, "r", encoding="utf-8") as config_file:
        updated_config = yaml.safe_load(config_file)

    updated_config["enabled"] = False
    with open(config_path, "w", encoding="utf-8") as config_file:
        yaml.safe_dump(updated_config,
                      config_file,
                      allow_unicode=True,
                      sort_keys=False)

    manager.load_tasks()

    assert manager.apscheduler.get_jobs() == []
    assert manager.tasks["IntervalTask"]["status"] == "stopped"
    assert dummy_signals.task_status_changed.emitted[-1][0] == (
        "IntervalTask", "stopped")


def test_rename_persistent_task_preserves_state(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    initial_state = {"count": 3, "enabled": True}
    _create_persistent_task(tasks_dir, state=initial_state)

    manager, fake_bus, dummy_signals = _create_manager(monkeypatch, tasks_dir)

    try:
        assert manager.state_manager.get_state("PersistentTask", "count") == 3

        assert manager.rename_task("PersistentTask", "RenamedTask")

        assert "RenamedTask" in manager.tasks
        assert "PersistentTask" not in manager.tasks
        assert manager.state_manager.get_state("RenamedTask", "count") == 3
        assert manager.state_manager.get_state("PersistentTask", "count") is None

        manager.state_manager.update_state("RenamedTask", "count", 5)

        renamed_path = Path(manager.tasks["RenamedTask"]["path"])
        manager.state_manager.save_state("RenamedTask", str(renamed_path))

        with open(renamed_path / "state.json", "r", encoding="utf-8") as state_file:
            persisted_state = json.load(state_file)

        assert persisted_state["count"] == 5
        assert persisted_state["enabled"] is True
        assert not fake_bus.unsubscribe_calls  # no subscriptions for disabled task
        assert not dummy_signals.task_status_changed.emitted
    finally:
        manager.shutdown()


def test_scheduler_submit_passes_context_keyword(prepared_manager):
    manager, _, _ = prepared_manager

    payload = {"value": 1}
    future = manager.scheduler_manager.submit(
        manager._prepare_and_run_task,
        "EventTask",
        payload,
        context=types.SimpleNamespace(task_name="EventTask"),
    )

    result = future.result(timeout=3)
    assert result == payload


def test_task_manager_rejects_task_name_with_separator(temp_task_manager, caplog):
    manager, module_type = temp_task_manager

    with caplog.at_level(logging.WARNING):
        assert not manager.create_task("bad/name", module_type)

    assert "path separator" in caplog.text
    assert manager.get_task_count() == 0
    assert os.listdir(manager.tasks_dir) == []


def test_task_manager_rejects_empty_task_name(temp_task_manager, caplog):
    manager, module_type = temp_task_manager

    with caplog.at_level(logging.WARNING):
        assert not manager.create_task("", module_type)

    assert "cannot be empty" in caplog.text
    assert manager.get_task_count() == 0
    assert os.listdir(manager.tasks_dir) == []


def test_task_manager_rejects_task_name_outside_directory(temp_task_manager,
                                                          caplog):
    manager, module_type = temp_task_manager

    with caplog.at_level(logging.WARNING):
        assert not manager.create_task("..", module_type)

    assert "outside the tasks directory" in caplog.text
    assert manager.get_task_count() == 0


def test_new_task_widget_warns_on_invalid_task_name(temp_task_manager,
                                                    monkeypatch):
    manager, module_type = temp_task_manager

    assert language_manager.load_language('en')

    from view import new_task_widget as new_task_widget_module

    widget = NewTaskWidget(manager)
    widget.task_name_input.setText("bad/name")

    messages: list[tuple[str, str]] = []

    def record_warning(parent, title, message):
        messages.append((title, message))

    monkeypatch.setattr(new_task_widget_module.QMessageBox,
                        "warning",
                        staticmethod(record_warning))

    create_called = False

    def unexpected_create(*args, **kwargs):
        nonlocal create_called
        create_called = True
        return True

    monkeypatch.setattr(manager, "create_task", unexpected_create)

    widget.create_task()

    assert not create_called
    assert messages
    assert messages[0][1] == _("task_name_separator_error")
