import os
import sys
import types
from pathlib import Path
from typing import Iterable

import pytest

try:
    from PyQt5.QtWidgets import QMessageBox as _QMessageBox  # noqa: F401
except Exception:  # pragma: no cover - executed in headless test environments
    PyQt5 = types.ModuleType("PyQt5")
    QtWidgets = types.ModuleType("PyQt5.QtWidgets")

    class _StubMessageBox:
        Ok = 0

        @staticmethod
        def warning(*args, **kwargs):
            return _StubMessageBox.Ok

        @staticmethod
        def information(*args, **kwargs):
            return _StubMessageBox.Ok

        @staticmethod
        def critical(*args, **kwargs):
            return _StubMessageBox.Ok

    QtWidgets.QMessageBox = _StubMessageBox
    PyQt5.QtWidgets = QtWidgets

    sys.modules.setdefault("PyQt5", PyQt5)
    sys.modules.setdefault("PyQt5.QtWidgets", QtWidgets)

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.task_manager import TaskManager
from core.module_manager import ModuleManager
from core.scheduler import SchedulerManager


@pytest.fixture
def manager_for_validation(tmp_path):
    tasks_dir = tmp_path / "tasks"
    modules_dir = tmp_path / "modules"

    module_manager_instance = ModuleManager()
    default_modules_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "modules"))
    original_module_path = getattr(module_manager_instance, "module_path", default_modules_dir)

    scheduler = SchedulerManager()
    manager = TaskManager(scheduler_manager=scheduler,
                          tasks_dir=str(tasks_dir),
                          modules_dir=str(modules_dir))

    try:
        yield manager
    finally:
        manager.shutdown(wait=False)
        module_manager_instance.set_module_path(original_module_path)


@pytest.mark.parametrize(
    ("task_name", "expected"),
    [
        ("", (False, "empty")),
        ("simple-task", (True, None)),
        ("valid_name.with.dots", (True, None)),
        ("..", (False, "outside")),
        ("../escape", (False, "separator")),
    ],
)
def test_validate_task_name_handles_basic_cases(manager_for_validation, task_name, expected):
    is_valid, error_code = manager_for_validation.validate_task_name(task_name)
    assert (is_valid, error_code) == expected


def test_validate_task_name_rejects_paths_with_separators(manager_for_validation):
    separators: Iterable[str] = {os.sep}
    if os.altsep:
        separators = set(separators) | {os.altsep}

    for separator in separators:
        candidate = f"bad{separator}name"
        is_valid, error_code = manager_for_validation.validate_task_name(candidate)
        assert (is_valid, error_code) == (False, "separator")


def test_validate_task_name_rejects_absolute_paths(manager_for_validation):
    absolute_candidate = os.path.abspath("forbidden_task")
    is_valid, error_code = manager_for_validation.validate_task_name(absolute_candidate)
    assert (is_valid, error_code) == (False, "separator")


def test_validate_task_name_accepts_nested_names_without_traversal(manager_for_validation):
    candidate = "nested_task"
    is_valid, error_code = manager_for_validation.validate_task_name(candidate)
    assert is_valid
    assert error_code is None
