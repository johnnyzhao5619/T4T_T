import importlib
import json
import logging
import sys
from pathlib import Path
from types import ModuleType

import pytest

PyQt5 = ModuleType("PyQt5")
QtWidgets = ModuleType("PyQt5.QtWidgets")
QtCore = ModuleType("PyQt5.QtCore")


class _DummyMessageBox:
    @staticmethod
    def critical(*args, **kwargs):
        return None

    @staticmethod
    def information(*args, **kwargs):
        return None

    @staticmethod
    def warning(*args, **kwargs):
        return None


QtWidgets.QMessageBox = _DummyMessageBox
PyQt5.QtWidgets = QtWidgets
PyQt5.QtCore = QtCore
sys.modules.setdefault("PyQt5", PyQt5)
sys.modules.setdefault("PyQt5.QtWidgets", QtWidgets)
sys.modules.setdefault("PyQt5.QtCore", QtCore)


class _DummyQObject:
    def __init__(self, *args, **kwargs):
        pass


class _DummySignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback, *args, **kwargs):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


QtCore.QObject = _DummyQObject
QtCore.pyqtSignal = lambda *args, **kwargs: _DummySignal()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.context import TaskContext
from core.scheduler import SchedulerManager
from core.state_manager import StateManager
from core.task_manager import TaskExecutionError, TaskManager
from utils.config import load_yaml


@pytest.fixture
def google_client_stubs(monkeypatch):
    class FakeExecutable:
        def __init__(self, response):
            self._response = response

        def execute(self):
            return self._response

    class FakeValuesResource:
        def __init__(self):
            self._get_response = {"values": []}
            self.update_calls = []
            self.raise_error = None

        def set_get_response(self, response):
            self._get_response = response

        def get(self, spreadsheetId, range):  # noqa: N803 - mimic API
            self.last_get = {"spreadsheetId": spreadsheetId, "range": range}
            return FakeExecutable(self._get_response)

        def update(self, spreadsheetId, range, valueInputOption, body):  # noqa: N803
            if self.raise_error:
                raise self.raise_error("simulated error")
            self.update_calls.append({
                "spreadsheetId": spreadsheetId,
                "range": range,
                "valueInputOption": valueInputOption,
                "body": body,
            })
            updated = sum(len(row) for row in body.get("values", []))
            return FakeExecutable({"updatedCells": updated})

    class FakeSpreadsheets:
        def __init__(self, values_resource):
            self._values = values_resource

        def values(self):
            return self._values

    class FakeSheetsService:
        def __init__(self, values_resource):
            self._spreadsheets = FakeSpreadsheets(values_resource)

        def spreadsheets(self):
            return self._spreadsheets

    fake_values = FakeValuesResource()
    fake_service = FakeSheetsService(fake_values)

    discovery_module = ModuleType("googleapiclient.discovery")
    discovery_module.build = lambda *args, **kwargs: fake_service  # type: ignore[assignment]

    class FakeHttpError(Exception):
        pass

    errors_module = ModuleType("googleapiclient.errors")
    errors_module.HttpError = FakeHttpError

    class FakeRequest:  # noqa: D401 - simple placeholder
        """Stub request object."""

    transport_module = ModuleType("google.auth.transport.requests")
    transport_module.Request = FakeRequest

    class FakeRefreshError(Exception):
        pass

    exceptions_module = ModuleType("google.auth.exceptions")
    exceptions_module.RefreshError = FakeRefreshError

    class FakeCredentials:
        def __init__(self, payload):
            self._payload = payload
            self.refresh_token = payload.get("refresh_token")
            self.expired = payload.get("expired", False)
            self.valid = payload.get("valid", True)

        @classmethod
        def from_authorized_user_file(cls, path, scopes):
            with open(path, "r", encoding="utf-8") as fp:
                payload = json.load(fp)
            payload.setdefault("valid", True)
            payload.setdefault("expired", False)
            payload.setdefault("refresh_token", payload.get("refresh_token"))
            instance = cls(payload)
            instance._scopes = scopes
            return instance

        def refresh(self, request):  # noqa: D401 - mimic API signature
            if self.refresh_token is None:
                raise FakeRefreshError("missing refresh token")
            self.valid = True
            self.expired = False

        def to_json(self):
            return json.dumps({"token": "refreshed"})

    credentials_module = ModuleType("google.oauth2.credentials")
    credentials_module.Credentials = FakeCredentials

    # Register stubs
    monkeypatch.setitem(sys.modules, "googleapiclient", ModuleType("googleapiclient"))
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery_module)
    monkeypatch.setitem(sys.modules, "googleapiclient.errors", errors_module)
    monkeypatch.setitem(sys.modules, "google.oauth2", ModuleType("google.oauth2"))
    monkeypatch.setitem(sys.modules, "google.oauth2.credentials", credentials_module)
    monkeypatch.setitem(sys.modules, "google.auth", ModuleType("google.auth"))
    monkeypatch.setitem(sys.modules, "google.auth.transport", ModuleType("google.auth.transport"))
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", transport_module)
    monkeypatch.setitem(sys.modules, "google.auth.exceptions", exceptions_module)

    stub_namespace = {
        "service": fake_service,
        "values": fake_values,
        "errors": errors_module,
        "exceptions": exceptions_module,
        "credentials_cls": FakeCredentials,
    }
    return stub_namespace


