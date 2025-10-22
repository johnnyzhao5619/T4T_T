import enum
import enum
import logging
import threading
from typing import Dict, Optional

from services.embedded_mqtt_broker import EmbeddedMQTTBroker
from utils.signals import global_signals
from .service_interface import ServiceInterface


class ServiceState(enum.Enum):
    """Enumeration for the state of a background service."""
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


class ServiceManager:
    """
    Singleton manager for background services within the application.
    Handles the lifecycle of services like an embedded MQTT broker.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ServiceManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # Ensure __init__ is called only once
        if not hasattr(self, '_initialized'):
            self._services: Dict[str, ServiceInterface] = {}
            self._service_states: Dict[str, ServiceState] = {}
            self._service_threads: Dict[str, threading.Thread] = {}
            self._logger = logging.getLogger(self.__class__.__name__)
            self._initialized = True

    def register_service(self, name: str, service: ServiceInterface):
        """Registers a new service with the manager."""
        self._logger.info(f"Registering service: {name}")
        self._services[name] = service
        self._service_states[name] = ServiceState.STOPPED

    def start_service(self, name: str):
        """Starts a registered service in a separate thread."""
        if name not in self._services:
            self._logger.error(f"Service '{name}' not registered.")
            return

        if self._service_states.get(name) in [
                ServiceState.RUNNING, ServiceState.STARTING
        ]:
            self._logger.warning(
                f"Service '{name}' is already running or starting.")
            return

        if name in self._service_threads and self._service_threads[
                name].is_alive():
            self._logger.warning(
                f"Service thread for '{name}' is still alive. Cannot start.")
            return

        self._set_state(name, ServiceState.STARTING)
        thread = threading.Thread(target=self._run_service,
                                  args=(name, ),
                                  daemon=True)
        self._service_threads[name] = thread
        thread.start()

    def stop_service(self, name: str):
        """Stops a running service."""
        if name not in self._services:
            self._logger.error(f"Service '{name}' not registered.")
            return

        if self._service_states.get(name) not in [ServiceState.RUNNING]:
            self._logger.warning(f"Service '{name}' is not running.")
            return

        self._set_state(name, ServiceState.STOPPING)
        service = self._services[name]
        try:
            service.stop()
        except Exception as e:
            self._logger.error(f"Error stopping service '{name}': {e}")
            self._set_state(name, ServiceState.FAILED)

        # The service's stop method should handle thread termination.
        # We just update the state here.
        if self._service_threads[name].is_alive():
            self._service_threads[name].join(
                timeout=5)  # Wait for thread to die

        self._set_state(name, ServiceState.STOPPED)

    def get_service_state(self, name: str) -> Optional[ServiceState]:
        """Returns the current state of a service."""
        return self._service_states.get(name)

    def get_service(self, name: str) -> Optional[ServiceInterface]:
        """Returns the service instance."""
        return self._services.get(name)

    def _run_service(self, name: str):
        """The target function for the service thread."""
        service = self._services[name]
        try:
            self._logger.info(f"Starting service '{name}'...")
            self._set_state(name, ServiceState.RUNNING)
            service.start()  # This is a blocking call
        except Exception as e:
            self._logger.error(f"Service '{name}' failed: {e}", exc_info=True)
            self._set_state(name, ServiceState.FAILED)
        finally:
            # If start() returns (e.g., on graceful shutdown), update state
            if self._service_states[name] == ServiceState.RUNNING:
                self._set_state(name, ServiceState.STOPPED)

    def _set_state(self, name: str, state: ServiceState):
        """Sets the state of a service and emits a signal."""
        if self._service_states.get(name) == state:
            return
        self._service_states[name] = state
        self._logger.info(f"Service '{name}' state changed to {state.value}")
        global_signals.service_state_changed.emit(name, state)


# Global singleton instance
service_manager = ServiceManager()
service_manager.register_service('mqtt_broker', EmbeddedMQTTBroker())
