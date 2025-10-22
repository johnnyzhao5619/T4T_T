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
        self.subscriptions: dict[str, Callable[[dict], None]] = {}

    def subscribe(self, topic: str, callback):
        self.subscriptions[topic] = callback

    def unsubscribe(self, topic: str):
        self.subscriptions.pop(topic, None)

    def publish(self, topic: str, payload: dict):
        callback = self.subscriptions.get(topic)
        if callback:
            callback(payload)


def _create_event_task(tasks_dir: Path, name: str = "EventTask",
                       topic: str = "test/topic", enabled: bool = True):
    task_dir = tasks_dir / name
    task_dir.mkdir()

    config = {
        "name": name,
        "module_type": "test",
        "enabled": enabled,
        "trigger": {
            "type": "event",
            "topic": topic
        }
    }

    script_content = "def run(context, inputs):\n    return inputs\n"

    import yaml
    with open(task_dir / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)

    with open(task_dir / "main.py", "w", encoding="utf-8") as f:
        f.write(script_content)


@pytest.fixture()
def prepared_manager(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    _create_event_task(tasks_dir)

    fake_bus = FakeBusManager()
    monkeypatch.setattr("core.task_manager.message_bus_manager", fake_bus)
    monkeypatch.setattr("core.task_manager.global_signals", DummySignals())

    scheduler = SchedulerManager()
    manager = TaskManager(scheduler_manager=scheduler,
                          tasks_dir=str(tasks_dir))

    yield manager, fake_bus

    manager.shutdown()


def test_event_task_disable_unsubscribes(prepared_manager, monkeypatch):
    manager, fake_bus = prepared_manager
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

    fake_bus.publish("test/topic", {"key": "value"})
    assert not calls


def test_event_task_removed_after_delete(prepared_manager, monkeypatch):
    manager, fake_bus = prepared_manager
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
    manager, fake_bus = prepared_manager
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