@pytest.fixture
def sheet_task_config(tmp_path):
    manifest_path = Path(__file__).resolve().parent.parent / "modules" / "google_sheet_sync" / "manifest.yaml"
    config = load_yaml(str(manifest_path))
    config["settings"]["spreadsheet_id"] = "spreadsheet123"
    config["settings"]["read_range"] = "Sheet1!A1:B2"
    config["settings"]["write_range"] = "Sheet1!A1"
    config["oauth"]["credentials_file"] = "oauth/client_secret.json"
    config["oauth"]["token_file"] = "oauth/token.json"
    return config


def _build_context(tmp_path, config):
    state_manager = StateManager()
    logger = logging.getLogger("test.google_sheet")
    logger.setLevel(logging.INFO)
    return TaskContext("test_task", logger, config, str(tmp_path), state_manager)


def test_run_google_sheet_sync_updates_state(tmp_path, google_client_stubs, sheet_task_config):
    tmp_task_dir = tmp_path / "task"
    tmp_task_dir.mkdir()
    oauth_dir = tmp_task_dir / "oauth"
    oauth_dir.mkdir()
    credentials_path = oauth_dir / "client_secret.json"
    token_path = oauth_dir / "token.json"

    # Prepare credential placeholder files
    credentials_path.write_text("{}", encoding="utf-8")
    token_path.write_text(json.dumps({"valid": True}), encoding="utf-8")

    sheet_task_config["persist_state"] = True
    context = _build_context(tmp_task_dir, sheet_task_config)

    # Import module after stubs are in place
    from modules.google_sheet_sync import google_sheet_sync_template as module
    module = importlib.reload(module)

    google_client_stubs["values"].set_get_response({"values": [["A", "1"], ["B", "2"]]})

    result = module.run(context, {"values": [["X", "10"]]})

    assert result == {"fetched_rows": 2, "updated_cells": 2}
    state_snapshot = context.state_manager.get_state("test_task", "google_sheet_sync", {})
    assert state_snapshot.get("fetched_rows") == 2
    assert state_snapshot.get("updated_cells") == 2
    assert google_client_stubs["values"].update_calls, "update 应至少调用一次"


def test_run_google_sheet_sync_raises_on_http_error(tmp_path, google_client_stubs, sheet_task_config):
    tmp_task_dir = tmp_path / "task"
    tmp_task_dir.mkdir()
    oauth_dir = tmp_task_dir / "oauth"
    oauth_dir.mkdir()
    (oauth_dir / "client_secret.json").write_text("{}", encoding="utf-8")
    (oauth_dir / "token.json").write_text(json.dumps({"valid": True}), encoding="utf-8")

    context = _build_context(tmp_task_dir, sheet_task_config)

    from modules.google_sheet_sync import google_sheet_sync_template as module
    module = importlib.reload(module)

    class Boom(google_client_stubs["errors"].HttpError):
        pass

    google_client_stubs["values"].raise_error = Boom

    with pytest.raises(TaskExecutionError):
        module.run(context, {"values": [["X"]]})


def test_task_manager_creates_google_sheet_task_with_oauth_files(tmp_path):
    scheduler = SchedulerManager()
    tasks_dir = tmp_path / "tasks"
    modules_dir = Path(__file__).resolve().parent.parent / "modules"

    manager = TaskManager(scheduler_manager=scheduler,
                          tasks_dir=str(tasks_dir),
                          modules_dir=str(modules_dir))
    try:
        created = manager.create_task("sheet_job", "google_sheet_sync")
        assert created

        task_path = tasks_dir / "sheet_job"
        config = load_yaml(task_path / "config.yaml")
        assert config["oauth"]["scopes"] == ["https://www.googleapis.com/auth/spreadsheets"]
        assert (task_path / "oauth" / "client_secret.sample.json").exists()
        assert (task_path / "oauth" / "client_secret.json").exists()
    finally:
        manager.apscheduler.shutdown(wait=False)
        scheduler.shutdown()
