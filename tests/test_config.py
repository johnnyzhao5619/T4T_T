import logging
from utils.config import ConfigManager


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
