import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PyQt5.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - handled via pytest skip
    pytest.skip(
        f"PyQt5 is required for JsonConfigEditorWidget tests: {exc}",
        allow_module_level=True,
    )

from utils.theme import theme_manager
from view.json_config_editor_widget import JsonConfigEditorWidget


class _DummyTaskManager:
    def get_task_config(self, task_name):
        return {}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def restore_theme():
    original_dir = theme_manager.theme_dir
    original_theme = theme_manager.current_theme_name
    yield
    theme_manager.theme_dir = original_dir
    theme_manager.current_theme_name = original_theme


def _assert_default_stylesheet(widget):
    stylesheet = widget.editor.styleSheet()
    assert "background-color: #1E1E1E;" in stylesheet
    assert "color: #D4D4D4;" in stylesheet
    assert "border: 1px solid #3c3c3c;" in stylesheet


def test_editor_style_falls_back_when_theme_missing(tmp_path, qapp, caplog):
    theme_manager.theme_dir = str(tmp_path)
    theme_manager.current_theme_name = "missing"

    with caplog.at_level(logging.WARNING):
        widget = JsonConfigEditorWidget("demo", _DummyTaskManager())

    try:
        _assert_default_stylesheet(widget)
        assert "Falling back to default editor style." in caplog.text
    finally:
        widget.deleteLater()


def test_editor_style_falls_back_when_theme_corrupted(tmp_path, qapp, caplog):
    theme_manager.theme_dir = str(tmp_path)
    theme_manager.current_theme_name = "corrupted"
    theme_file = tmp_path / "corrupted.json"
    theme_file.write_text("{ invalid json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        widget = JsonConfigEditorWidget("demo", _DummyTaskManager())

    try:
        _assert_default_stylesheet(widget)
        assert "Falling back to default editor style." in caplog.text
    finally:
        widget.deleteLater()
