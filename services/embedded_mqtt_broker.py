import asyncio
import logging
import threading
import time
from collections import deque

from amqtt.broker import Broker

from core.service_interface import ServiceInterface
from utils.config import ConfigManager
from utils.signals import global_signals


class EmbeddedMQTTBroker(ServiceInterface):
    """
    An implementation of ServiceInterface that runs an embedded AMQTT broker.
    """

    def __init__(self,
                 config_manager: ConfigManager | None = None,
                 config_dir: str | None = None):
        self._logger = logging.getLogger(self.__class__.__name__)
        if config_manager:
            self._config_manager = config_manager
        else:
            self._config_manager = ConfigManager(config_dir=config_dir
                                                 or 'config')
        self._broker: Broker | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stats_thread: threading.Thread | None = None
        self._stats_running = False

        # --- Statistics ---
        self.clients_lock = threading.Lock()
        self.msg_sent = 0
        self.msg_received = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.last_stats_time = time.time()
        # Store last 60s of data points for rate calculation
        self.msg_sent_history = deque(maxlen=60)
        self.msg_recv_history = deque(maxlen=60)

        # Load MQTT configuration
        mqtt_config = self._config_manager.mqtt
        self.host = mqtt_config.get('host', 'localhost')
        self.port = mqtt_config.get('port', 1883)

        # AMQTT broker configuration
        self.config = {
            'listeners': {
                'default': {
                    'type': 'tcp',
                    'bind': f'{self.host}:{self.port}',
                    'max_connections': 50
                }
            },
            'sys_interval': 10,
            'topic-check': {
                'enabled': False
            }
        }
        # Connect signals to update stats
        self._signals_connected = False
        self._connect_signals()

    def _connect_signals(self):
        if self._signals_connected:
            return
        global_signals.message_published.connect(self._on_message_published)
        global_signals.message_received.connect(self._on_message_received)
        self._signals_connected = True

    def disconnect_signals(self):
        if not self._signals_connected:
            return
        for signal, handler in [
                (global_signals.message_published, self._on_message_published),
                (global_signals.message_received, self._on_message_received)
        ]:
            try:
                signal.disconnect(handler)
            except TypeError:
                self._logger.debug("Signal handler already disconnected")
        self._signals_connected = False

    def get_connection_details(self):
        return {'host': self.host, 'port': self.port}

    def _on_message_published(self, topic: str, payload: str):
        with self.clients_lock:
            self.msg_sent += 1
            self.bytes_sent += len(payload.encode('utf-8'))

    def _on_message_received(self, topic: str, payload: str):
        with self.clients_lock:
            self.msg_received += 1
            self.bytes_received += len(payload.encode('utf-8'))

    def _reset_stats(self):
        with self.clients_lock:
            self.msg_sent = 0
            self.msg_received = 0
            self.bytes_sent = 0
            self.bytes_received = 0
            self.msg_sent_history.clear()
            self.msg_recv_history.clear()

    def _stats_collector(self):
        """
        Periodically collects stats and emits a signal.
        Runs in a separate thread.
        """
        while self._stats_running:
            now = time.time()
            delta_time = now - self.last_stats_time
            self.last_stats_time = now

            with self.clients_lock:
                client_count = len(
                    self._broker.sessions) if self._broker else 0
                msg_sent_current = self.msg_sent
                msg_recv_current = self.msg_received
                self.msg_sent = 0
                self.msg_received = 0

            # Calculate rates
            msg_sent_rate = (msg_sent_current /
                             delta_time if delta_time > 0 else 0)
            msg_recv_rate = (msg_recv_current /
                             delta_time if delta_time > 0 else 0)

            self.msg_sent_history.append(msg_sent_rate)
            self.msg_recv_history.append(msg_recv_rate)

            stats = {
                'client_count': client_count,
                'msg_sent_rate': msg_sent_rate,
                'msg_recv_rate': msg_recv_rate,
                'msg_sent_history': list(self.msg_sent_history),
                'msg_recv_history': list(self.msg_recv_history),
            }
            global_signals.mqtt_stats_updated.emit(stats)

            time.sleep(1)

    def start(self):
        """
        Starts the embedded MQTT broker in the current thread.
        This is a blocking call.
        """
        self._connect_signals()
        self._logger.info(
            f"Starting embedded MQTT broker on {self.host}:{self.port}...")
        self._reset_stats()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._broker = Broker(self.config, loop=self._loop)

        # Start stats collector thread
        self._stats_running = True
        self._stats_thread = threading.Thread(target=self._stats_collector,
                                              daemon=True)
        self._stats_thread.start()

        try:
            self._loop.run_until_complete(self._broker.start())
            self._logger.info("MQTT Broker started.")
            self._loop.run_forever()
        except Exception as e:
            self._logger.error(f"Error starting MQTT broker: {e}",
                               exc_info=True)
        finally:
            self._logger.info("MQTT Broker event loop finished.")
            # Ensure stats thread is stopped when broker stops
            self.stop()

    def stop(self):
        """
        Stops the embedded MQTT broker.
        """
        # Stop the stats collector first
        if self._stats_running:
            self._stats_running = False
            if self._stats_thread and self._stats_thread.is_alive():
                self._stats_thread.join(timeout=2)
            self._stats_thread = None
            self._logger.info("MQTT stats collector stopped.")

        if self._broker and self._loop and self._loop.is_running():
            self._logger.info("Stopping embedded MQTT broker...")

            async def shutdown():
                await self._broker.shutdown()

            # Schedule the shutdown on the broker's event loop
            future = asyncio.run_coroutine_threadsafe(shutdown(), self._loop)

            try:
                # Wait for the shutdown to complete
                future.result(timeout=5)
                self._logger.info("Broker shutdown complete.")
            except Exception as e:
                self._logger.error(f"Error during broker shutdown: {e}")
            finally:
                # Stop the event loop
                if self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._loop.stop)
                    self._logger.info("Broker event loop stop requested.")
        else:
            self._logger.warning("Broker is not running or already stopped.")
