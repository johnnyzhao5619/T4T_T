import os
import sys

import pytest

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

import core.service_manager as service_manager_module
from core.service_interface import ServiceInterface
from core.service_manager import ServiceState


class DummyService(ServiceInterface):
    def __init__(self):
        self.stop_called = 0
        self.disconnect_called = 0

    def start(self):
        return

    def stop(self):
        self.stop_called += 1

    def disconnect_signals(self):
        self.disconnect_called += 1


@pytest.fixture
def fresh_service_manager():
    original_instance = service_manager_module.ServiceManager._instance
    original_singleton = service_manager_module.service_manager
    service_manager_module.ServiceManager._instance = None
    manager = service_manager_module.ServiceManager()
    service_manager_module.service_manager = manager
    try:
        yield manager
    finally:
        service_manager_module.ServiceManager._instance = original_instance
        service_manager_module.service_manager = original_singleton


def test_service_manager_has_no_default_services(fresh_service_manager):
    assert 'mqtt_broker' not in fresh_service_manager._services


def test_register_service_replaces_existing_instance(fresh_service_manager):
    manager = fresh_service_manager
    first = DummyService()
    manager.register_service('dummy', first)
    manager._service_states['dummy'] = ServiceState.RUNNING

    replacement = DummyService()
    manager.register_service('dummy', replacement)

    assert first.stop_called == 1
    assert first.disconnect_called == 1
    assert manager.get_service('dummy') is replacement
    assert manager.get_service_state('dummy') == ServiceState.STOPPED
