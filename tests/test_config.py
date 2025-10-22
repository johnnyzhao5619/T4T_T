import logging
import os
import sys
import textwrap

import pytest

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from core.state_manager import StateManager
from utils.config import ConfigManager, load_yaml


def test_defaults_when_no_file(tmp_path):
    """
    Tests that ConfigManager returns all default values when the config
    file does not exist.
    """
    # Point to a non-existent config directory
    config_dir = tmp_path / "non_existent_config"
    manager = ConfigManager(config_dir=str(config_dir))

    # Test MessageBus defaults
    assert manager.message_bus['type'] == 'MQTT'

    # Test MQTT defaults
    mqtt_config = manager.mqtt
    assert mqtt_config['host'] == 'localhost'
    assert mqtt_config['port'] == 1883
    assert mqtt_config['username'] == ''
    assert mqtt_config['password'] == ''
    assert mqtt_config['client_id'] == ''
    assert mqtt_config['reconnect_interval_max_seconds'] == 60
    assert mqtt_config['tls_enabled'] is False


def test_loading_full_config(tmp_path):
    """
    Tests that ConfigManager correctly loads all specified values from a
    valid config.ini file.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.ini"
    config_content = """
[MessageBus]
type = TestBus

[MQTT]
host = 192.168.1.1
port = 8883
username = testuser
password = testpass
client_id = test_client_123
reconnect_interval_max_seconds = 30
tls_enabled = True
"""
    config_file.write_text(config_content)

    manager = ConfigManager(config_dir=str(config_dir))

    # Test MessageBus value
    assert manager.message_bus['type'] == 'TestBus'

    # Test MQTT values
    mqtt_config = manager.mqtt
    assert mqtt_config['host'] == '192.168.1.1'
    assert mqtt_config['port'] == 8883
    assert mqtt_config['username'] == 'testuser'
    assert mqtt_config['password'] == 'testpass'
    assert mqtt_config['client_id'] == 'test_client_123'
    assert mqtt_config['reconnect_interval_max_seconds'] == 30
    assert mqtt_config['tls_enabled'] is True


def test_partial_config_with_defaults(tmp_path):
    """
    Tests that ConfigManager uses defaults for missing keys in a section.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.ini"
    config_content = """
[MQTT]
host = remote.broker.com
port = 1884
# username and other keys are missing
"""
    config_file.write_text(config_content)

    manager = ConfigManager(config_dir=str(config_dir))

    # Test specified and default values
    mqtt_config = manager.mqtt
    assert mqtt_config['host'] == 'remote.broker.com'
    assert mqtt_config['port'] == 1884
    assert mqtt_config['username'] == ''  # Default
    assert mqtt_config['password'] == ''  # Default


def test_missing_section_with_defaults(tmp_path):
    """
    Tests that ConfigManager uses all defaults when a whole section is missing.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.ini"
    config_content = """
[MessageBus]
type = Kafka
# [MQTT] section is completely missing
"""
    config_file.write_text(config_content)

    manager = ConfigManager(config_dir=str(config_dir))

    # Test that all MQTT values are defaults
    mqtt_config = manager.mqtt
    assert mqtt_config['host'] == 'localhost'
    assert mqtt_config['port'] == 1883
    assert mqtt_config['username'] == ''


def test_invalid_integer_value_fallback(tmp_path, caplog):
    """
    Tests that ConfigManager falls back to the default value and logs a
    warning when an integer key has an invalid value.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.ini"
    config_content = """
[MQTT]
port = not-a-number
reconnect_interval_max_seconds = also-invalid
"""
    config_file.write_text(config_content)

    with caplog.at_level(logging.WARNING):
        manager = ConfigManager(config_dir=str(config_dir))
        mqtt_config = manager.mqtt

        # Assert that fallbacks are used
        assert mqtt_config['port'] == 1883
        assert mqtt_config['reconnect_interval_max_seconds'] == 60

        # Assert that warnings were logged
        assert len(caplog.records) == 2
        assert "Invalid value for 'port'" in caplog.text
        assert "Using default value: 1883" in caplog.text
        reconnect_log = "Invalid value for 'reconnect_interval_max_seconds'"
        assert reconnect_log in caplog.text
        assert "Using default value: 60" in caplog.text


