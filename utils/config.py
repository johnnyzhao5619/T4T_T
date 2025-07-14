import os
import configparser
import logging
from typing import Dict, Any
import yaml

logger = logging.getLogger(__name__)


def load_yaml(file_path: str) -> Dict[str, Any]:
    """
    Loads a YAML file and returns its content as a dictionary.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"YAML file not found at: {file_path}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file {file_path}: {e}")
        return {}


def save_yaml(file_path: str, data: Dict[str, Any]) -> None:
    """
    Saves a dictionary to a YAML file.
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        logger.error(f"Error saving YAML file {file_path}: {e}")


class ConfigManager:
    """
    A class responsible for managing application configuration settings from 
    a .ini file.

    This manager provides a robust way to access configuration, with built-in
    defaults, type conversion, and error handling.
    """

    def __init__(self, config_dir: str = 'config'):
        """
        Initialize the ConfigManager.

        Args:
            config_dir (str): The directory containing the configuration file.
        """
        self.config_file = os.path.join(config_dir, 'config.ini')
        self.config = configparser.ConfigParser()
        self._message_bus_config: Dict[str, Any] | None = None
        self._mqtt_config: Dict[str, Any] | None = None
        self._kafka_config: Dict[str, Any] | None = None
        self.load_config()

    def load_config(self) -> None:
        """
        Loads the configuration from the .ini file.
        If the file doesn't exist, it proceeds with an empty configuration,
        allowing fallbacks to default values.
        """
        if os.path.exists(self.config_file):
            self.config.read(self.config_file)
        else:
            logger.info(
                f"Configuration file not found at: {self.config_file}. "
                "Using default values.")

    @property
    def message_bus(self) -> Dict[str, Any]:
        """
        Get the [message_bus] configuration, parsed with defaults.

        Returns:
            A dictionary containing the message_bus configuration.
        """
        if self._message_bus_config is None:
            self._message_bus_config = {
                'active_service':
                self.config.get('message_bus',
                                'active_service',
                                fallback='mqtt')
            }
        return self._message_bus_config

    @property
    def mqtt(self) -> Dict[str, Any]:
        """
        Get the [MQTT] configuration, parsed with defaults and type safety.

        Returns:
            A dictionary containing the MQTT connection parameters.
        """
        if self._mqtt_config is None:
            self._mqtt_config = {
                'host':
                self.config.get('MQTT', 'host', fallback='localhost'),
                'port':
                self._get_int('MQTT', 'port', 1883),
                'username':
                self.config.get('MQTT', 'username', fallback=''),
                'password':
                self.config.get('MQTT', 'password', fallback=''),
                'client_id':
                self.config.get('MQTT', 'client_id', fallback=''),
                'reconnect_interval_max_seconds':
                self._get_int('MQTT', 'reconnect_interval_max_seconds', 60),
                'tls_enabled':
                self.config.getboolean('MQTT', 'tls_enabled', fallback=False)
            }
        return self._mqtt_config

    @property
    def kafka(self) -> Dict[str, Any]:
        """
        Get the [kafka] configuration, parsed with defaults.
        """
        if self._kafka_config is None:
            self._kafka_config = {
                'bootstrap_servers':
                self.config.get('kafka',
                                'bootstrap_servers',
                                fallback='localhost:9092'),
                'client_id':
                self.config.get('kafka', 'client_id', fallback='t4t_client'),
                'sasl_plain_username':
                self.config.get('kafka', 'sasl_plain_username', fallback=''),
                'sasl_plain_password':
                self.config.get('kafka', 'sasl_plain_password', fallback=''),
                'security_protocol':
                self.config.get('kafka',
                                'security_protocol',
                                fallback='PLAINTEXT'),
                'sasl_mechanism':
                self.config.get('kafka', 'sasl_mechanism', fallback=''),
            }
        return self._kafka_config

    def _get_int(self, section: str, key: str, fallback: int) -> int:
        """
        Safely retrieve an integer value from the configuration.

        If the section or key is missing, or if the value is not a valid
        integer, it logs a warning and returns the fallback value.

        Args:
            section (str): The section in the config file.
            key (str): The key in the section.
            fallback (int): The default value to return on failure.

        Returns:
            The integer value or the fallback.
        """
        try:
            return self.config.getint(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback  # No need to log if the key simply doesn't exist
        except ValueError:
            value = self.config.get(section, key)
            logger.warning(
                f"Invalid value for '{key}' in section '[{section}]'. "
                f"Expected an integer, but got '{value}'. "
                f"Using default value: {fallback}.")
            return fallback

    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        """
        Retrieve a configuration value for a given section and key.

        Args:
            section (str): The section in the config file.
            key (str): The key in the section.
            fallback: Value to return if the section or key is not found.

        Returns:
            The value associated with the key, or the fallback value.
        """
        return self.config.get(section, key, fallback=fallback)

    def set(self, section: str, key: str, value: str) -> None:
        """
        Set a configuration value for a given section and key.

        Args:
            section (str): The section in the config file.
            key (str): The key in the section.
            value (str): The value to set for the key.
        """
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, value)
        self.save_config()

    def save_config(self) -> None:
        """Save the current configuration to the config file."""
        # Ensure the directory exists before writing
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        with open(self.config_file, 'w') as configfile:
            self.config.write(configfile)
