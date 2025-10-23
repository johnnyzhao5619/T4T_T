import os
import sys
import threading
import time

import pytest

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.service_manager import ServiceState
from utils.message_bus import BusConnectionState
from utils.signals import global_signals


class FakeConfigManager:
    def __init__(self, mode: str = 'embedded'):
        self._mode = mode
        self.mqtt = {'host': 'localhost', 'port': 1883}

    def get(self, section: str, key: str, fallback=None):
        if section.lower() == 'mqtt' and key.lower() == 'mode':
            return self._mode
        return fallback


class FakeServiceManager:
    def __init__(self, delay: float = 0.05):
        self._state = ServiceState.STOPPED
        self._delay = delay
        self.start_calls = 0
        self._service = object()
        self.running_event = threading.Event()

    def get_service_state(self, name: str):
        return self._state

    def get_service(self, name: str):
        return self._service

    def start_service(self, name: str):
        self.start_calls += 1
        self._state = ServiceState.STARTING

        def _delayed_start():
            time.sleep(self._delay)
            self._state = ServiceState.RUNNING
            self.running_event.set()
            global_signals.service_state_changed.emit(name, ServiceState.RUNNING)

        threading.Thread(target=_delayed_start, daemon=True).start()


class StubBus:
    def __init__(self, config, logger, on_state_change):
        self.connect_calls = 0
        self.connected_before_running = False
        self.disconnect_calls = 0
        self._subscriptions = {}
        self._running_event = None

    def attach_running_event(self, event: threading.Event):
        self._running_event = event

    def connect(self):
        self.connect_calls += 1
        if self._running_event and not self._running_event.is_set():
            self.connected_before_running = True

    def disconnect(self):
        self.disconnect_calls += 1

    def publish(self, topic, payload):
        return None

    def subscribe(self, topic, callback):
        self._subscriptions.setdefault(topic, []).append(callback)

    def unsubscribe(self, topic, callback=None):
        callbacks = self._subscriptions.get(topic, [])
        if callback and callback in callbacks:
            callbacks.remove(callback)
        elif callback is None:
            callbacks.clear()


class SimpleSignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def disconnect(self, callback):
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


@pytest.fixture
def stub_bus_class(monkeypatch):
    instances = []

    def _factory(config, logger, on_state_change):
        bus = StubBus(config, logger, on_state_change)
        instances.append(bus)
        return bus

    monkeypatch.setattr('utils.message_bus.MqttBus', _factory)
    return instances


@pytest.fixture
def service_state_signal(monkeypatch):
    signal = SimpleSignal()
    monkeypatch.setattr(global_signals, 'service_state_changed', signal, raising=False)
    return signal


@pytest.fixture
def message_bus_status_signal(monkeypatch):
    signal = SimpleSignal()
    monkeypatch.setattr(global_signals, 'message_bus_status_changed', signal, raising=False)
    return signal


def test_connect_waits_for_embedded_broker(monkeypatch, stub_bus_class,
                                           service_state_signal):
    from utils.message_bus import MessageBusManager

    fake_service_manager = FakeServiceManager(delay=0.05)
    config_manager = FakeConfigManager(mode='embedded')

    manager = MessageBusManager(config_manager=config_manager)
    manager._service_manager = fake_service_manager

    # Attach running event to stub bus
    assert stub_bus_class, "Stub bus should have been instantiated"
    stub_bus = stub_bus_class[0]
    stub_bus.attach_running_event(fake_service_manager.running_event)

    manager.connect()

    assert fake_service_manager.start_calls == 1
    assert fake_service_manager.running_event.wait(0.5)
    assert stub_bus.connect_calls == 1
    assert not stub_bus.connected_before_running


def test_connect_emits_disconnect_on_timeout(monkeypatch, stub_bus_class,
                                             service_state_signal,
                                             message_bus_status_signal):
    from utils.message_bus import MessageBusManager

    monkeypatch.setattr('utils.message_bus.SERVICE_START_TIMEOUT_SECONDS', 0,
                        raising=False)

    class NeverRunningServiceManager:
        def __init__(self):
            self._state = ServiceState.STOPPED
            self.start_calls = 0
            self._service = object()

        def get_service_state(self, name: str):
            return self._state

        def get_service(self, name: str):
            return self._service

        def start_service(self, name: str):
            self.start_calls += 1
            self._state = ServiceState.STARTING

    config_manager = FakeConfigManager(mode='embedded')
    manager = MessageBusManager(config_manager=config_manager)
    manager._service_manager = NeverRunningServiceManager()

    events = []
    message_bus_status_signal.connect(lambda status, message: events.append((status, message)))

    manager.connect()

    assert events, "Expected a disconnect event when service start times out"
    status, message = events[-1]
    assert status == BusConnectionState.DISCONNECTED.value
    assert "Timed out" in message

    stub_bus = stub_bus_class[0]
    assert stub_bus.connect_calls == 0


def test_connect_emits_disconnect_on_failed_service(monkeypatch, stub_bus_class,
                                                    service_state_signal,
                                                    message_bus_status_signal):
    from utils.message_bus import MessageBusManager

    failure_event = threading.Event()

    class FailingServiceManager:
        def __init__(self):
            self._state = ServiceState.STOPPED
            self._service = object()

        def get_service_state(self, name: str):
            return self._state

        def get_service(self, name: str):
            return self._service

        def start_service(self, name: str):
            self._state = ServiceState.STARTING

            def _fail():
                time.sleep(0.01)
                self._state = ServiceState.FAILED
                failure_event.set()
                global_signals.service_state_changed.emit(name, ServiceState.FAILED)

            threading.Thread(target=_fail, daemon=True).start()

    config_manager = FakeConfigManager(mode='embedded')
    manager = MessageBusManager(config_manager=config_manager)
    manager._service_manager = FailingServiceManager()

    events = []
    message_bus_status_signal.connect(lambda status, message: events.append((status, message)))

    manager.connect()

    assert failure_event.wait(1.0), "Expected service failure event to be emitted"
    assert events, "Expected a disconnect event when service fails to start"
    status, message = events[-1]
    assert status == BusConnectionState.DISCONNECTED.value
    assert "entered FAILED state" in message or "FAILED" in message

    stub_bus = stub_bus_class[0]
    assert stub_bus.connect_calls == 0
