import abc
import enum
import json
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

import paho.mqtt.client as mqtt

from core.service_manager import service_manager, ServiceState
from .config import ConfigManager
from .signals import global_signals

# Default logger if none is provided
default_logger = logging.getLogger(__name__)


SERVICE_START_TIMEOUT_SECONDS = 10.0


class BusConnectionState(enum.Enum):
    """Enumeration for the message bus connection state."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"


class MessageBusInterface(abc.ABC):
    """Abstract base class for a message bus."""

    @abc.abstractmethod
    def connect(self) -> None:
        """Connect to the message bus."""
        pass

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the message bus."""
        pass

    @abc.abstractmethod
    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Publish a message to a topic.

        Args:
            topic (str): The topic to publish to.
            payload (Dict[str, Any]): The message payload.
        """
        pass

    @abc.abstractmethod
    def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]],
                                                       None]) -> None:
        """
        Subscribe to a topic.

        Args:
            topic (str): The topic to subscribe to.
            callback (Callable): The function to call when a message
            is received.
        """
        pass

    @abc.abstractmethod
    def unsubscribe(self, topic: str,
                    callback: Callable[[Dict[str, Any]], None] | None = None
                    ) -> None:
        """Unsubscribe from a topic."""
        pass


class MqttBus(MessageBusInterface):
    """
    A message bus implementation using the MQTT protocol with paho-mqtt.
    It handles connection, disconnection, and automatic reconnection logic.
    """

    def __init__(self,
                 config: Dict[str, Any],
                 logger: logging.Logger = default_logger,
                 on_state_change: Callable[[BusConnectionState], None]
                 | None = None):
        self.logger = logger
        self._config = config
        self._client: mqtt.Client | None = None
        self._on_state_change_callback = on_state_change
        self._state = BusConnectionState.DISCONNECTED
        self._subscriptions: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._reconnect_delay = 1
        self._reconnect_thread: threading.Thread | None = None
        self._stop_reconnect = threading.Event()
        self._init_client()

    def _init_client(self):
        """Initializes the MQTT client."""
        client_id = self._config.get('client_id', '')
        self._client = mqtt.Client(client_id=client_id,
                                   callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        if self._config.get('username'):
            self._client.username_pw_set(self._config['username'],
                                         self._config.get('password'))

        if self._config.get('tls_enabled'):
            self._client.tls_set()

    def _set_state(self, new_state: BusConnectionState):
        if self._state != new_state:
            self._state = new_state
            self.logger.info(f"MQTT state changed to: {new_state.value}")
            if self._on_state_change_callback:
                self._on_state_change_callback(new_state)

    def get_state(self) -> BusConnectionState:
        """Returns the current connection state of the bus."""
        return self._state

    def connect(self) -> None:
        if self._state != BusConnectionState.DISCONNECTED:
            self.logger.warning(
                "Connect called while not in a disconnected state.")
            return

        self._set_state(BusConnectionState.CONNECTING)
        try:
            self._client.connect_async(self._config['host'],
                                       self._config['port'])
            self._client.loop_start()
        except (OSError, ConnectionRefusedError) as e:
            self.logger.error(f"MQTT connection failed: {e}")
            self._set_state(BusConnectionState.DISCONNECTED)
            self._start_reconnect_loop()

    def disconnect(self) -> None:
        self.logger.info("Disconnecting from MQTT broker...")
        self._stop_reconnect_loop()

        # Check if the client is actually connected before disconnecting
        if self._client and self._state == BusConnectionState.CONNECTED:
            self._client.disconnect()

        if self._client:
            try:
                self._client.loop_stop()
            except Exception as exc:
                self.logger.warning("Failed to stop MQTT network loop: %s", exc)

        # Always ensure the state is set to DISCONNECTED
        self._set_state(BusConnectionState.DISCONNECTED)

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._state != BusConnectionState.CONNECTED:
            self.logger.warning(f"Cannot publish, MQTT is not connected. "
                                f"State: {self._state.value}")
            return

        # Cycle detection
        hops = payload.get('__hops', 0) + 1
        payload['__hops'] = hops

        try:
            json_payload = json.dumps(payload)
            # Emit signal before publishing
            global_signals.message_published.emit(topic, json_payload)
            self._client.publish(topic, json_payload)
        except TypeError as e:
            self.logger.error(
                f"Failed to serialize payload for topic '{topic}': {e}")

    def subscribe(self, topic: str,
                  callback: Callable[[Dict[str, Any]], None]) -> None:
        self.logger.info(f"Subscribing to topic: {topic}")
        callbacks = self._subscriptions.setdefault(topic, [])
        if callback in callbacks:
            return

        callbacks.append(callback)
        if self._state == BusConnectionState.CONNECTED and len(callbacks) == 1:
            try:
                self._client.subscribe(topic)
            except Exception as exc:
                self.logger.error(
                    f"Failed to subscribe to topic '{topic}': {exc}")

    def unsubscribe(self, topic: str,
                    callback: Callable[[Dict[str, Any]], None] | None = None
                    ) -> None:
        self.logger.info(f"Unsubscribing from topic: {topic}")
        callbacks = self._subscriptions.get(topic)
        if not callbacks:
            return

        removed_all = False

        if callback is None:
            removed_all = True
            self._subscriptions.pop(topic, None)
        else:
            try:
                callbacks.remove(callback)
            except ValueError:
                self.logger.debug(
                    "Callback not found for topic '%s' during unsubscribe.",
                    topic)
            else:
                if not callbacks:
                    removed_all = True
                    self._subscriptions.pop(topic, None)

        if removed_all and self._client and self._state == BusConnectionState.CONNECTED:
            try:
                self._client.unsubscribe(topic)
            except Exception as exc:
                self.logger.error(
                    f"Failed to unsubscribe from topic '{topic}': {exc}")

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.logger.info("Successfully connected to MQTT broker.")
            self._set_state(BusConnectionState.CONNECTED)
            # Reset reconnect delay on successful connection
            self._reconnect_delay = 1
            self._stop_reconnect_loop(wait=False)
            # Resubscribe to all topics
            for topic in self._subscriptions:
                self.logger.info(f"Resubscribing to {topic}")
                self._client.subscribe(topic)
        else:
            self.logger.error(
                f"Failed to connect to MQTT broker, return code: {rc}")
            self._set_state(BusConnectionState.DISCONNECTED)

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        self.logger.warning(
            f"Disconnected from MQTT broker with result code: {rc}.")
        if not self._stop_reconnect.is_set():
            self._start_reconnect_loop()

    def _on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode('utf-8')
            global_signals.message_received.emit(msg.topic, payload_str)
            payload = json.loads(payload_str)
            callbacks = self._subscriptions.get(msg.topic)
            if callbacks:
                for callback in list(callbacks):
                    try:
                        callback(payload)
                    except Exception as exc:
                        self.logger.error(
                            "Error in callback for topic '%s': %s",
                            msg.topic,
                            exc)
            else:
                self.logger.warning(
                    f"Received message on unsubscribed topic: {msg.topic}")
        except json.JSONDecodeError:
            self.logger.error(
                f"Could not decode JSON payload from topic: {msg.topic}")
        except Exception as e:
            self.logger.error(
                f"Error processing message from topic {msg.topic}: {e}")

    def _start_reconnect_loop(self):
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return  # Reconnect loop already running

        self._set_state(BusConnectionState.RECONNECTING)
        self._stop_reconnect.clear()
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop,
                                                  daemon=True)
        self._reconnect_thread.start()

    def _stop_reconnect_loop(self, wait: bool = True):
        self._stop_reconnect.set()
        thread = self._reconnect_thread
        if not thread:
            return

        if wait and thread is not threading.current_thread():
            thread.join(timeout=2)
            if thread.is_alive():
                self.logger.warning(
                    "MQTT reconnect thread did not terminate within timeout.")

        if not thread.is_alive():
            self._reconnect_thread = None

    def _reconnect_loop(self):
        try:
            while not self._stop_reconnect.is_set():
                try:
                    self.logger.info(
                        f"Attempting to reconnect in {self._reconnect_delay} "
                        f"seconds...")
                    if self._stop_reconnect.wait(self._reconnect_delay):
                        break

                    # Use blocking connect in the reconnect loop
                    self._client.reconnect()
                    # If reconnect() is successful, on_connect will be called
                    # and will stop the loop.
                    break
                except (OSError, ConnectionRefusedError) as e:
                    self.logger.warning(f"Reconnect attempt failed: {e}")
                    max_delay = self._config.get('reconnect_interval_max_seconds',
                                                 60)
                    self._reconnect_delay = min(self._reconnect_delay * 2,
                                                max_delay)
        finally:
            if self._reconnect_thread is threading.current_thread():
                self._reconnect_thread = None


class MessageBusManager:
    """
    Singleton manager for the application's message bus.
    It handles the lifecycle of the bus and proxies calls to it.
    It coordinates with the ServiceManager to ensure the underlying
    service (e.g., an embedded MQTT broker) is running.
    """

    def __init__(self,
                 config_manager: ConfigManager | None = None,
                 config_dir: str | None = None):
        self._config_manager: ConfigManager | None = None
        self._logger = logging.getLogger(self.__class__.__name__)
        self._bus: MessageBusInterface | None = None
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._service_manager = service_manager
        self._active_service_type = 'mqtt'
        self._warned_missing_service = False
        self._set_config_manager(config_manager=config_manager,
                                 config_dir=config_dir)
        self._initialize_bus()

    def _set_config_manager(self,
                            config_manager: ConfigManager | None = None,
                            config_dir: str | None = None) -> None:
        """Resolves and assigns the ConfigManager instance."""
        if config_manager:
            self._config_manager = config_manager
            return

        if config_dir:
            self._config_manager = ConfigManager(config_dir=config_dir)
            return

        if self._config_manager is None:
            self._config_manager = ConfigManager()

    def configure(self,
                  *,
                  config_manager: ConfigManager | None = None,
                  config_dir: str | None = None) -> None:
        """Updates the configuration source and rebuilds the bus instance."""
        self._set_config_manager(config_manager=config_manager,
                                 config_dir=config_dir)
        self._initialize_bus()

    def _initialize_bus(self):
        """Initializes the MQTT bus client."""
        if self._bus:
            self._bus.disconnect()

        if self._config_manager is None:
            raise RuntimeError("ConfigManager must be set before initializing the"
                               " message bus.")

        config = self._config_manager.mqtt
        self._bus = MqttBus(config=config,
                            logger=self._logger,
                            on_state_change=self._handle_state_change)

        # Re-apply all existing subscriptions to the new bus instance
        for topic, callbacks in self._subscriptions.items():
            for callback in callbacks:
                self._bus.subscribe(topic, callback)

    def _should_manage_embedded_broker(self) -> bool:
        """Determines whether the manager should control the embedded broker."""
        if self._active_service_type != 'mqtt':
            return False

        if self._config_manager is None:
            return True

        mode = (self._config_manager.get('mqtt', 'mode', fallback='embedded')
                or 'embedded').strip().lower()
        if mode != 'embedded':
            self._logger.info(
                "MQTT configuration set to '%s'; assuming external broker.",
                mode)
            return False

        service = self._service_manager.get_service('mqtt_broker')
        if service is None:
            if not self._warned_missing_service:
                self._logger.warning(
                    "Embedded MQTT mode enabled but no 'mqtt_broker' service "
                    "is registered. Proceeding without managed startup.")
                self._warned_missing_service = True
            return False

        return True

    def get_active_service_type(self) -> str:
        """Returns the type of the currently active service."""
        return self._active_service_type

    def _handle_state_change(self, new_state: BusConnectionState):
        """
        Emits a global signal when the bus state changes.
        """
        message = f"Message bus state changed to {new_state.value}."
        global_signals.message_bus_status_changed.emit(new_state.value,
                                                       message)

    def get_bus(self):
        """Returns the underlying message bus instance."""
        return self._bus

    def get_state(self) -> BusConnectionState:
        """Returns the current connection state of the managed bus."""
        if self._bus and hasattr(self._bus, 'get_state'):
            return self._bus.get_state()
        return BusConnectionState.DISCONNECTED

    def connect(self):
        """
        Ensures the embedded broker service is running and then connects the
        message bus client.
        """
        if not self._bus:
            return

        if not self._should_manage_embedded_broker():
            self._bus.connect()
            return

        wait_event = threading.Event()
        failure_state: Optional[ServiceState] = None

        def _on_service_state_changed(service_name: str,
                                       state: ServiceState) -> None:
            nonlocal failure_state
            if service_name != 'mqtt_broker':
                return
            if state == ServiceState.RUNNING:
                wait_event.set()
            elif state in (ServiceState.FAILED, ServiceState.STOPPED):
                failure_state = state
                wait_event.set()

        global_signals.service_state_changed.connect(_on_service_state_changed)

        try:
            state = self._service_manager.get_service_state('mqtt_broker')
            if state == ServiceState.RUNNING:
                wait_event.set()
            else:
                if state not in (ServiceState.STARTING, ServiceState.RUNNING):
                    self._logger.info(
                        "Starting embedded MQTT broker before connecting bus.")
                    self._service_manager.start_service('mqtt_broker')

                # Double-check in case the service transitioned immediately.
                current_state = self._service_manager.get_service_state(
                    'mqtt_broker')
                if current_state == ServiceState.RUNNING:
                    wait_event.set()

                if not wait_event.wait(SERVICE_START_TIMEOUT_SECONDS):
                    self._logger.error(
                        "Timed out after %.1f seconds waiting for 'mqtt_broker' "
                        "to reach RUNNING state.",
                        SERVICE_START_TIMEOUT_SECONDS)
                    return

            if failure_state is not None and failure_state != ServiceState.RUNNING:
                self._logger.error(
                    "Service 'mqtt_broker' entered %s state before connection.",
                    failure_state.value)
                return
        finally:
            try:
                global_signals.service_state_changed.disconnect(
                    _on_service_state_changed)
            except TypeError:
                pass

        self._bus.connect()

    def disconnect(self):
        """
        Disconnects the message bus client and stops the embedded broker.
        """
        if self._bus:
            self._bus.disconnect()

        # Stop the embedded broker service
        if self._active_service_type == 'mqtt':
            self._service_manager.stop_service('mqtt_broker')

    def publish(self, topic: str, payload: Dict[str, Any]):
        """
        Publishes a message through the bus.

        Args:
            topic (str): The topic to publish to.
            payload (Dict[str, Any]): The message payload.
        """
        if self._bus:
            self._bus.publish(topic, payload)

    def subscribe(self, topic: str, callback: Callable):
        """
        Subscribes to a topic through the bus and stores the subscription
        to re-apply it if the bus service is switched.
        """
        callbacks = self._subscriptions.setdefault(topic, [])
        if callback not in callbacks:
            callbacks.append(callback)
            if self._bus:
                self._bus.subscribe(topic, callback)

    def unsubscribe(self, topic: str, callback: Callable | None = None):
        """Unsubscribes from a topic and removes internal bookkeeping."""
        callbacks = self._subscriptions.get(topic)
        if not callbacks:
            if self._bus:
                if callback is None:
                    self._bus.unsubscribe(topic)
                else:
                    self._bus.unsubscribe(topic, callback)
            return

        if callback is None:
            self._subscriptions.pop(topic, None)
            if self._bus:
                self._bus.unsubscribe(topic)
            return

        removed_callback = False
        if callback in callbacks:
            callbacks.remove(callback)
            removed_callback = True
            if self._bus:
                self._bus.unsubscribe(topic, callback)
        if not callbacks:
            self._subscriptions.pop(topic, None)
            if self._bus and not removed_callback:
                self._bus.unsubscribe(topic)

    def switch_service(self, service_type: str):
        """
        Switches the active message bus implementation.

        Currently only the embedded MQTT implementation is supported,
        but the method exists to avoid runtime errors from UI actions
        and to provide a single place to extend the behaviour.
        """
        normalized_type = service_type.lower()
        if normalized_type != 'mqtt':
            self._logger.warning(
                "Unsupported message bus service requested: %s",
                service_type)
            return

        if normalized_type == self._active_service_type:
            self._logger.debug("Message bus already using '%s'.", service_type)
            return

        self.disconnect()
        self._active_service_type = normalized_type
        self._initialize_bus()
        self.connect()


# Global singleton instance of the MessageBusManager
message_bus_manager = MessageBusManager()
