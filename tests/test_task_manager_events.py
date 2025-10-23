import importlib.util
import json
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


class _DummySignal:
    def connect(self, *args, **kwargs):
        return None

    def disconnect(self, *args, **kwargs):
        return None

    def emit(self, *args, **kwargs):
        return None


QtCore.QObject = object
QtCore.pyqtSignal = lambda *args, **kwargs: _DummySignal()
QtWidgets.QMessageBox = type(
    "QMessageBox", (), {"critical": staticmethod(lambda *args, **kwargs: None)})

PyQt5.QtCore = QtCore
PyQt5.QtWidgets = QtWidgets

sys.modules.setdefault("PyQt5", PyQt5)
sys.modules.setdefault("PyQt5.QtCore", QtCore)
sys.modules.setdefault("PyQt5.QtWidgets", QtWidgets)

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from core.context import TaskContextFilter
from core.scheduler import SchedulerManager
from core.task_manager import (
    SCHEDULED_TRIGGER_TYPES,
    TaskManager,
    is_scheduled_trigger,
)
from utils.logger import SignalHandler


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


def _write_task_files(task_dir: Path, config: dict) -> None:
    task_dir.mkdir()

    import yaml

    with open(task_dir / "config.yaml", "w", encoding="utf-8") as config_file:
        yaml.safe_dump(config,
                      config_file,
                      allow_unicode=True,
                      sort_keys=False)

    with open(task_dir / "main.py", "w", encoding="utf-8") as script_file:
        script_file.write(_SCRIPT_CONTENT)


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
