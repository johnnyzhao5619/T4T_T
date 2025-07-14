import os
import sys
import time
import json
import pytest
import logging
import threading
import subprocess
from pathlib import Path

import paho.mqtt.client as mqtt

# Add project root to the Python path to allow imports of project modules
# This is a common pattern for testing standalone scripts
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from core.task_manager import TaskManager
from core.scheduler import SchedulerManager
from utils.signals import global_signals
from utils.message_bus import message_bus_manager, BusConnectionState

# Configure logging for tests
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s')
logger = logging.getLogger(__name__)

# --- Constants for MQTT Broker ---
MQTT_HOST = "localhost"
MQTT_PORT = 1883
# This assumes a local Mosquitto broker is running, perhaps in Docker.
# Command to run a temporary broker:
# docker run -d --rm --name test-mosquitto -p 1883:1883 -p 9001:9001 eclipse-mosquitto
# Command to stop it:
# docker stop test-mosquitto

# --- Fixtures ---


@pytest.fixture(scope="function")
def test_tasks_dir(tmp_path):
    """
    Pytest fixture to create a temporary, isolated directory for tasks for each test function.
    This ensures that tests do not interfere with each other.
    """
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    logger.info(f"Created temporary tasks directory: {tasks_dir}")
    yield str(tasks_dir)
    logger.info(f"Cleaning up temporary tasks directory: {tasks_dir}")
    # shutil.rmtree(tasks_dir) # tmp_path fixture handles cleanup automatically


@pytest.fixture(scope="function")
def task_creator(test_tasks_dir):
    """
    Factory fixture to create task files (config.yaml, main.py) within the temporary tasks directory.
    This simplifies the "Arrange" phase of the tests.
    """

    def _create_task(task_name: str, config: dict, script_content: str):
        task_path = Path(test_tasks_dir) / task_name
        task_path.mkdir()

        config_path = task_path / "config.yaml"
        script_path = task_path / "main.py"

        import yaml
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        with open(script_path, 'w') as f:
            f.write(script_content)

        logger.info(f"Created task '{task_name}' with config and script.")
        return str(task_path)

    return _create_task


