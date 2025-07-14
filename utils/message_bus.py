import abc
import enum
import json
import logging
import threading
import time
from typing import Callable, Dict, Any

import paho.mqtt.client as mqtt

from core.service_manager import service_manager
from .config import ConfigManager
from .signals import global_signals

# Default logger if none is provided
default_logger = logging.getLogger(__name__)


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
        self._client = None
        self._on_state_change_callback = on_state_change
        self._state = BusConnectionState.DISCONNECTED
        self._subscriptions: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._reconnect_delay = 1
        self._reconnect_thread: threading.Thread | None = None
        self._stop_reconnect = threading.Event()
        self._init_client()

    def _init_client(self):
        """Initializes the MQTT client."""
        client_id = self._config.get('client_id', '')
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                   client_id=client_id)
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
        self._stop_reconnect.set()
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self._reconnect_thread.join(timeout=2)  # Add timeout

        # Check if the client is actually connected before disconnecting
        if self._state == BusConnectionState.CONNECTED:
            self._client.disconnect()

        if self._client.is_connected():
            self._client.loop_stop()

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

    def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]],
                                                       None]) -> None:
        self.logger.info(f"Subscribing to topic: {topic}")
        self._subscriptions[topic] = callback
        if self._state == BusConnectionState.CONNECTED:
            self._client.subscribe(topic)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.logger.info("Successfully connected to MQTT broker.")
            self._set_state(BusConnectionState.CONNECTED)
            # Reset reconnect delay on successful connection
            self._reconnect_delay = 1
            self._stop_reconnect.set()  # Stop any running reconnect loop
            # Resubscribe to all topics
            for topic in self._subscriptions:
                self.logger.info(f"Resubscribing to {topic}")
                self._client.subscribe(topic)
        else:
            self.logger.error(
                f"Failed to connect to MQTT broker, return code: {rc}")
            self._set_state(BusConnectionState.DISCONNECTED)

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self.logger.warning(
            f"Disconnected from MQTT broker with result code: {rc}.")
        if not self._stop_reconnect.is_set():
            self._start_reconnect_loop()

    def _on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode('utf-8')
            global_signals.message_received.emit(msg.topic, payload_str)
            payload = json.loads(payload_str)
            if msg.topic in self._subscriptions:
                self._subscriptions[msg.topic](payload)
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

    def _reconnect_loop(self):
        while not self._stop_reconnect.is_set():
            try:
                self.logger.info(
                    f"Attempting to reconnect in {self._reconnect_delay} "
                    f"seconds...")
                time.sleep(self._reconnect_delay)

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


class MessageBusManager:
    """
    Singleton manager for the application's message bus.
    It handles the lifecycle of the bus and proxies calls to it.
    It coordinates with the ServiceManager to ensure the underlying
    service (e.g., an embedded MQTT broker) is running.
    """

    def __init__(self):
        self._config_manager = ConfigManager()
        self._logger = logging.getLogger(self.__class__.__name__)
        self._bus: MessageBusInterface | None = None
        self._subscriptions: Dict[str, Callable] = {}
        self._service_manager = service_manager
        self._initialize_bus()

    def _initialize_bus(self):
        """Initializes the MQTT bus client."""
        if self._bus:
            self._bus.disconnect()

        config = self._config_manager.mqtt
        self._bus = MqttBus(config=config,
                            logger=self._logger,
                            on_state_change=self._handle_state_change)

        # Re-apply all existing subscriptions to the new bus instance
        for topic, callback in self._subscriptions.items():
            self._bus.subscribe(topic, callback)

    def get_active_service_type(self) -> str:
        """Returns the type of the currently active service."""
        return 'mqtt'

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
        # Start the embedded broker service
        self._service_manager.start_service('mqtt_broker')

        # TODO: We might need a short delay or a signal-based wait here
        # to ensure the broker is fully up before the client tries to connect.
        # For now, we'll rely on the client's built-in reconnect logic.

        if self._bus:
            self._bus.connect()

    def disconnect(self):
        """
        Disconnects the message bus client and stops the embedded broker.
        """
        if self._bus:
            self._bus.disconnect()

        # Stop the embedded broker service
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
        self._subscriptions[topic] = callback
        if self._bus:
            self._bus.subscribe(topic, callback)


# Global singleton instance of the MessageBusManager
message_bus_manager = MessageBusManager()