def test_lowercase_sections_are_read(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.ini"
    config_content = textwrap.dedent("""
        [message_bus]
        type = CustomBus
        active_service = kafka

        [mqtt]
        host = mqtt.local
        port = 2883
        username = lower_user
        password = lower_pass
        client_id = lower_client
        reconnect_interval_max_seconds = 45
        tls_enabled = false

        [kafka]
        bootstrap_servers = kafka.local:29092
        client_id = lower_kafka_client
    """)
    config_file.write_text(config_content)

    manager = ConfigManager(config_dir=str(config_dir))

    assert manager.message_bus['type'] == 'CustomBus'
    assert manager.message_bus['active_service'] == 'kafka'

    mqtt_config = manager.mqtt
    assert mqtt_config['host'] == 'mqtt.local'
    assert mqtt_config['port'] == 2883
    assert mqtt_config['username'] == 'lower_user'
    assert mqtt_config['password'] == 'lower_pass'
    assert mqtt_config['client_id'] == 'lower_client'
    assert mqtt_config['reconnect_interval_max_seconds'] == 45
    assert mqtt_config['tls_enabled'] is False

    kafka_config = manager.kafka
    assert kafka_config['bootstrap_servers'] == 'kafka.local:29092'
    assert kafka_config['client_id'] == 'lower_kafka_client'

    assert manager.get('mqtt', 'host') == 'mqtt.local'
    assert manager.get('MQTT', 'host') == 'mqtt.local'


def test_set_invalidates_cached_properties(tmp_path):
    config_dir = tmp_path / "config"
    manager = ConfigManager(config_dir=str(config_dir))

    # 预热缓存，随后更新值应立即反映出来。
    assert manager.message_bus['type'] == 'MQTT'
    manager.set('MessageBus', 'type', 'Kafka')
    assert manager.message_bus['type'] == 'Kafka'

    assert manager.mqtt['host'] == 'localhost'
    manager.set('MQTT', 'host', 'mqtt.example.com')
    assert manager.mqtt['host'] == 'mqtt.example.com'


def test_load_yaml_empty_file_returns_empty_dict(tmp_path, caplog):
    empty_yaml = tmp_path / "empty.yaml"
    empty_yaml.write_text("", encoding='utf-8')

    with caplog.at_level(logging.INFO):
        data = load_yaml(str(empty_yaml))

    assert data == {}
    assert any("empty" in record.message for record in caplog.records)


def test_task_manager_loads_empty_config_without_error(tmp_path):
    pytest.importorskip(
        "PyQt5.QtWidgets",
        reason="PyQt5 is required for TaskManager tests",
        exc_type=ImportError,
    )
    from core.task_manager import TaskManager

    tasks_dir = tmp_path / "tasks"
    task_dir = tasks_dir / "dummy"
    task_dir.mkdir(parents=True)
    (task_dir / "main.py").write_text("def run():\n    pass\n", encoding='utf-8')
    (task_dir / "config.yaml").write_text("", encoding='utf-8')

    task_manager = TaskManager.__new__(TaskManager)
    task_manager.tasks_dir = str(tasks_dir)
    task_manager.tasks = {}
    task_manager._event_task_topics = {}
    task_manager.state_manager = StateManager()
    task_manager._unsubscribe_event_task = lambda *_, **__: None
    task_manager._initialize_tasks = lambda: None

    try:
        task_manager.load_tasks()
    except Exception as exc:  # pragma: no cover - explicit failure path
        pytest.fail(f"load_tasks raised an exception: {exc}")

    assert "dummy" in task_manager.tasks
    assert task_manager.tasks["dummy"]["config_data"] == {}