@pytest.fixture(scope="function")
def mqtt_client():
    """
    Provides a connected paho-mqtt client for publishing messages during tests.
    This fixture now ensures the broker is available before yielding the client.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        logger.info("MQTT client connected for testing.")
        yield client
    except ConnectionRefusedError:
        pytest.fail(
            "MQTT Connection Refused. Please ensure the MQTT broker (e.g., Mosquitto in Docker) is running."
        )
    finally:
        if client.is_connected():
            client.loop_stop()
            client.disconnect()
        logger.info("MQTT client disconnected.")


@pytest.fixture(scope="function")
def bus_manager():
    """
    A fixture that manages the lifecycle of the message_bus_manager singleton.
    It ensures the bus is connected before tests run and disconnected after.
    This is crucial for preventing state pollution between tests.
    """
    import threading
    connected_event = threading.Event()

    def on_state_change(state, message):
        if state == BusConnectionState.CONNECTED.value:
            connected_event.set()

    global_signals.message_bus_status_changed.connect(on_state_change)

    try:
        message_bus_manager.connect()
        # Wait for the connection to be established, with a timeout
        was_set = connected_event.wait(timeout=5)
        if not was_set:
            pytest.fail(
                "Message bus did not connect within the 5-second timeout.")

        yield message_bus_manager

    finally:
        # Teardown
        global_signals.message_bus_status_changed.disconnect(on_state_change)
        message_bus_manager.disconnect()
        # Give a moment for the disconnect to process
        time.sleep(0.5)


@pytest.fixture(scope="function")
def active_task_manager(test_tasks_dir, bus_manager):
    """
    Provides a TaskManager that is initialized with a guaranteed-connected bus.
    """
    scheduler = SchedulerManager()
    task_manager = TaskManager(scheduler_manager=scheduler,
                               tasks_dir=test_tasks_dir)
    yield task_manager
    task_manager.shutdown()


# --- Test Cases ---


def test_producer_consumer_flow(task_creator, active_task_manager):
    """
    Tests the basic producer-consumer pattern.
    """
    # --- Arrange ---
    test_tasks_dir = active_task_manager.tasks_dir
    flag_file = Path(test_tasks_dir) / "consumer_run.flag"

    # Create tasks
    consumer_config = {
        "name": "C",
        "module_type": "test",
        "enabled": True,
        "trigger": {
            "type": "event",
            "topic": "test/consumer"
        }
    }
    consumer_script = f'def run(c, i): open("{flag_file.as_posix()}", "w").write("c")'
    task_creator("ConsumerTask", consumer_config, consumer_script)

    producer_config = {
        "name": "P",
        "module_type": "test",
        "enabled": True,
        "trigger": {
            "type": "interval",
            "config": {
                "seconds": 1
            }
        }
    }
    producer_script = 'from utils.message_bus import message_bus_manager\ndef run(c,i): message_bus_manager.publish("test/consumer", {"d":"h"})'
    task_creator("ProducerTask", producer_config, producer_script)

    active_task_manager.load_tasks()

    # --- Act ---
    time.sleep(2)

    # --- Assert ---
    assert flag_file.exists(), "Consumer task did not create the flag file."


def test_mqtt_reconnection_and_recovery(task_creator, test_tasks_dir, caplog):
    """
    Tests the MQTT client's ability to automatically reconnect.
    """
    # --- Arrange ---
    broker_container_name = "test-mosquitto"
    flag_file = Path(test_tasks_dir) / "recovery.flag"
    task_creator(
        "RecoveryConsumer", {
            "name": "RC",
            "module_type": "test",
            "enabled": True,
            "trigger": {
                "type": "event",
                "topic": "test/recovery"
            }
        }, f'def run(c,i): open("{flag_file.as_posix()}", "w").write("r")')

    # Setup signal listener and event for synchronization
    status_event = threading.Event()
    status_changes = []

    def on_status_change(state, message):
        logger.info(f"SIGNAL RECEIVED: {state} - {message}")
        status_changes.append(BusConnectionState(state))
        status_event.set()

    global_signals.message_bus_status_changed.connect(on_status_change)

    # --- Act & Assert ---
    # 1. Initial Connection
    status_event.clear()
    message_bus_manager.connect()
    assert status_event.wait(5), "Initial connection signal timed out"
    assert status_changes[
        -1] == BusConnectionState.CONNECTED, "Initial connection failed"

    task_manager = TaskManager(scheduler_manager=SchedulerManager(),
                               tasks_dir=test_tasks_dir)

    # 2. Stop Broker and Assert Reconnecting
    status_event.clear()
    subprocess.run(["docker", "stop", broker_container_name],
                   check=True,
                   capture_output=True)
    assert status_event.wait(10), "Reconnecting signal timed out"
    assert BusConnectionState.RECONNECTING in status_changes
    assert "Reconnecting in" in caplog.text

    # 3. Restart Broker and Assert Reconnected
    status_event.clear()
    subprocess.run(["docker", "start", broker_container_name],
                   check=True,
                   capture_output=True)
    assert status_event.wait(15), "Reconnect to CONNECTED signal timed out"
    assert status_changes[-1] == BusConnectionState.CONNECTED

    # 4. Verify Message Flow
    mqtt_client().publish("test/recovery", json.dumps({"data": "test"}))
    time.sleep(1)
    assert flag_file.exists(
    ), "Consumer task was not triggered after reconnection"

    # --- Teardown ---
    task_manager.shutdown()
    global_signals.message_bus_status_changed.disconnect(on_status_change)
    message_bus_manager.disconnect()


def test_input_validation_failure(task_creator, active_task_manager,
                                  mqtt_client, caplog):
    """
    Tests that a task is not executed if a required input is missing.
    """
    # --- Arrange ---
    flag_file = Path(active_task_manager.tasks_dir) / "validation_run.flag"
    topic = "test/validation"
    config = {
        "name": "VT",
        "module_type": "test",
        "enabled": True,
        "trigger": {
            "type": "event",
            "topic": topic
        },
        "inputs": [{
            "name": "data",
            "required": True
        }]
    }
    script = f'def run(c,i): open("{flag_file.as_posix()}", "w").write("v")'
    task_creator("ValidationTask", config, script)
    active_task_manager.load_tasks()

    # --- Act ---
    mqtt_client.publish(topic, json.dumps({"other_field": "value"}))
    time.sleep(1)

    # --- Assert ---
    assert not flag_file.exists()
    assert "missing required input 'data'" in caplog.text


def test_circular_dependency_detection(task_creator, active_task_manager,
                                       mqtt_client, caplog):
    """
    Tests that the system prevents infinite loops by using a hop count.
    """
    # --- Arrange ---
    max_hops = 5
    log_a = Path(active_task_manager.tasks_dir) / "task_a.log"
    log_b = Path(active_task_manager.tasks_dir) / "task_b.log"

    # Task A: listens on topic/A, publishes to topic/B
    conf_a = {
        "name": "A",
        "module_type": "test",
        "enabled": True,
        "trigger": {
            "type": "event",
            "topic": "topic/A"
        }
    }
    script_a = f'from u_m import message_bus_manager\ndef run(c,i):open("{log_a.as_posix()}","a").write("r\\n");message_bus_manager.publish("topic/B", {{"d":"fA"}})'
    task_creator("TaskA", conf_a, script_a.replace("u_m", "utils.message_bus"))

    # Task B: listens on topic/B, publishes to topic/A
    conf_b = {
        "name": "B",
        "module_type": "test",
        "enabled": True,
        "trigger": {
            "type": "event",
            "topic": "topic/B"
        }
    }
    script_b = f'from u_m import message_bus_manager\ndef run(c,i):open("{log_b.as_posix()}","a").write("r\\n");message_bus_manager.publish("topic/A", {{"d":"fB"}})'
    task_creator("TaskB", conf_b, script_b.replace("u_m", "utils.message_bus"))

    active_task_manager.load_tasks()

    # --- Act ---
    mqtt_client.publish("topic/A", json.dumps({"data": "initial"}))
    time.sleep(3)

    # --- Assert ---
    task_a_runs = len(open(log_a).readlines()) if log_a.exists() else 0
    task_b_runs = len(open(log_b).readlines()) if log_b.exists() else 0
    total_runs = task_a_runs + task_b_runs

    assert total_runs <= max_hops + 1
    assert "max hop count exceeded" in caplog.text


def test_graceful_shutdown(task_creator, test_tasks_dir):
    """
    Tests that the application waits for running tasks to complete before
    shutting down.
    """
    # --- Arrange ---
    sleep_duration = 4
    start_time_file = Path(test_tasks_dir) / "start.time"
    end_time_file = Path(test_tasks_dir) / "end.time"

    # 1. Create a long-running task
    long_task_config = {
        "name": "LongTask",
        "module_type": "test",
        "enabled": True,
        "trigger": {
            "type": "interval",
            "config": {
                "seconds": 10
            }
        }  # Schedule once
    }
    long_task_script = f"""
