import importlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PyQt5.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - handled via pytest skip
    pytest.skip(
        f"PyQt5 is required for MessageBusMonitorWidget tests: {exc}",
        allow_module_level=True,
    )

from core import service_manager as service_manager_module
from utils import i18n


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def message_bus_module():
    original_instance = service_manager_module.ServiceManager._instance
    original_singleton = service_manager_module.service_manager

    service_manager_module.ServiceManager._instance = None
    service_manager_module.service_manager = service_manager_module.ServiceManager()

    module = importlib.import_module("view.message_bus_monitor_widget")
    module = importlib.reload(module)

    try:
        yield module
    finally:
        service_manager_module.ServiceManager._instance = original_instance
        service_manager_module.service_manager = original_singleton
        module.service_manager = original_singleton
        importlib.reload(module)


def test_update_status_handles_unregistered_service(qapp, message_bus_module):
    module = message_bus_module

    original_translations = i18n.language_manager.translations
    original_language = i18n.language_manager.current_language

    i18n.language_manager.load_language("zh-CN")

    widget = module.MessageBusMonitorWidget()

    try:
        widget.update_status()

        expected_status = i18n._("service_status_unregistered")
        assert widget.status_label.text() == f"⚪ <strong>{expected_status}</strong>"
        assert "#7f8c8d" in widget.status_label.styleSheet()
        assert not widget.start_button.isEnabled()
        assert not widget.stop_button.isEnabled()
        assert widget.host_label.text() == "N/A"
        assert widget.port_label.text() == "N/A"
    finally:
        widget.deleteLater()
        i18n.language_manager.translations = original_translations
        i18n.language_manager.current_language = original_language


def test_signals_disconnect_on_close(qapp, message_bus_module):
    module = message_bus_module

    signal_names = [
        "service_state_changed",
        "message_published",
        "message_received",
        "mqtt_stats_updated",
    ]

    def collect_counts():
        return {
            name: getattr(module.global_signals, name).receivers()
            for name in signal_names
        }

    baseline_counts = collect_counts()

    widget = module.MessageBusMonitorWidget()

    try:
        connected_counts = collect_counts()
        for name in signal_names:
            assert connected_counts[name] == baseline_counts[name] + 1

        module.global_signals.message_received.emit("demo/topic", "payload")
        qapp.processEvents()
        initial_text = widget.text_browser.toPlainText()
        assert initial_text.strip(), "Expected the widget to receive the signal"

        widget.close()
        qapp.processEvents()

        closed_counts = collect_counts()
        for name in signal_names:
            assert closed_counts[name] == baseline_counts[name]

        module.global_signals.message_received.emit("demo/topic", "payload")
        qapp.processEvents()
        assert widget.text_browser.toPlainText() == initial_text
    finally:
        widget.deleteLater()
        qapp.processEvents()
