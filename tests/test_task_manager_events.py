import os
import sys
import types
from pathlib import Path
from typing import Callable

import pytest

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

from core.scheduler import SchedulerManager
from core.task_manager import TaskManager


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


def _write_task(task_dir: Path, config: dict) -> None:
    task_dir.mkdir()

    import yaml

    with open(task_dir / "config.yaml", "w", encoding="utf-8") as config_file:
        yaml.safe_dump(config, config_file)

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

    _write_task(task_dir, config)


def _create_interval_task(tasks_dir: Path, name: str = "IntervalTask",
                          seconds: int = 5, enabled: bool = True):
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

    _write_task(task_dir, config)


@pytest.fixture()
def prepared_manager(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_event_task(tasks_dir)

    fake_bus = FakeBusManager()
    dummy_signals = DummySignals()
    monkeypatch.setattr("core.task_manager.message_bus_manager", fake_bus)
    monkeypatch.setattr("core.task_manager.global_signals", dummy_signals)

    scheduler = SchedulerManager()
    manager = TaskManager(scheduler_manager=scheduler,
                          tasks_dir=str(tasks_dir))

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