import time
def run(context, inputs):
    with open("{start_time_file.as_posix()}", "w") as f:
        f.write(str(time.time()))
    
    time.sleep({sleep_duration})
    
    with open("{end_time_file.as_posix()}", "w") as f:
        f.write(str(time.time()))
"""
    task_creator("LongTask", long_task_config, long_task_script)

    # --- Act ---
    scheduler = SchedulerManager()
    task_manager = TaskManager(scheduler_manager=scheduler,
                               tasks_dir=test_tasks_dir)

    # Manually trigger the task for consistent timing
    task_manager._execute_task_logic("LongTask", {})

    # Give the task a moment to start and create the start file
    time.sleep(1)
    assert start_time_file.exists()

    # Trigger shutdown while the task is sleeping
    shutdown_start_time = time.time()
    task_manager.shutdown()
    shutdown_end_time = time.time()

    # --- Assert ---
    shutdown_duration = shutdown_end_time - shutdown_start_time

    # The shutdown should be blocked for roughly the remainder of the sleep time
    assert shutdown_duration > (sleep_duration - 1.5), \
        f"Shutdown was too fast ({shutdown_duration:.2f}s), indicating it didn't wait for the task."

    assert end_time_file.exists(
    ), "Task did not complete and create the end time file."

    with open(start_time_file) as f:
        start_time = float(f.read())
    with open(end_time_file) as f:
        end_time = float(f.read())

    task_run_duration = end_time - start_time
    assert task_run_duration >= sleep_duration, "Task did not run for its full duration."
